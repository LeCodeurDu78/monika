"""RAG (Retrieval-Augmented Generation) sur les documents personnels de l'utilisateur."""

import os
import sqlite3
from typing import Optional

import numpy as np

from tools.memory import (
    embed_text,
    embed_texts,
    embedding_dimension,
    embedding_to_blob,
    blob_to_embedding,
    cosine_similarity,
)
from config import APP_DIR

DB_PATH = str(APP_DIR / "rag.db")


TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".py", ".log"}
PDF_EXTENSIONS = {".pdf"}
DOCX_EXTENSIONS = {".docx"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS | DOCX_EXTENSIONS


CHUNK_SIZE = 900
CHUNK_OVERLAP = 150


RAG_TOP_K = 5
RAG_MIN_SIMILARITY = 0.35


BACKFILL_BATCH_SIZE = 25

_IGNORED_DIR_NAMES = {"__pycache__", ".git", "node_modules", ".venv", "venv"}


def _init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rag_chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                embedding BLOB,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_rag_source ON rag_chunks(source)")
        conn.commit()


def _backfill_missing_embeddings(conn: sqlite3.Connection) -> None:
    """Vectorise les chunks sans embedding, et revectorise ceux dont la dimension stockée ne correspond plus au modèle actuel."""
    cursor = conn.cursor()
    current_dim = embedding_dimension()

    if current_dim is not None:
        cursor.execute(
            "SELECT id, content FROM rag_chunks WHERE embedding IS NULL OR length(embedding) != ? LIMIT ?",
            (current_dim * 4, BACKFILL_BATCH_SIZE),
        )
    else:
        cursor.execute(
            "SELECT id, content FROM rag_chunks WHERE embedding IS NULL LIMIT ?",
            (BACKFILL_BATCH_SIZE,),
        )

    rows = cursor.fetchall()
    if not rows:
        return

    for row_id, content in rows:
        vector = embed_text(content)
        if vector is None:
            break
        cursor.execute(
            "UPDATE rag_chunks SET embedding = ? WHERE id = ?", (embedding_to_blob(vector), row_id)
        )
    conn.commit()


def _extract_text(file_path: str) -> tuple[Optional[str], Optional[str]]:
    """Extrait le texte brut d'un fichier."""
    ext = os.path.splitext(file_path)[1].lower()

    if ext in TEXT_EXTENSIONS:
        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read(), None
        except Exception as e:
            return None, f"Impossible de lire '{file_path}' : {e}"

    if ext in PDF_EXTENSIONS:
        try:
            from pypdf import PdfReader
        except ImportError:
            return (
                None,
                "Le module 'pypdf' n'est pas installé (pip install pypdf) : impossible de lire les PDF.",
            )
        try:
            reader = PdfReader(file_path)
            pages_text = [page.extract_text() or "" for page in reader.pages]
            return "\n\n".join(pages_text), None
        except Exception as e:
            return None, f"Impossible de lire le PDF '{file_path}' : {e}"

    if ext in DOCX_EXTENSIONS:
        try:
            import docx
        except ImportError:
            return (
                None,
                "Le module 'python-docx' n'est pas installé (pip install python-docx) : impossible de lire les .docx.",
            )
        try:
            document = docx.Document(file_path)
            return "\n".join(p.text for p in document.paragraphs), None
        except Exception as e:
            return None, f"Impossible de lire le document '{file_path}' : {e}"

    return (
        None,
        f"Format non pris en charge : '{ext}' (formats acceptés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}).",
    )


def _iter_supported_files(path: str):
    """Génère les chemins de fichiers indexables sous `path` (fichier unique ou dossier récursif)."""
    if os.path.isfile(path):
        if os.path.splitext(path)[1].lower() in SUPPORTED_EXTENSIONS:
            yield path
        return

    for root, dirs, files in os.walk(path):
        dirs[:] = [d for d in dirs if d not in _IGNORED_DIR_NAMES and not d.startswith(".")]
        for filename in files:
            if os.path.splitext(filename)[1].lower() in SUPPORTED_EXTENSIONS:
                yield os.path.join(root, filename)


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Découpe un texte en morceaux d'environ `chunk_size` caractères, en coupant sur un espace plutôt qu'en plein milieu d'un mot."""
    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0
    length = len(text)

    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            last_space = text.rfind(" ", start + int(chunk_size * 0.5), end)
            if last_space != -1:
                end = last_space

        piece = text[start:end].strip()
        if piece:
            chunks.append(piece)

        if end >= length:
            break

        next_start = end - overlap
        start = next_start if next_start > start else end

    return chunks


def _keyword_search(conn: sqlite3.Connection, query: str) -> list[tuple[str, int, str]]:
    query_str = f"%{query.strip().lower()}%"
    cursor = conn.cursor()
    cursor.execute(
        "SELECT source, chunk_index, content FROM rag_chunks WHERE content LIKE ? LIMIT ?",
        (query_str, RAG_TOP_K),
    )
    return cursor.fetchall()


def _semantic_search(
    conn: sqlite3.Connection, query_embedding: np.ndarray
) -> list[tuple[str, int, str, float]]:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT source, chunk_index, content, embedding FROM rag_chunks WHERE embedding IS NOT NULL"
    )

    scored = []
    for source, chunk_index, content, blob in cursor.fetchall():
        similarity = cosine_similarity(query_embedding, blob_to_embedding(blob))
        if similarity >= RAG_MIN_SIMILARITY:
            scored.append((source, chunk_index, content, similarity))

    scored.sort(key=lambda row: row[3], reverse=True)
    return scored[:RAG_TOP_K]


