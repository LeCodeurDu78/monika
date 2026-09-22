"""Recherche vectorielle générique par table SQLite (embeddings + repli par mot-clé)."""

import sqlite3
from typing import Callable, Optional, Sequence

import numpy as np

from tools.knowledge.memory_tools import (
    embed_texts,
    embedding_dimension,
    embedding_to_blob,
    blob_to_embedding,
    cosine_similarity,
)

DEFAULT_BACKFILL_BATCH_SIZE = 25


def backfill_missing_embeddings(
    conn: sqlite3.Connection,
    *,
    table: str,
    id_column: str,
    text_columns: Sequence[str],
    text_for_embedding: Callable[[tuple], str],
    batch_size: int = DEFAULT_BACKFILL_BATCH_SIZE,
) -> None:
    """Vectorise par lots les lignes de `table` sans embedding, et revectorise celles dont la
    dimension stockée ne correspond plus au modèle actuel (ex: changement de backend
    d'embedding). `text_for_embedding` reçoit chaque ligne brute (id_column + text_columns,
    dans cet ordre) et renvoie le texte à vectoriser."""
    cursor = conn.cursor()
    current_dim = embedding_dimension()
    columns_sql = ", ".join([id_column, *text_columns])

    if current_dim is not None:
        cursor.execute(
            f"SELECT {columns_sql} FROM {table} WHERE embedding IS NULL OR length(embedding) != ? LIMIT ?",
            (current_dim * 4, batch_size),
        )
    else:
        cursor.execute(
            f"SELECT {columns_sql} FROM {table} WHERE embedding IS NULL LIMIT ?",
            (batch_size,),
        )

    rows = cursor.fetchall()
    if not rows:
        return

    texts = [text_for_embedding(row) for row in rows]
    vectors = embed_texts(texts)
    if vectors is None:
        return

    for row, vector in zip(rows, vectors):
        row_id = row[0]
        cursor.execute(
            f"UPDATE {table} SET embedding = ? WHERE {id_column} = ?",
            (embedding_to_blob(vector), row_id),
        )
    conn.commit()


def keyword_search(
    conn: sqlite3.Connection,
    *,
    table: str,
    query: str,
    select_columns: Sequence[str],
    like_columns: Sequence[str],
    limit: Optional[int] = None,
) -> list[tuple]:
    """Recherche par mot-clé (LIKE), utilisée en repli quand la recherche sémantique échoue ou
    qu'aucun embedding n'est encore disponible."""
    query_str = f"%{query.strip().lower()}%"
    cursor = conn.cursor()
    where_sql = " OR ".join(f"{col} LIKE ?" for col in like_columns)
    limit_sql = " LIMIT ?" if limit else ""
    params = [query_str] * len(like_columns) + ([limit] if limit else [])
    cursor.execute(
        f"SELECT {', '.join(select_columns)} FROM {table} WHERE {where_sql}{limit_sql}",
        params,
    )
    return cursor.fetchall()


def semantic_search(
    conn: sqlite3.Connection,
    query_embedding: np.ndarray,
    *,
    table: str,
    select_columns: Sequence[str],
    min_similarity: float,
    top_k: int,
) -> list[tuple]:
    """Recherche par similarité cosinus sur les lignes de `table` disposant d'un embedding.
    Chaque tuple renvoyé est (colonnes de `select_columns`..., score de similarité), trié par
    score décroissant et limité à `top_k` résultats."""
    cursor = conn.cursor()
    cursor.execute(
        f"SELECT {', '.join(select_columns)}, embedding FROM {table} WHERE embedding IS NOT NULL"
    )

    scored = []
    for row in cursor.fetchall():
        *content, blob = row
        similarity = cosine_similarity(query_embedding, blob_to_embedding(blob))
        if similarity >= min_similarity:
            scored.append((*content, similarity))

    scored.sort(key=lambda row: row[-1], reverse=True)
    return scored[:top_k]