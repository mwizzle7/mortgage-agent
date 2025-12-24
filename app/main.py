from __future__ import annotations

import os
import uuid

from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.routes_admin import router as admin_router
from app.api.routes_feedback import router as feedback_router
from app.core.config import settings
from app.core.grounding import enforce_grounding, extract_source_citations, filter_citations
from app.core.limits import check_and_increment, ensure_session, hash_user_id
from app.core.rate_limit import enforce_rate_limit
from app.core.prompts import SYSTEM_PROMPT, build_context
from app.llm.client import generate_chat_completion
from app.observability.logger import init_db, log_event
from app.rag.retriever import retrieve


app = FastAPI(title="Mortgage Agent", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501"],
    allow_origin_regex=r"https://.*\.streamlit\.app",
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Admin-Token"],
)
app.include_router(admin_router)
app.include_router(feedback_router)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # for MVP, any string is fine (email/uuid/etc.)


def _ensure_storage_paths() -> None:
    os.makedirs(os.path.dirname(settings.vector_index_path), exist_ok=True)
    os.makedirs(os.path.dirname(settings.log_db_path), exist_ok=True)
    os.makedirs(settings.corpus_raw_path, exist_ok=True)


@app.on_event("startup")
def startup():
    _ensure_storage_paths()
    init_db(settings.log_db_path)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "env": settings.app_env,
        "port": settings.port,
        "strict_grounding": settings.strict_grounding,
        "citations_required": settings.citations_required,
        "char_limit": settings.char_limit,
        "q_limit_day": settings.q_limit_day,
        "q_limit_session": settings.q_limit_session,
        "embedding_model": settings.embedding_model,
        "vector_index_path": settings.vector_index_path,
        "corpus_version": settings.corpus_version,
        "admin_protection_enabled": settings.admin_token_enabled and bool(settings.admin_token),
        "ip_rate_limit_enabled": settings.ip_rate_limit_enabled,
        "ip_rate_limit_window_seconds": settings.ip_rate_limit_window_seconds,
        "ip_rate_limit_max_requests": settings.ip_rate_limit_max_requests,
    }