def rag_control(action: str, path: str = "", query: str = "", doc_name: str = "") -> str:
    """Gère la base de connaissances RAG sur les documents personnels de l'utilisateur."""
    _init_db()

    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()

            if action == "ingest":
                if not path:
                    return "Erreur : 'path' est requis pour indexer un fichier ou un dossier."

                expanded_path = os.path.expanduser(path)
                if not os.path.exists(expanded_path):
                    return f"Erreur : le chemin '{expanded_path}' n'existe pas."

                files = list(_iter_supported_files(expanded_path))
                if not files:
                    return (
                        f"Aucun fichier indexable trouvé sous '{expanded_path}'. "
                        f"Formats acceptés : {', '.join(sorted(SUPPORTED_EXTENSIONS))}."
                    )

                indexed, skipped, total_chunks = [], [], 0
                for file_path in files:
                    text, error = _extract_text(file_path)
                    if error:
                        skipped.append(f"{file_path} ({error})")
                        continue

                    chunks = _chunk_text(text)
                    if not chunks:
                        skipped.append(f"{file_path} (aucun texte extractible)")
                        continue

                    cursor.execute("DELETE FROM rag_chunks WHERE source = ?", (file_path,))

                    vectors = embed_texts(chunks)

                    for i, chunk in enumerate(chunks):
                        if vectors is not None and i < len(vectors):
                            embedding_blob = embedding_to_blob(np.asarray(vectors[i], dtype=np.float32))
                        else:
                            embedding_blob = None
                        cursor.execute(
                            "INSERT INTO rag_chunks (source, chunk_index, content, embedding) VALUES (?, ?, ?, ?)",
                            (file_path, i, chunk, embedding_blob),
                        )

                    conn.commit()
                    indexed.append(f"{file_path} ({len(chunks)} chunks)")
                    total_chunks += len(chunks)

                summary = (
                    f"📚 Indexation terminée : {len(indexed)} document(s), {total_chunks} chunks au total."
                )
                if indexed:
                    summary += "\n✅ Indexés :\n" + "\n".join(f"  • {i}" for i in indexed)
                if skipped:
                    summary += "\n⚠️ Ignorés :\n" + "\n".join(f"  • {s}" for s in skipped)
                return summary

            elif action == "search":
                if not query.strip():
                    return "Erreur : 'query' est requis pour interroger les documents."

                _backfill_missing_embeddings(conn)

                query_embedding = embed_text(query)
                if query_embedding is not None:
                    semantic_results = _semantic_search(conn, query_embedding)
                    if semantic_results:
                        lines = [
                            f"• [{os.path.basename(src)} — chunk {idx}] (pertinence {sim:.0%})\n{content}"
                            for src, idx, content, sim in semantic_results
                        ]
                        return "🔎 Passages pertinents trouvés dans tes documents :\n\n" + "\n\n".join(lines)

                keyword_results = _keyword_search(conn, query)
                if not keyword_results:
                    return f"Aucun passage pertinent trouvé pour '{query}' dans les documents indexés."

                lines = [
                    f"• [{os.path.basename(src)} — chunk {idx}]\n{content}"
                    for src, idx, content in keyword_results
                ]
                return "🔍 Passages trouvés par mot-clé :\n\n" + "\n\n".join(lines)

            elif action == "list":
                cursor.execute("SELECT source, COUNT(*) FROM rag_chunks GROUP BY source ORDER BY source")
                rows = cursor.fetchall()
                if not rows:
                    return "Aucun document indexé pour l'instant. Utilise l'action 'ingest' pour en ajouter."

                lines = [f"• {source} ({count} chunks)" for source, count in rows]
                return f"📚 {len(rows)} document(s) indexé(s) :\n" + "\n".join(lines)

            elif action == "delete":
                if not doc_name:
                    return "Erreur : 'doc_name' est requis pour supprimer un document (voir action='list')."

                cursor.execute("SELECT COUNT(*) FROM rag_chunks WHERE source = ?", (doc_name,))
                count = cursor.fetchone()[0]
                if count == 0:
                    return f"Aucun document indexé ne correspond à '{doc_name}'. Vérifie le chemin exact avec l'action 'list'."

                cursor.execute("DELETE FROM rag_chunks WHERE source = ?", (doc_name,))
                conn.commit()
                return f"🗑️ Document '{doc_name}' retiré de l'index ({count} chunks supprimés)."

            return "Action non reconnue pour l'outil rag_control."

    except Exception as e:
        return f"Erreur lors de l'accès à la base RAG : {str(e)}"
