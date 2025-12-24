from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple

import faiss
import numpy as np

from app.core.config import settings
from app.observability.logger import init_db
from app.rag.chunking import chunk_text
from app.rag.embeddings import embed_texts


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_vectors(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vectors / norms


def _read_txt_files(path: Path) -> List[Path]:
    path.mkdir(parents=True, exist_ok=True)
    return sorted([p for p in path.glob("*.txt") if p.is_file()])


def _split_header_body(raw_text: str) -> Tuple[Dict[str, str], List[str]]:
    header_lines: List[str] = []
    body_lines: List[str] = []
    in_header = True

    for line in raw_text.splitlines():
        if in_header and line.strip() == "---":
            in_header = False
            continue
        if in_header:
            header_lines.append(line)
        else:
            body_lines.append(line)

    metadata: Dict[str, str] = {}
    for line in header_lines:
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key:
            metadata[key] = value
    return metadata, body_lines


def _derive_title(body_lines: List[str], fallback: str) -> str:
    for line in body_lines:
        stripped = line.strip()
        if not stripped:
            continue
        return stripped
    return fallback


def _build_doc_metadata(metadata: Dict[str, str], file_path: Path) -> Dict[str, str]:
    slug_title = file_path.stem.replace("_", " ").replace("-", " ").strip().title()
    retrieved_date = metadata.get("retrieved_date") or datetime.now().date().isoformat()
    return {
        "source_name": metadata.get("source_name") or "unknown",
        "source_url": metadata.get("source_url") or None,
        "source_domain": metadata.get("source_domain") or None,
        "jurisdiction": metadata.get("jurisdiction") or "",
        "retrieved_date": retrieved_date,
        "content_type": metadata.get("content_type") or "extracted",
        "page_title": metadata.get("page_title") or "",
        "title_fallback": slug_title or "Untitled Document",
    }


def ingest_txt_corpus() -> dict:
    init_db(settings.log_db_path)  # ensure tables exist

    raw_path = Path(settings.corpus_raw_path)
    files = _read_txt_files(raw_path)
    if not files:
        return {"docs": 0, "chunks": 0, "index_path": settings.vector_index_path}

    os.makedirs(os.path.dirname(settings.vector_index_path), exist_ok=True)

    conn = sqlite3.connect(settings.log_db_path)
    cur = conn.cursor()

    # Reset documents/chunks for fresh ingestion
    cur.execute("DELETE FROM chunks")
    cur.execute("DELETE FROM documents")
    conn.commit()

    chunk_texts: List[str] = []
    chunk_meta: List[dict] = []
    doc_count = 0

    for file_path in files:
        text = file_path.read_text(encoding="utf-8")
        metadata, body_lines = _split_header_body(text)
        doc_fields = _build_doc_metadata(metadata, file_path)
        body_text = "\n".join(body_lines).strip()

        doc_id = str(uuid.uuid4())
        title = doc_fields.get("page_title") or _derive_title(body_lines, doc_fields["title_fallback"])

        cur.execute(
            """
            INSERT INTO documents (doc_id, title, page_title, source_name, source_url, source_domain, jurisdiction, published_date, retrieved_date, corpus_version, content_type, is_approved)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                doc_id,
                title,
                doc_fields.get("page_title") or None,
                doc_fields["source_name"],
                doc_fields["source_url"],
                doc_fields.get("source_domain"),
                doc_fields["jurisdiction"],
                None,
                doc_fields["retrieved_date"],
                settings.corpus_version,
                doc_fields["content_type"],
                1,
            ),
        )

        if not body_text:
            doc_count += 1
            continue

        chunks = chunk_text(body_text)
        for idx, chunk in enumerate(chunks):
            chunk_id = f"{doc_id}_{idx}"
            chunk_texts.append(chunk)
            chunk_meta.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "chunk_index": idx,
                }
            )
        doc_count += 1

    conn.commit()

    if not chunk_texts:
        conn.close()
        if os.path.exists(settings.vector_index_path):
            os.remove(settings.vector_index_path)
        return {"docs": doc_count, "chunks": 0, "index_path": settings.vector_index_path}

    embeddings = embed_texts(chunk_texts)
    vectors = np.asarray(embeddings, dtype="float32")
    vectors = _normalize_vectors(vectors)
    dim = vectors.shape[1]

    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    faiss.write_index(index, settings.vector_index_path)

    for embedding_index, meta in enumerate(chunk_meta):
        cur.execute(
            """
            INSERT INTO chunks (chunk_id, doc_id, chunk_index, text, embedding_index)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                meta["chunk_id"],
                meta["doc_id"],
                meta["chunk_index"],
                chunk_texts[embedding_index],
                embedding_index,
            ),
        )

    conn.commit()
    conn.close()

    return {
        "docs": doc_count,
        "chunks": len(chunk_texts),
        "index_path": settings.vector_index_path,
    }