@app.post("/chat")
def chat(req: ChatRequest, _: None = Depends(enforce_rate_limit)):
    request_id = f"req_{uuid.uuid4().hex}"
    session_id = req.session_id or f"sess_{uuid.uuid4().hex}"

    # Character limit
    if len(req.message) > settings.char_limit:
        log_event(
            settings.log_db_path,
            "limit_rejected",
            request_id,
            session_id,
            None,
            {
                "reason": "CHARACTER_LIMIT_PER_QUESTION",
                "char_limit": settings.char_limit,
                "message_len": len(req.message),
            },
        )
        raise HTTPException(
            status_code=400,
            detail=f"Message too long. Limit is {settings.char_limit} characters.",
        )

    # User hash (require user_id for proper per-day limits; fallback to session_id)
    raw_user = req.user_id or session_id
    user_id_hash = hash_user_id(raw_user, settings.hash_salt)

    ensure_session(settings.log_db_path, session_id, user_id_hash)

    # Log request
    log_event(
        settings.log_db_path,
        "chat_request",
        request_id,
        session_id,
        user_id_hash,
        {"message_len": len(req.message), "message_preview": req.message[:120]},
    )

    # Limits + increment
    allowed, reason = check_and_increment(
        settings.log_db_path,
        user_id_hash=user_id_hash,
        session_id=session_id,
        q_limit_day=settings.q_limit_day,
        q_limit_session=settings.q_limit_session,
    )

    if not allowed:
        log_event(
            settings.log_db_path,
            "limit_rejected",
            request_id,
            session_id,
            user_id_hash,
            {"reason": reason},
        )
        raise HTTPException(status_code=429, detail=f"Limit reached: {reason}")

    try:
        retrieval_result = retrieve(req.message, top_k=settings.top_k)
    except Exception as exc:  # pragma: no cover - log retrieval failures
        log_event(
            settings.log_db_path,
            "retrieval_error",
            request_id,
            session_id,
            user_id_hash,
            {"error": str(exc)},
        )
        retrieval_result = {"sources": [], "chunks_retrieved": 0, "sources_deduped": 0}

    index_missing = not os.path.exists(settings.vector_index_path)
    sources_found = retrieval_result.get("sources", []) or []
    chunks_retrieved = retrieval_result.get("chunks_retrieved", len(sources_found))
    sources_deduped = retrieval_result.get("sources_deduped", len(sources_found))

    log_event(
        settings.log_db_path,
        "retrieval_completed",
        request_id,
        session_id,
        user_id_hash,
        {
            "chunks_retrieved": chunks_retrieved,
            "sources_deduped": sources_deduped,
            "top_scores": [c["score"] for c in sources_found[:3]],
        },
    )

    citation_payload_full = []
    for source in sources_found:
        previews = [
            (excerpt.get("text") or "")[:200]
            for excerpt in (source.get("excerpts") or [])
            if excerpt.get("text")
        ]
        citation_payload_full.append(
            {
                "id": source.get("source_id"),
                "title": source.get("page_title") or source.get("title"),
                "page_title": source.get("page_title"),
                "source_domain": source.get("source_domain"),
                "jurisdiction": source.get("jurisdiction"),
                "url": source.get("source_url"),
                "score": source.get("score"),
                "previews": previews,
            }
        )

    allowed_citations = {
        c.get("source_id")
        for c in sources_found
        if c.get("source_id")
    }

    context_block = build_context(sources_found)
    user_prompt = (
        f"Context:\n{context_block}\n\n"
        f"User question:\n{req.message}\n\n"
        "Answer using only the provided context excerpts and follow the required sections."
    ) if context_block else ""

    llm_output = ""
    llm_error_reason = None
    grounding_result = {"ok": False, "reason": "LLM_NOT_EXECUTED", "citations": []}

    if user_prompt:
        try:
            llm_output = generate_chat_completion(SYSTEM_PROMPT, user_prompt)
        except Exception as exc:  # pragma: no cover - external service failure
            llm_error_reason = str(exc)

        if llm_output:
            grounding_result = enforce_grounding(
                llm_output,
                allowed_citations,
                settings.citations_required,
                settings.strict_grounding,
            )
        else:
            grounding_result = {"ok": False, "reason": "EMPTY_COMPLETION", "citations": []}
    else:
        llm_error_reason = llm_error_reason or "NO_CONTEXT_AVAILABLE"
        grounding_result = {"ok": False, "reason": "NO_CONTEXT_AVAILABLE", "citations": []}

    def _fallback_answer() -> str:
        return "I can't answer confidently from my verified sources right now."

    fallback_reason = None
    safe_mode = False

    if not sources_found:
        safe_mode = True
        fallback_reason = "NO_INDEX" if index_missing else "NO_CONTEXT"
    elif not grounding_result.get("ok"):
        safe_mode = True
        if llm_error_reason or grounding_result.get("reason") in ("EMPTY_COMPLETION", "LLM_NOT_EXECUTED"):
            fallback_reason = "LLM_ERROR"
        else:
            fallback_reason = "GROUNDING_FAILED"

    if safe_mode:
        answer = _fallback_answer()
        citation_payload = citation_payload_full if sources_found else []
        returned_ids = [c.get("id") or c.get("source_id") for c in citation_payload if c.get("id") or c.get("source_id")]
        answer_citation_ids: list[str] = []
    else:
        answer = grounding_result["text"]
        answer_citation_ids = extract_source_citations(answer)
        filtered_citations = filter_citations(citation_payload_full, answer_citation_ids)
        citation_payload = filtered_citations
        returned_ids = [c.get("id") or c.get("source_id") for c in citation_payload if c.get("id") or c.get("source_id")]

    log_event(
        settings.log_db_path,
        "llm_completed",
        request_id,
        session_id,
        user_id_hash,
        {
            "model": settings.llm_model,
            "error": llm_error_reason,
            "output_len": len(llm_output),
            "output_preview": llm_output[:200],
            "extracted_citations": answer_citation_ids,
            "allowed_citations": sorted(allowed_citations),
            "grounding_ok": grounding_result.get("ok", False),
            "grounding_reason": grounding_result.get("reason"),
            "returned_citations": returned_ids,
            "returned_citations_count": len(returned_ids),
        },
    )

    log_event(
        settings.log_db_path,
        "chat_response",
        request_id,
        session_id,
        user_id_hash,
        {
            "response_len": len(answer),
            "citation_count": len(citation_payload),
        },
    )

    response = {
        "request_id": request_id,
        "session_id": session_id,
        "answer": answer,
        "citations": citation_payload,
    }

    if fallback_reason:
        response["fallback_reason"] = fallback_reason

    return response
