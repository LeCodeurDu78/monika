"""Mémoire persistante long terme pour Monika."""

import json
import re
import sqlite3
import threading
from datetime import date
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


# --- Faits atomiques tracés (à côté du stockage par embedding) -----------------------------

FACT_STATUS_ACTIVE = "actif"
FACT_STATUS_CONTRADICTED = "contredit"
FACT_STATUS_TO_REVIEW = "à revoir"

FACT_EXTRACTION_SYSTEM_PROMPT = (
    "Tu extrais UN SEUL fait atomique clair et durable d'un texte, pour la mémoire factuelle "
    "tracée de Monika (ex: préférence, information personnelle, statut d'un projet). Réponds "
    "UNIQUEMENT avec un objet JSON valide, sans texte avant/après, sans balise markdown/```.\n\n"
    "Format exact attendu :\n"
    '{"has_fact": false, "subject": "", "value": "", "fact_date": null, "confidence": "haute"}\n\n'
    "Règles :\n"
    "1. 'has_fact' : true seulement si un fait clair, factuel et durable est présent (pas une "
    "question, pas une opinion vague, pas du bavardage).\n"
    "2. 'subject' : sujet court et normalisé du fait (ex: 'ville', 'anniversaire', 'projet X - statut').\n"
    "3. 'value' : la valeur exacte du fait (ex: 'Paris', '12 mars', 'en pause').\n"
    "4. 'fact_date' : date ISO ('YYYY-MM-DD') si le texte mentionne une date précise pour ce fait, "
    "sinon null (la date du jour sera utilisée par défaut).\n"
    "5. 'confidence' : 'haute' si le fait est explicite et sans ambiguïté, 'faible' si incertain "
    "(le fait sera alors marqué 'à revoir' plutôt qu'actif).\n"
    "6. N'invente rien : si aucun fait clair n'est présent, réponds avec has_fact=false."
)


def _init_facts_db() -> None:
    """Crée les tables de faits atomiques tracés (dans la même base memory.db)."""
    with get_connection(DB_PATH) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                value TEXT NOT NULL,
                fact_date TEXT,
                status TEXT NOT NULL DEFAULT 'actif',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_facts_subject ON facts(subject COLLATE NOCASE);
            CREATE TABLE IF NOT EXISTS fact_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact_id INTEGER NOT NULL REFERENCES facts(id),
                observed_text TEXT,
                observed_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
    return text.strip()


def _extract_atomic_fact(source_text: str) -> Optional[dict]:
    """Appelle le LLM pour extraire {subject, value, fact_date, confidence} du texte, ou None
    si aucun fait clair n'est présent."""
    from config import client, MODEL_NAME

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": FACT_EXTRACTION_SYSTEM_PROMPT},
                {"role": "user", "content": source_text[:2000]},
            ],
        )
        raw = _strip_code_fences(response.choices[0].message.content or "")
        data = json.loads(raw)
        if not data.get("has_fact"):
            return None

        subject = str(data.get("subject", "")).strip()
        value = str(data.get("value", "")).strip()
        if not subject or not value:
            return None

        raw_date = data.get("fact_date")
        return {
            "subject": subject,
            "value": value,
            "fact_date": str(raw_date).strip() if raw_date else None,
            "confidence": str(data.get("confidence", "haute")).strip().lower(),
        }
    except Exception:
        return None


def _find_active_fact(cursor: sqlite3.Cursor, subject: str) -> Optional[tuple]:
    cursor.execute(
        "SELECT id, value FROM facts WHERE subject = ? COLLATE NOCASE AND status = ?",
        (subject, FACT_STATUS_ACTIVE),
    )
    return cursor.fetchone()


