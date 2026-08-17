"""
tools/memory.py
----------------
Gestion de la mémoire persistante à long terme pour Monika (SQLite), et
backend d'embeddings 100% local basé sur BGE-M3 (BAAI/bge-m3) utilisé pour la
recherche sémantique.

--- Embeddings locaux (BGE-M3) ---
BGE-M3 est un modèle multilingue open-source qui tourne directement sur la
machine de l'utilisateur via `sentence-transformers` : plus besoin d'un
serveur distant (LM Studio, API cloud...) pour vectoriser du texte. Ce fichier
expose aussi les fonctions embed_text/embed_texts/embedding_dimension/warmup,
réutilisées par tools/utils/rag_tools.py pour le RAG.

Pourquoi BGE-M3 : multilingue (100+ langues, bon en français), pas besoin de
préfixe d'instruction spécial sur la requête, bonnes performances de
recherche sémantique pour une taille raisonnable (~560M paramètres, ~2.2 Go).

Chargement : le modèle est initialisé une seule fois (singleton protégé par
verrou) au premier appel (ou dès le démarrage de Monika via warmup(), voir
agent.py), puis réutilisé pour tous les appels suivants.

--- Mémoire (memory_control) ---
La recherche est sémantique : chaque information enregistrée est vectorisée
avec BGE-M3, et une recherche compare le sens de la requête aux souvenirs
stockés plutôt qu'un simple mot-clé exact. Exemple concret : chercher
"éditeur de code" retrouvera un souvenir enregistré sous la clé "outil_dev"
avec la valeur "VS Code", ce qu'un LIKE SQL ne pouvait pas faire.

Robustesse : si le modèle d'embeddings local n'est pas disponible (dépendance
manquante, échec de chargement...), les fonctions d'embedding renvoient None
et la mémoire retombe automatiquement sur une recherche par mot-clé (LIKE).

Migration automatique : si le modèle d'embeddings change (dimension de
vecteur différente), les entrées "périmées" sont détectées via leur taille en
octets et automatiquement revectorisées par le backfill, sans action requise.
"""

import os
import sqlite3
import threading
from typing import Optional, Sequence

import numpy as np

from config import LOCAL_EMBEDDING_MODEL_NAME, LOCAL_EMBEDDING_DEVICE

DB_PATH = os.path.expanduser("~/.config/monika/memory.db")

# Nombre max de résultats sémantiques renvoyés, et seuil de similarité
# cosinus en dessous duquel un résultat est jugé trop peu pertinent pour
# être montré (évite de renvoyer du bruit sur une base volumineuse).
SEMANTIC_TOP_K = 5
SEMANTIC_MIN_SIMILARITY = 0.35

# Nombre max de souvenirs "rattrapés" (backfill) en une seule recherche,
# pour les entrées enregistrées avant l'activation de cette fonctionnalité,
# pendant une panne du modèle d'embeddings, ou avec un ancien modèle dont
# la dimension de vecteur ne correspond plus au modèle actuel.
BACKFILL_BATCH_SIZE = 25


# ==========================================================================
# Embeddings locaux (BGE-M3) — voir aussi tools/utils/rag_tools.py qui
# importe embed_text / embed_texts / embedding_dimension depuis ce module.
# ==========================================================================

_model = None
_model_lock = threading.Lock()
_load_failed = False


def resolve_device() -> str:
    """Détermine le device qui sera utilisé pour l'inférence : valeur
    explicite de config.py/.env si fournie, sinon auto-détection (GPU CUDA
    si disponible, sinon CPU). Exposé publiquement pour diagnostic
    (voir scripts/setup_bge_m3.py)."""
    if LOCAL_EMBEDDING_DEVICE:
        return LOCAL_EMBEDDING_DEVICE
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _get_model_dimension(model) -> int:
    """Récupère la dimension des embeddings du modèle, compatible avec les
    anciennes et nouvelles versions de sentence-transformers (la méthode a
    été renommée get_sentence_embedding_dimension -> get_embedding_dimension)."""
    if hasattr(model, "get_embedding_dimension"):
        return model.get_embedding_dimension()
    return model.get_sentence_embedding_dimension()


def _load_model():
    """Charge et met en cache le modèle BGE-M3 (thread-safe, une seule fois)."""
    global _model, _load_failed

    if _model is not None or _load_failed:
        return _model

    with _model_lock:
        if _model is not None or _load_failed:  # revérifié après acquisition du verrou
            return _model

        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            print(
                "⚠️ [Embeddings locaux] Le module 'sentence-transformers' n'est pas installé.\n"
                "   -> pip install sentence-transformers torch\n"
                "   En attendant, Monika retombe sur la recherche par mot-clé."
            )
            _load_failed = True
            return None

        device = resolve_device()
        try:
            print(f"⏳ [Embeddings locaux] Chargement de '{LOCAL_EMBEDDING_MODEL_NAME}' sur '{device}' (une seule fois, peut être long au premier lancement)...")
            _model = SentenceTransformer(LOCAL_EMBEDDING_MODEL_NAME, device=device)
            print(f"✅ [Embeddings locaux] Modèle chargé (dimension {_get_model_dimension(_model)}).")
        except Exception as e:
            print(f"⚠️ [Embeddings locaux] Impossible de charger '{LOCAL_EMBEDDING_MODEL_NAME}' : {e}")
            _load_failed = True
            return None

    return _model


