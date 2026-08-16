"""
tools/memory.py
----------------
Gestion de la mémoire persistante à long terme pour Monika, avec SQLite.

La recherche est désormais sémantique : chaque information enregistrée est
vectorisée (embedding) via le même serveur local que le modèle de chat
(voir EMBEDDING_MODEL_NAME dans config.py), et une recherche compare le sens
de la requête aux souvenirs stockés plutôt qu'un simple mot-clé exact.
Exemple concret : chercher "éditeur de code" retrouvera un souvenir enregistré
sous la clé "outil_dev" avec la valeur "VS Code", ce qu'un LIKE SQL ne
pouvait pas faire.

Robustesse : si le serveur d'embeddings est injoignable (modèle non chargé,
serveur éteint...), on retombe automatiquement sur l'ancienne recherche par
mot-clé (LIKE) plutôt que de faire échouer l'outil.
"""

import os
import sqlite3
from typing import Optional

import numpy as np

from config import client, EMBEDDING_MODEL_NAME

DB_PATH = os.path.expanduser("~/.config/monika/memory.db")

# Nombre max de résultats sémantiques renvoyés, et seuil de similarité
# cosinus en dessous duquel un résultat est jugé trop peu pertinent pour
# être montré (évite de renvoyer du bruit sur une base volumineuse).
SEMANTIC_TOP_K = 5
SEMANTIC_MIN_SIMILARITY = 0.35

# Nombre max de souvenirs "rattrapés" (backfill) en une seule recherche,
# pour les entrées enregistrées avant l'activation de cette fonctionnalité
# ou pendant une panne du serveur d'embeddings.
BACKFILL_BATCH_SIZE = 25


def _init_db() -> None:
    """Initialise la table de mémoire si elle n'existe pas, et migre le schéma
    (ajout de la colonne 'embedding') si la base existait déjà sans."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                key TEXT UNIQUE NOT NULL,
                value TEXT NOT NULL,
                embedding BLOB,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        existing_columns = {row[1] for row in cursor.execute("PRAGMA table_info(memories)")}
        if "embedding" not in existing_columns:
            cursor.execute("ALTER TABLE memories ADD COLUMN embedding BLOB")
        conn.commit()


def _get_embedding(text: str) -> Optional[np.ndarray]:
    """Calcule le vecteur d'embedding d'un texte via le serveur local.

    Renvoie None (plutôt que de lever une exception) si le serveur ou le
    modèle d'embeddings n'est pas disponible, pour permettre un repli
    silencieux sur la recherche par mot-clé.
    """
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        response = client.embeddings.create(model=EMBEDDING_MODEL_NAME, input=cleaned)
        return np.array(response.data[0].embedding, dtype=np.float32)
    except Exception as e:
        print(f"⚠️ [Mémoire] Embeddings indisponibles ({e}). Repli sur la recherche par mot-clé.")
        return None


def _embedding_to_blob(vector: np.ndarray) -> bytes:
    return vector.astype(np.float32).tobytes()


def _blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return -1.0  # embeddings de dimensions différentes (ex: modèle changé) -> non comparables
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _backfill_missing_embeddings(conn: sqlite3.Connection) -> None:
    """Calcule l'embedding des souvenirs qui n'en ont pas encore (entrées créées
    avant cette fonctionnalité, ou pendant une panne du serveur d'embeddings)."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, key, value FROM memories WHERE embedding IS NULL LIMIT ?",
        (BACKFILL_BATCH_SIZE,),
    )
    rows = cursor.fetchall()
    if not rows:
        return

    for row_id, key, value in rows:
        vector = _get_embedding(f"{key} : {value}")
        if vector is None:
            break  # serveur d'embeddings indisponible, inutile d'insister sur les suivants
        cursor.execute(
            "UPDATE memories SET embedding = ? WHERE id = ?",
            (_embedding_to_blob(vector), row_id),
        )
    conn.commit()


