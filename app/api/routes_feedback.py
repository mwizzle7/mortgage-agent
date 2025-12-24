from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from typing import Optional

from pydantic import BaseModel

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.observability.logger import log_event


router = APIRouter(tags=["feedback"])


class FeedbackRequest(BaseModel):
    request_id: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    question: str
    helpful: bool
    comment: Optional[str] = None


@router.post("/feedback", dependencies=[Depends(enforce_rate_limit)])
def submit_feedback(payload: FeedbackRequest):
    comment = (payload.comment or "").strip()
    if len(comment) > 2000:
        raise HTTPException(status_code=400, detail="Comment too long (2000 character limit).")

    try:
        log_event(
            settings.log_db_path,
            "user_feedback",
            payload.request_id,
            payload.session_id,
            payload.user_id,
            {
                "request_id": payload.request_id,
                "user_id": payload.user_id,
                "session_id": payload.session_id,
                "question": payload.question,
                "helpful": payload.helpful,
                "comment": comment,
            },
        )
    except Exception as exc:  # pragma: no cover - DB failure
        raise HTTPException(status_code=500, detail=f"Failed to record feedback: {exc}") from exc

    return {"status": "ok"}
