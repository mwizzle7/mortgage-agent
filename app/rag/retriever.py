from __future__ import annotations

import os
import sqlite3
from typing import Any, Dict, List, Optional

import faiss
import numpy as np

from app.core.config import settings
from app.rag.embeddings import embed_texts


MAX_EXCERPTS_PER_SOURCE = 3


def _normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if norm == 0:
        return vec
    return vec / norm


def _fetch_chunk_metadata(cur: sqlite3.Cursor, embedding_index: int) -> Optional[Dict[str, Any]]:
    cur.execute(
        """
        SELECT c.chunk_id, c.text, c.doc_id, d.title, d.jurisdiction, d.source_url, d.source_name
        FROM chunks c
        JOIN documents d ON c.doc_id = d.doc_id
        WHERE c.embedding_index = ?
        """,
        (embedding_index,),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "chunk_id": row[0],
        "text": row[1],
        "doc_id": row[2],
        "title": row[3],
        "jurisdiction": row[4] or "",
        "source_url": row[5],
        "source_name": row[6],
    }


def _empty_result() -> Dict[str, Any]:
    return {"sources": [], "chunks_retrieved": 0, "sources_deduped": 0}


def retrieve(query: str, top_k: Optional[int] = None) -> Dict[str, Any]:
    cleaned = (query or "").strip()
    if not cleaned:
        return _empty_result()

    index_path = settings.vector_index_path
    if not os.path.exists(index_path):
        return _empty_result()

    top_k = top_k or settings.top_k
    if top_k <= 0:
        return _empty_result()

    embeddings = embed_texts([cleaned])
    if not embeddings:
        return _empty_result()

    query_vec = np.asarray(embeddings[0], dtype="float32")
    query_vec = _normalize(query_vec)

    index = faiss.read_index(index_path)
    scores, indices = index.search(query_vec.reshape(1, -1), top_k)

    conn = sqlite3.connect(settings.log_db_path)
    cur = conn.cursor()

    chunk_hits: List[Dict[str, Any]] = []
    for score, idx in zip(scores[0], indices[0]):
        if idx < 0:
            continue
        meta = _fetch_chunk_metadata(cur, int(idx))
        if not meta:
            continue
        chunk_hits.append(
            {
                "chunk_id": meta["chunk_id"],
                "doc_id": meta["doc_id"],
                "score": float(score),
                "title": meta["title"],
                "jurisdiction": meta["jurisdiction"],
                "text": meta["text"],
                "source_url": meta.get("source_url"),
                "source_name": meta.get("source_name"),
            }
        )

    conn.close()

    if not chunk_hits:
        return _empty_result()

    groups: Dict[str, Dict[str, Any]] = {}
    for rank, chunk in enumerate(chunk_hits):
        source_key = chunk["source_url"] or chunk["doc_id"]
        if source_key not in groups:
            groups[source_key] = {
                "source_url": chunk.get("source_url"),
                "doc_id": chunk["doc_id"],
                "title": chunk.get("title") or "Untitled Source",
                "jurisdiction": chunk.get("jurisdiction") or "",
                "source_name": chunk.get("source_name"),
                "chunks": [],
                "best_score": chunk["score"],
                "first_rank": rank,
            }
        group = groups[source_key]
        group["chunks"].append(chunk)
        if chunk["score"] > group["best_score"]:
            group["best_score"] = chunk["score"]

    sorted_groups = sorted(
        groups.values(),
        key=lambda g: (-g["best_score"], g["first_rank"]),
    )

    max_sources = settings.top_sources if settings.top_sources > 0 else 1
    sources: List[Dict[str, Any]] = []
    for idx, group in enumerate(sorted_groups[:max_sources], start=1):
        sorted_chunks = sorted(group["chunks"], key=lambda c: c["score"], reverse=True)
        excerpts = [
            {
                "chunk_id": chunk["chunk_id"],
                "score": chunk["score"],
                "text": chunk["text"],
            }
            for chunk in sorted_chunks[:MAX_EXCERPTS_PER_SOURCE]
        ]
        sources.append(
            {
                "source_id": f"S{idx}",
                "source_url": group["source_url"],
                "source_name": group.get("source_name"),
                "title": group["title"],
                "jurisdiction": group["jurisdiction"],
                "score": group["best_score"],
                "doc_id": group["doc_id"],
                "excerpts": excerpts,
            }
        )

    return {
        "sources": sources,
        "chunks_retrieved": len(chunk_hits),
        "sources_deduped": len(groups),
    }