def _keyword_search(conn: sqlite3.Connection, query: str) -> list[tuple[str, str, str]]:
    """Recherche historique par mot-clé (LIKE), utilisée en repli."""
    query_str = f"%{query.strip().lower()}%"
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT category, key, value FROM memories
        WHERE key LIKE ? OR value LIKE ? OR category LIKE ?
        """,
        (query_str, query_str, query_str),
    )
    return cursor.fetchall()


def _semantic_search(conn: sqlite3.Connection, query_embedding: np.ndarray) -> list[tuple[str, str, str, float]]:
    """Recherche par similarité cosinus sur les souvenirs disposant d'un embedding."""
    cursor = conn.cursor()
    cursor.execute("SELECT category, key, value, embedding FROM memories WHERE embedding IS NOT NULL")

    scored = []
    for category, key, value, blob in cursor.fetchall():
        similarity = _cosine_similarity(query_embedding, _blob_to_embedding(blob))
        if similarity >= SEMANTIC_MIN_SIMILARITY:
            scored.append((category, key, value, similarity))

    scored.sort(key=lambda row: row[3], reverse=True)
    return scored[:SEMANTIC_TOP_K]


def memory_control(action: str, key: str = "", value: str = "", category: str = "general") -> str:
    """Gère la mémoire persistante à long terme de Monika.

    Actions disponibles :
    - 'save'   : Enregistre une information (requiert 'key' et 'value').
    - 'search' : Recherche des informations par sens (sémantique, via 'key' comme requête),
                 avec repli automatique sur la recherche par mot-clé si les embeddings
                 sont indisponibles ou ne donnent aucun résultat pertinent.
    - 'list'   : Affiche l'ensemble des mémoires enregistrées.
    """
    _init_db()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "save":
                if not key or not value:
                    return "Erreur : 'key' et 'value' sont requis pour enregistrer une information."

                clean_key = key.strip().lower()
                clean_value = value.strip()
                vector = _get_embedding(f"{clean_key} : {clean_value}")
                embedding_blob = _embedding_to_blob(vector) if vector is not None else None

                cursor.execute("""
                    INSERT INTO memories (category, key, value, embedding)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value, category=excluded.category, embedding=excluded.embedding
                """, (category, clean_key, clean_value, embedding_blob))
                conn.commit()
                return f"🧠 Mémoire enregistrée avec succès : [{key}] = {value}"

            elif action == "search":
                if not key.strip():
                    return "Erreur : 'key' est requis pour préciser ce que l'on recherche."

                _backfill_missing_embeddings(conn)

                query_embedding = _get_embedding(key)
                if query_embedding is not None:
                    semantic_results = _semantic_search(conn, query_embedding)
                    if semantic_results:
                        lines = [f"• [{cat}] {k} : {v}  (pertinence {sim:.0%})" for cat, k, v, sim in semantic_results]
                        return "🔎 Résultats de la recherche sémantique :\n" + "\n".join(lines)

                # Repli : pas d'embeddings disponibles, ou aucun résultat assez pertinent.
                keyword_results = _keyword_search(conn, key)
                if not keyword_results:
                    return f"Aucune mémoire trouvée pour '{key}'."

                lines = [f"• [{cat}] {k} : {v}" for cat, k, v in keyword_results]
                return "🔍 Résultats de la recherche par mot-clé :\n" + "\n".join(lines)

            elif action == "list":
                cursor.execute("SELECT category, key, value FROM memories ORDER BY category")
                rows = cursor.fetchall()

                if not rows:
                    return "La mémoire de Monika est actuellement vide."

                results = [f"• [{cat}] {k} : {v}" for cat, k, v in rows]
                return "Contenu complet de la mémoire :\n" + "\n".join(results)

            return "Action non reconnue pour l'outil memory_control."

    except Exception as e:
        return f"Erreur lors de l'accès à la mémoire : {str(e)}"
