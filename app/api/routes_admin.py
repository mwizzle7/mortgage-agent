from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.rag.ingest import ingest_txt_corpus
from app.core.security import verify_admin_token
from app.corpus.fetcher import fetch_sources, load_seed_packs
from app.observability.logger import log_event
from app.core.config import settings

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_token)])


@router.post("/ingest")
def run_ingest():
    try:
        result = ingest_txt_corpus()
    except Exception as exc:  # pragma: no cover - surfaced to client
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result


@router.post("/fetch_and_ingest")
def fetch_and_ingest(pack: Optional[str] = Query(default="all")):
    pack_filter = None if not pack or pack.strip().lower() == "all" else pack.strip()
    try:
        specs, packs_loaded = load_seed_packs(pack_filter)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    if not specs:
        raise HTTPException(status_code=400, detail="No URLs found in the requested seed pack(s).")

    written, failed = fetch_sources(specs)
    try:
        ingest_result = ingest_txt_corpus()
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    log_event(
        settings.log_db_path,
        "corpus_fetch_completed",
        request_id=None,
        session_id=None,
        user_id_hash=None,
        payload={
            "packs_loaded": packs_loaded,
            "urls_total": len(specs),
            "files_written": len(written),
            "failed_count": len(failed),
        },
    )

    return {
        "packs_loaded": packs_loaded,
        "urls_total": len(specs),
        "files_written": len(written),
        "failed_urls": failed,
        **ingest_result,
    }