def embedding_dimension() -> Optional[int]:
    """Dimension des vecteurs produits par le modèle actuellement chargé, ou
    None si le modèle est indisponible."""
    model = _load_model()
    if model is None:
        return None
    return _get_model_dimension(model)


def embed_text(text: str) -> Optional[np.ndarray]:
    """Vectorise un texte unique. Renvoie None si le modèle est indisponible."""
    cleaned = text.strip()
    if not cleaned:
        return None

    model = _load_model()
    if model is None:
        return None

    try:
        vector = model.encode(cleaned, normalize_embeddings=True)
        return np.asarray(vector, dtype=np.float32)
    except Exception as e:
        print(f"⚠️ [Embeddings locaux] Échec de vectorisation : {e}")
        return None


def embed_texts(texts: Sequence[str]) -> Optional[np.ndarray]:
    """Vectorise plusieurs textes en un seul batch (bien plus rapide que
    d'appeler embed_text() en boucle lors d'une indexation massive de
    documents). Renvoie un tableau (n, dim), ou None si le modèle est
    indisponible. Les entrées vides sont silencieusement ignorées."""
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return np.empty((0,), dtype=np.float32)

    model = _load_model()
    if model is None:
        return None

    try:
        vectors = model.encode(cleaned, normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        return np.asarray(vectors, dtype=np.float32)
    except Exception as e:
        print(f"⚠️ [Embeddings locaux] Échec de vectorisation par lot : {e}")
        return None


def is_available() -> bool:
    """Indique si le backend d'embeddings locaux est utilisable (déjà chargé,
    ou chargeable). Utile pour afficher un statut sans déclencher un
    chargement inutile si on veut juste vérifier."""
    return _load_model() is not None


def warmup() -> bool:
    """Force le chargement du modèle immédiatement (au lieu d'attendre le
    premier appel à memory_control/rag_control). Utilisé au démarrage de
    Monika (voir agent.py) pour que le modèle soit déjà prêt en mémoire/VRAM
    avant la première question de l'utilisateur, plutôt que de le charger
    "à la volée" et faire attendre la première recherche sémantique.
    Renvoie True si le chargement a réussi, False sinon (dépendance
    manquante, échec de chargement...)."""
    return _load_model() is not None


# ==========================================================================
# Mémoire persistante (memory_control)
# ==========================================================================

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
    """Calcule le vecteur d'embedding d'un texte avec le modèle local BGE-M3.

    Renvoie None (plutôt que de lever une exception) si le modèle local n'est
    pas disponible, pour permettre un repli silencieux sur la recherche par
    mot-clé.
    """
    return embed_text(text)


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
    avant cette fonctionnalité, pendant une panne du modèle d'embeddings), et
    revectorise aussi celles dont le vecteur stocké a une dimension différente
    du modèle actuel (par ex. après un changement de backend d'embeddings)."""
    cursor = conn.cursor()
    current_dim = embedding_dimension()

    if current_dim is not None:
        # length(embedding) est en octets ; un float32 = 4 octets.
        cursor.execute(
            "SELECT id, key, value FROM memories WHERE embedding IS NULL OR length(embedding) != ? LIMIT ?",
            (current_dim * 4, BACKFILL_BATCH_SIZE),
        )
    else:
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
            break  # modèle d'embeddings indisponible, inutile d'insister sur les suivants
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


def memory_control(action: str, key: str = "", value: str = "", category: str = "general", query: str = "", **kwargs) -> str:
    """Gère la mémoire persistante à long terme de Monika.

    Actions disponibles :
    - 'save'   : Enregistre une information (requiert 'key' et 'value').
    - 'search' : Recherche des informations par sens (sémantique, via 'key' ou 'query' comme requête),
                 avec repli automatique sur la recherche par mot-clé si les embeddings
                 sont indisponibles ou ne donnent aucun résultat pertinent.
    - 'list'   : Affiche l'ensemble des mémoires enregistrées.
    """
    # Si le modèle passe 'query' au lieu de 'key' (ex: memory_control(action='search', query='...'))
    if query and not key:
        key = query

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
                    return "Erreur : 'key' (ou 'query') est requis pour préciser ce que l'on recherche."

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