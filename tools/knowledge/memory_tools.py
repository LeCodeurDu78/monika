"""Mémoire persistante long terme pour Monika."""

import sqlite3
import threading
from typing import Optional, Sequence
from sentence_transformers import SentenceTransformer

import numpy as np

from core.settings import settings

LOCAL_EMBEDDING_MODEL_NAME = settings.LOCAL_EMBEDDING_MODEL_NAME
LOCAL_EMBEDDING_DEVICE = settings.LOCAL_EMBEDDING_DEVICE
from core.db import db_path, get_connection

DB_PATH = db_path("memory.db")


SEMANTIC_TOP_K = 5
SEMANTIC_MIN_SIMILARITY = 0.35


BACKFILL_BATCH_SIZE = 25


_model = None
_model_lock = threading.Lock()
_load_failed = False


def resolve_device() -> str:
    """Device utilisé pour l'inférence."""
    if LOCAL_EMBEDDING_DEVICE:
        return LOCAL_EMBEDDING_DEVICE
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


def _get_model_dimension(model) -> int:
    """Dimension des embeddings."""
    if hasattr(model, "get_embedding_dimension"):
        return model.get_embedding_dimension()
    return model.get_sentence_embedding_dimension()


def _load_model():
    """Charge et met en cache le modèle."""
    global _model, _load_failed

    if _model is not None or _load_failed:
        return _model

    with _model_lock:
        if _model is not None or _load_failed:
            return _model

        device = resolve_device()
        try:
            print(
                f"⏳ [Embeddings locaux] Chargement de '{LOCAL_EMBEDDING_MODEL_NAME}' sur '{device}' (une seule fois, peut être long au premier lancement)..."
            )
            _model = SentenceTransformer(LOCAL_EMBEDDING_MODEL_NAME, device=device)
            print(f"✅ [Embeddings locaux] Modèle chargé (dimension {_get_model_dimension(_model)}).")
        except Exception as e:
            print(f"⚠️ [Embeddings locaux] Impossible de charger '{LOCAL_EMBEDDING_MODEL_NAME}' : {e}")
            _load_failed = True
            return None

    return _model


def embedding_dimension() -> Optional[int]:
    """Dimension des vecteurs du modèle actuellement chargé."""
    model = _load_model()
    if model is None:
        return None
    return _get_model_dimension(model)


def embed_text(text: str) -> Optional[np.ndarray]:
    """Vectorise un texte unique."""
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
    """Vectorise plusieurs textes en un seul batch."""
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
    """Indique si le backend d'embeddings locaux est utilisable."""
    return _load_model() is not None


def warmup() -> bool:
    """Force le chargement immédiat du modèle."""
    return _load_model() is not None


def embedding_to_blob(vector: np.ndarray) -> bytes:
    return vector.astype(np.float32).tobytes()


