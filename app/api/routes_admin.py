from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.rag.ingest import ingest_txt_corpus
from app.core.security import verify_admin_token

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(verify_admin_token)])


@router.post("/ingest")
def run_ingest():
    try:
        result = ingest_txt_corpus()
    except Exception as exc:  # pragma: no cover - surfaced to client
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return result
