"""Recherche hybride (dense + BM25, fusion RRF) puis reranking par cross-encoder."""

from dataclasses import dataclass
from typing import Optional

from core.settings import settings
from rag import sparse
from rag.models import get_embedder, get_reranker
from rag.store import get_store


@dataclass
class Hit:
    path: str
    location: str
    header: str
    text: str
    rerank_score: Optional[float]  # None si le reranker est désactivé ou indisponible


def search(query: str, top_k: Optional[int] = None, path_prefix: Optional[str] = None) -> tuple[list[Hit], dict]:
    """Renvoie (résultats, infos). infos : candidates, reranked, filtered_out."""
    top_k = top_k or settings.RAG_TOP_K
    dense = get_embedder().embed_query(query)
    points = get_store().search(dense, sparse.encode_query(query), settings.RAG_CANDIDATES, path_prefix)
    info = {"candidates": len(points), "reranked": False, "filtered_out": 0}
    if not points:
        return [], info

    hits = [
        Hit(
            path=p.payload["path"], location=p.payload.get("location", ""),
            header=p.payload.get("header", p.payload["path"]), text=p.payload.get("text", ""),
            rerank_score=None,
        )
        for p in points
    ]

    if settings.RAG_RERANK_ENABLED and len(hits) > 1:
        scores = get_reranker().score(query, [f"{h.header}\n{h.text}" for h in hits])
        if scores is not None:
            info["reranked"] = True
            for hit, score in zip(hits, scores):
                hit.rerank_score = score
            hits.sort(key=lambda h: h.rerank_score, reverse=True)
            kept = [h for h in hits if h.rerank_score >= settings.RAG_RERANK_MIN_SCORE]
            info["filtered_out"] = len(hits) - len(kept)
            hits = kept

    # Diversité : au plus N extraits par fichier, pour ne pas laisser un seul document occuper tout le résultat.
    per_file: dict[str, int] = {}
    final: list[Hit] = []
    for hit in hits:
        if per_file.get(hit.path, 0) >= settings.RAG_MAX_PER_FILE:
            continue
        per_file[hit.path] = per_file.get(hit.path, 0) + 1
        final.append(hit)
        if len(final) >= top_k:
            break
    return final, info