def record_atomic_fact(source_text: str) -> Optional[str]:
    """Extrait un fait atomique de `source_text` (s'il y en a un) et le trace : renforcement
    (fact_observations) si un fait identique est déjà 'actif' pour ce sujet, contradiction si la
    valeur a changé (l'ancien fait passe à 'contredit', le nouveau devient 'actif'/'à revoir'),
    sinon nouveau fait. Renvoie une courte note (ou None si rien d'extrait, ou si rien de nouveau
    à signaler lors d'un simple renforcement)."""
    extracted = _extract_atomic_fact(source_text)
    if extracted is None:
        return None

    _init_facts_db()
    subject, value, fact_date, confidence = (
        extracted["subject"], extracted["value"], extracted["fact_date"], extracted["confidence"]
    )
    fact_date = fact_date or date.today().isoformat()
    status = FACT_STATUS_ACTIVE if confidence != "faible" else FACT_STATUS_TO_REVIEW

    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        existing = _find_active_fact(cursor, subject)

        if existing is None:
            cursor.execute(
                "INSERT INTO facts (subject, value, fact_date, status) VALUES (?, ?, ?, ?)",
                (subject, value, fact_date, status),
            )
            conn.commit()
            return f"🧩 Nouveau fait tracé : [{subject}] = {value} ({status})"

        existing_id, existing_value = existing
        if existing_value.strip().lower() == value.strip().lower():
            cursor.execute(
                "INSERT INTO fact_observations (fact_id, observed_text) VALUES (?, ?)",
                (existing_id, source_text[:500]),
            )
            cursor.execute("UPDATE facts SET updated_at = CURRENT_TIMESTAMP WHERE id = ?", (existing_id,))
            conn.commit()
            return None

        cursor.execute(
            "UPDATE facts SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (FACT_STATUS_CONTRADICTED, existing_id),
        )
        cursor.execute(
            "INSERT INTO facts (subject, value, fact_date, status) VALUES (?, ?, ?, ?)",
            (subject, value, fact_date, status),
        )
        conn.commit()
        return f"⚠️ Fait contredit sur [{subject}] : « {existing_value} » → « {value} »"


def facts_needing_review() -> str:
    """Liste les faits marqués 'contredit' ou 'à revoir' — utilisé par le curator nocturne
    (tools/system/curator.py) et pour l'inspection humaine."""
    _init_facts_db()
    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT subject, value, status, updated_at FROM facts WHERE status IN (?, ?) "
            "ORDER BY updated_at DESC",
            (FACT_STATUS_CONTRADICTED, FACT_STATUS_TO_REVIEW),
        )
        rows = cursor.fetchall()

    if not rows:
        return ""
    return "\n".join(
        f"• [{status}] {subject} = {value} (maj {updated_at})"
        for subject, value, status, updated_at in rows
    )


# --- Export Markdown en lecture seule (miroir humain de la mémoire) -------------------------
#
# Génère un fichier .md par catégorie (ex: preferences.md si la catégorie 'preference' est
# utilisée, projets.md si 'projet' l'est) — sur le modèle de graph_backfill (tools/knowledge/
# graph_tools.py) : régénérable à la demande, et rappelé périodiquement par le curator nocturne.

def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_")
    return slug or "general"


def export_memory_markdown() -> str:
    """Génère un miroir Markdown en lecture seule de la mémoire long terme, un fichier par
    catégorie, dans <APP_DIR>/memory_export/."""
    _init_db()
    export_dir = settings.APP_DIR / "memory_export"
    export_dir.mkdir(parents=True, exist_ok=True)

    with get_connection(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT category, key, value FROM memories ORDER BY category, key")
        rows = cursor.fetchall()

    by_category: dict[str, list[tuple[str, str]]] = {}
    for category, key, value in rows:
        by_category.setdefault(category or "general", []).append((key, value))

    written = []
    for category, entries in by_category.items():
        filename = _slugify(category) + ".md"
        lines = [f"# Mémoire — {category}", "", "_Généré automatiquement, lecture seule._", ""]
        lines += [f"- **{key}** : {value}" for key, value in entries]
        (export_dir / filename).write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(filename)

    if not written:
        return "Aucune mémoire à exporter."
    return f"📄 Export Markdown généré ({len(written)} fichier(s)) dans {export_dir} : {', '.join(written)}"


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

                try:
                    record_atomic_fact(f"{clean_key} : {clean_value}")
                except Exception as e:
                    print(f"⚠️ [memory] Échec du traçage de fait atomique : {e}")

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