def blob_to_embedding(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    if a.shape != b.shape:
        return -1.0
    denom = np.linalg.norm(a) * np.linalg.norm(b)
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _init_db() -> None:
    """Crée la table de mémoire si besoin."""
    with get_connection(DB_PATH) as conn:
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


def _backfill_missing_embeddings(conn: sqlite3.Connection) -> None:
    """Vectorise les souvenirs sans embedding, et revectorise ceux dont la dimension stockée ne correspond plus au modèle actuel (changement de backend)."""
    cursor = conn.cursor()
    current_dim = embedding_dimension()

    if current_dim is not None:

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

    texts = [f"{key} : {value}" for _row_id, key, value in rows]
    vectors = embed_texts(texts)
    if vectors is None:
        return

    for (row_id, _key, _value), vector in zip(rows, vectors):
        cursor.execute(
            "UPDATE memories SET embedding = ? WHERE id = ?",
            (embedding_to_blob(vector), row_id),
        )
    conn.commit()


def _keyword_search(conn: sqlite3.Connection, query: str) -> list[tuple[str, str, str]]:
    """Recherche par mot-clé (LIKE), utilisée en repli."""
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


def _semantic_search(
    conn: sqlite3.Connection, query_embedding: np.ndarray
) -> list[tuple[str, str, str, float]]:
    """Recherche par similarité cosinus sur les souvenirs disposant d'un embedding."""
    cursor = conn.cursor()
    cursor.execute("SELECT category, key, value, embedding FROM memories WHERE embedding IS NOT NULL")

    scored = []
    for category, key, value, blob in cursor.fetchall():
        similarity = cosine_similarity(query_embedding, blob_to_embedding(blob))
        if similarity >= SEMANTIC_MIN_SIMILARITY:
            scored.append((category, key, value, similarity))

    scored.sort(key=lambda row: row[3], reverse=True)
    return scored[:SEMANTIC_TOP_K]


def _init_proactive_actions_db() -> None:
    """Crée la table de journalisation des actions autonomes."""
    with get_connection(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS proactive_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reason TEXT NOT NULL,
                action_type TEXT NOT NULL,
                payload TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def log_proactive_action(reason: str, action_type: str, payload: str = "") -> None:
    """Enregistre une intervention autonome réalisée, pour permettre le dédoublonnage."""
    _init_proactive_actions_db()
    with get_connection(DB_PATH) as conn:
        conn.execute(
            "INSERT INTO proactive_actions (reason, action_type, payload) VALUES (?, ?, ?)",
            (reason.strip(), action_type.strip(), payload.strip()),
        )
        conn.commit()


def was_recently_notified(reason: str, cooldown_minutes: int) -> bool:
    """Indique si une raison très similaire a déjà donné lieu à une intervention autonome récammment."""
    _init_proactive_actions_db()

    reason_words = {w for w in reason.strip().lower().split() if len(w) > 3}
    if not reason_words:
        return False

    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT reason FROM proactive_actions "
            "WHERE created_at >= datetime('now', ?) ORDER BY created_at DESC LIMIT 50",
            (f"-{int(cooldown_minutes)} minutes",),
        )
        recent_reasons = [row[0] for row in cursor.fetchall()]

    for past_reason in recent_reasons:
        past_words = {w for w in past_reason.strip().lower().split() if len(w) > 3}
        if not past_words:
            continue
        overlap = len(reason_words & past_words) / max(len(reason_words | past_words), 1)
        if overlap >= 0.5:
            return True

    return False


def memory_control(
    action: str, key: str = "", value: str = "", category: str = "general", query: str = "", **kwargs
) -> str:
    """Gère la mémoire persistante à long terme de Monika."""
    if query and not key:
        key = query

    _init_db()

    try:
        with get_connection(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "save":
                if not key or not value:
                    return "Erreur : 'key' et 'value' sont requis pour enregistrer une information."

                clean_key = key.strip().lower()
                clean_value = value.strip()
                vector = embed_text(f"{clean_key} : {clean_value}")
                embedding_blob = embedding_to_blob(vector) if vector is not None else None

                cursor.execute(
                    """
                    INSERT INTO memories (category, key, value, embedding)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value=excluded.value, category=excluded.category, embedding=excluded.embedding
                """,
                    (category, clean_key, clean_value, embedding_blob),
                )
                conn.commit()
                return f"🧠 Mémoire enregistrée avec succès : [{key}] = {value}"

            elif action == "search":
                if not key.strip():
                    return "Erreur : 'key' (ou 'query') est requis pour préciser ce que l'on recherche."

                _backfill_missing_embeddings(conn)

                query_embedding = embed_text(key)
                if query_embedding is not None:
                    semantic_results = _semantic_search(conn, query_embedding)
                    if semantic_results:
                        lines = [
                            f"• [{cat}] {k} : {v}  (pertinence {sim:.0%})"
                            for cat, k, v, sim in semantic_results
                        ]
                        return "🔎 Résultats de la recherche sémantique :\n" + "\n".join(lines)

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