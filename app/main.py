from __future__ import annotations

import os
import uuid

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.api.routes_admin import router as admin_router
from app.core.config import settings
from app.core.limits import check_and_increment, ensure_session, hash_user_id
from app.core.grounding import enforce_grounding
from app.core.prompts import SYSTEM_PROMPT, build_context
from app.llm.client import generate_chat_completion
from app.observability.logger import init_db, log_event
from app.rag.retriever import retrieve


app = FastAPI(title="Mortgage Agent", version="0.1.0")
app.include_router(admin_router)


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    user_id: Optional[str] = None  # for MVP, any string is fine (email/uuid/etc.)


@app.on_event("startup")
def startup():
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
    }


@app.post("/chat")
def chat(req: ChatRequest):
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
                "title": source.get("title"),
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
            "extracted_citations": grounding_result.get("citations", []),
            "allowed_citations": sorted(allowed_citations),
            "grounding_ok": grounding_result.get("ok", False),
            "grounding_reason": grounding_result.get("reason"),
        },
    )

    def _fallback_answer(has_citations: bool) -> str:
        base = "I don't have enough verified information in my sources to answer that fully."
        if has_citations and allowed_citations:
            cite_list = ", ".join(f"[{cid}]" for cid in sorted(allowed_citations))
            return f"{base} Here's what I can cite: {cite_list}"
        return base

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
        answer = _fallback_answer(bool(citation_payload_full))
        citation_payload = citation_payload_full if sources_found else []
    else:
        answer = grounding_result["text"]
        citation_payload = citation_payload_full

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
