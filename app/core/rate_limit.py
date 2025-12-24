from __future__ import annotations

import time
from collections import deque
from typing import Deque, Dict, Tuple

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.security import get_client_ip
from app.observability.logger import log_event


_REQUEST_HISTORY: Dict[Tuple[str, str], Deque[float]] = {}


def enforce_rate_limit(request: Request) -> None:
    if not settings.ip_rate_limit_enabled:
        return
    ip = get_client_ip(request)
    path = request.url.path
    key = (ip, path)
    now = time.time()
    window = settings.ip_rate_limit_window_seconds
    max_requests = settings.ip_rate_limit_max_requests
    dq = _REQUEST_HISTORY.setdefault(key, deque())
    while dq and now - dq[0] > window:
        dq.popleft()
    if len(dq) >= max_requests:
        log_event(
            settings.log_db_path,
            "rate_limited",
            request_id=None,
            session_id=None,
            user_id_hash=None,
            payload={
                "ip": ip,
                "path": path,
                "window_s": window,
                "max": max_requests,
            },
        )
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again later.")
    dq.append(now)
