from __future__ import annotations

import html
import json
import os
import re
import uuid
from typing import Any, Dict, List, Sequence

import requests
import streamlit as st


def _secret_value(key: str) -> str | None:
    try:
        secrets = st.secrets
    except Exception:  # pragma: no cover - Streamlit secrets not available
        return None
    return secrets.get(key)


def _resolve_api_base_default() -> str:
    secret_val = _secret_value("API_BASE_URL")
    if secret_val:
        return secret_val.strip()
    env_val = os.getenv("API_BASE_URL")
    if env_val:
        return env_val.strip()
    return "http://127.0.0.1:8000"


def _resolve_public_mode() -> bool:
    raw = _secret_value("PUBLIC_UI")
    if raw is None:
        raw = os.getenv("PUBLIC_UI")
    if raw is None:
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "y", "on")


DEFAULT_API_BASE = _resolve_api_base_default()
PUBLIC_UI = _resolve_public_mode()
REQUEST_TIMEOUT = 60

CUSTOM_CSS = """
<style>
    body {
        background-color: #f5f7fb;
    }
    .main-header {
        background: white;
        padding: 1.2rem 1.5rem;
        border-radius: 12px;
        border: 1px solid #e1e4eb;
        margin-bottom: 1rem;
        box-shadow: 0 2px 6px rgba(24, 39, 75, 0.05);
    }
    .main-header h1 {
        margin-bottom: 0.4rem;
    }
    .user-message,
    .assistant-message {
        background: white;
        border-radius: 12px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        border: 1px solid #e3e6ef;
        box-shadow: 0 1px 3px rgba(24, 39, 75, 0.06);
    }
    .user-message {
        border-left: 4px solid #4a90e2;
    }
    .assistant-message {
        border-left: 4px solid #57b59a;
    }
    .assistant-message.error {
        border-left-color: #e25858;
        background: #fff6f6;
    }
    .message-label {
        font-weight: 600;
        margin-bottom: 0.35rem;
        color: #606378;
        text-transform: uppercase;
        font-size: 0.8rem;
    }
    .source-citation {
        border-left: 3px solid #d1d8f2;
        padding: 0.5rem 0.75rem;
        margin-bottom: 0.5rem;
        background: #f8faff;
        border-radius: 6px;
    }
    .source-citation:last-child {
        margin-bottom: 0;
    }
    .source-citation a {
        color: #3a6ed8;
    }
</style>
"""


def _random_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}"


def _build_url(base_url: str, path: str) -> str:
    base = (base_url or DEFAULT_API_BASE).rstrip("/")
    if not path.startswith("/"):
        path = f"/{path}"
    return f"{base}{path}"


def call_api(method: str, path: str, base_url: str, **kwargs: Any) -> tuple[bool, Any, int | None, str, str | None]:
    url = _build_url(base_url, path)
    try:
        response = requests.request(method, url, timeout=REQUEST_TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        return False, None, None, "", str(exc)

    raw_text = response.text or ""
    try:
        payload = response.json()
    except ValueError:
        payload = raw_text

    if response.ok:
        return True, payload, response.status_code, raw_text, None

    error_message: str | None = None
    if isinstance(payload, dict):
        error_message = payload.get("detail") or payload.get("message")
    if not error_message:
        error_message = f"{response.status_code} {response.reason}".strip()
    return False, payload, response.status_code, raw_text, error_message


def _ensure_state() -> None:
    state = st.session_state
    state.setdefault("api_base_url", DEFAULT_API_BASE)
    state.setdefault("user_id", _random_id("user"))
    state.setdefault("session_id", _random_id("session"))
    state.setdefault("chat_history", [])
    state.setdefault("health_data", None)
    state.setdefault("auto_rotate_session", False)
    state.setdefault("show_raw_json", False)
    state.setdefault("clear_question_input", False)
    state.setdefault("public_ui", PUBLIC_UI)


def _extract_from_health(data: Dict[str, Any] | None, paths: Sequence[Sequence[str]]) -> Any:
    if not isinstance(data, dict):
        return None
    for path in paths:
        current: Any = data
        for key in path:
            if not isinstance(current, dict):
                break
            current = current.get(key)
        else:
            if current is not None:
                return current
    return None


def render_sidebar() -> tuple[str, str, str, bool]:
    sidebar = st.sidebar
    sidebar.title("Mortgage Agent")
    sidebar.caption("Configure your session or open the advanced tools for diagnostics.")

    health = st.session_state.get("health_data")

    sidebar.subheader("Session identity")
    user_id_input = sidebar.text_input("user_id", value=st.session_state["user_id"])
    if user_id_input.strip():
        st.session_state["user_id"] = user_id_input.strip()
    if sidebar.button("New user_id"):
        st.session_state["user_id"] = _random_id("user")
        st.rerun()

    session_id_input = sidebar.text_input("session_id", value=st.session_state["session_id"])
    if session_id_input.strip():
        st.session_state["session_id"] = session_id_input.strip()
    if sidebar.button("New session_id"):
        st.session_state["session_id"] = _random_id("session")
        st.rerun()

    question_limit_day = _extract_from_health(
        health,
        (("limits", "per_day"), ("limits", "question_limit_per_day"), ("QUESTION_LIMIT_PER_DAY",), ("question_limit_per_day",)),
    )
    question_limit_session = _extract_from_health(
        health,
        (("limits", "per_session"), ("limits", "question_limit_per_session"), ("QUESTION_LIMIT_PER_SESSION",)),
    )
    char_limit = _extract_from_health(
        health,
        (("limits", "character_limit"), ("CHARACTER_LIMIT_PER_QUESTION",), ("character_limit_per_question",)),
    )

    sidebar.markdown("### Limits")
    sidebar.write(f"Daily question limit: {question_limit_day if question_limit_day is not None else 'n/a'}")
    sidebar.write(f"Session question limit: {question_limit_session if question_limit_session is not None else 'n/a'}")
    sidebar.write(f"Character limit: {char_limit if char_limit is not None else 'n/a'}")

    auto_rotate = sidebar.toggle(
        "Auto-rotate session_id after each question",
        value=st.session_state.get("auto_rotate_session", False),
    )
    st.session_state["auto_rotate_session"] = auto_rotate

    show_raw = st.session_state.get("show_raw_json", False)
    if not PUBLIC_UI:
        show_raw = sidebar.toggle(
            "Show raw JSON for each answer",
            value=show_raw,
        )
        st.session_state["show_raw_json"] = show_raw
    else:
        show_raw = False
        st.session_state["show_raw_json"] = False

    if not PUBLIC_UI:
        with sidebar.expander("Developer tools", expanded=False):
            api_input = st.text_input("API Base URL", value=st.session_state["api_base_url"])
            api_base = api_input.strip() or DEFAULT_API_BASE
            st.session_state["api_base_url"] = api_base

            col_health, col_ingest = st.columns(2)
            if col_health.button("Check health"):
                ok, payload, _, raw_text, err = call_api("GET", "/health", api_base)
                if ok and isinstance(payload, dict):
                    st.session_state["health_data"] = payload
                    st.success("Health check succeeded")
                elif ok:
                    st.warning("Health endpoint did not return JSON")
                    st.code(raw_text)
                else:
                    st.error(f"Health check failed: {err or 'Unknown error'}")

            if col_ingest.button("Run ingestion"):
                ok, payload, _, raw_text, err = call_api("POST", "/admin/ingest", api_base)
                if ok:
                    st.success("Ingestion started")
                    if isinstance(payload, (dict, list)):
                        st.json(payload)
                    else:
                        st.code(raw_text)
                else:
                    st.error(f"Ingestion failed: {err or 'Unknown error'}")
                    if isinstance(payload, (dict, list)):
                        st.json(payload)
                    elif raw_text:
                        st.code(raw_text)

            health = st.session_state.get("health_data")
            if isinstance(health, dict):
                st.markdown("**Environment snapshot**")
                env_rows = {
                    "Strict grounding": health.get("strict_grounding"),
                    "Citations required": health.get("citations_required"),
                    "Embedding model": health.get("embedding_model"),
                    "Corpus version": health.get("corpus_version"),
                }
                for label, value in env_rows.items():
                    st.write(f"{label}: {value if value is not None else 'n/a'}")
    else:
        api_base = st.session_state["api_base_url"] = st.session_state.get("api_base_url", DEFAULT_API_BASE)
        sidebar.caption(f"API endpoint: {api_base}")

    api_base = st.session_state["api_base_url"]

    return api_base, st.session_state["user_id"], st.session_state["session_id"], show_raw


def _extract_answer(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("answer", "message", "response", "output"):
            value = payload.get(key)
            if value:
                return str(value)
    return str(payload) if payload is not None else ""


def _extract_citations(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        citations = payload.get("citations")
        if isinstance(citations, list):
            return [c for c in citations if isinstance(c, dict)]
    return []


_DOLLAR_PATTERN = re.compile(r"(?<!\\)\$")
_BACKTICK_PATTERN = re.compile(r"(?<!\\)`")


def sanitize_for_streamlit_md(text: str) -> str:
    if not text:
        return ""
    sanitized = _DOLLAR_PATTERN.sub(r"\\$", text)
    sanitized = _BACKTICK_PATTERN.sub(r"\\`", sanitized)
    return sanitized


def _format_text_html(text: str) -> str:
    sanitized = sanitize_for_streamlit_md(text)
    escaped = html.escape(sanitized)
    return escaped.replace("\n", "<br>")


def _append_history(entry: Dict[str, Any]) -> None:
    st.session_state.chat_history.append(entry)


def _store_feedback_summary(request_id: str, helpful: bool, comment: str | None) -> None:
    summary = json.dumps(
        {
            "request_id": request_id,
            "helpful": helpful,
            "comment": comment or "",
        },
        indent=2,
    )
    st.session_state[f"feedback_done_{request_id}"] = True
    st.session_state[f"feedback_summary_{request_id}"] = summary


def _submit_feedback(entry: Dict[str, Any], helpful: bool, comment: str | None, api_base: str, user_id: str, session_id: str) -> None:
    request_id = entry.get("request_id")
    if not request_id:
        st.error("Unable to send feedback: missing request_id.")
        return
    payload = {
        "request_id": request_id,
        "user_id": entry.get("user_id") or user_id,
        "session_id": entry.get("session_id") or session_id,
        "question": entry.get("question") or "",
        "helpful": helpful,
        "comment": (comment or "").strip() or None,
    }
    ok, response_payload, status_code, raw_text, err = call_api("POST", "/feedback", api_base, json=payload)
    if ok:
        st.success("Thanks — feedback received.")
        _store_feedback_summary(request_id, helpful, payload["comment"] or "")
        summary = st.session_state.get(f"feedback_summary_{request_id}")
        if summary:
            st.code(summary)
    else:
        message = err or f"HTTP {status_code or '???'}"
        st.error(f"Unable to send feedback: {message}")
        if isinstance(response_payload, (dict, list)):
            st.json(response_payload)
        elif raw_text:
            st.code(raw_text)


def _render_history(api_base: str, user_id: str, session_id: str, show_raw: bool) -> None:
    history: List[Dict[str, Any]] = st.session_state.get("chat_history", [])
    if not history:
        st.info("No questions asked yet.")
        return
    for idx, item in enumerate(history):
        user_html = f"""
        <div class="user-message">
            <div class="message-label">You</div>
            <div class="message-text">{_format_text_html(item["question"])}</div>
        </div>
        """
        st.markdown(user_html, unsafe_allow_html=True)

        error_text = item.get("error")
        if error_text:
            assistant_html = f"""
            <div class="assistant-message error">
                <div class="message-label">Assistant</div>
                <div class="message-text">{_format_text_html(error_text)}</div>
            </div>
            """
            st.markdown(assistant_html, unsafe_allow_html=True)
        else:
            answer_html = f"""
            <div class="assistant-message">
                <div class="message-label">Assistant</div>
                <div class="message-text">{_format_text_html(item.get("answer") or "No answer returned.")}</div>
            </div>
            """
            st.markdown(answer_html, unsafe_allow_html=True)
            citations = item.get("citations") or []
            with st.expander("Citations", expanded=False):
                if not citations:
                    st.write("No citations returned.")
                else:
                    for source in citations:
                        source_id = source.get("id") or source.get("source_id") or "S?"
                        title = (
                            source.get("page_title")
                            or source.get("title")
                            or source.get("document_title")
                            or "Untitled Source"
                        )
                        jurisdiction = source.get("jurisdiction") or source.get("scope") or "N/A"
                        url = source.get("url") or source.get("source_url")
                        domain = source.get("source_domain") or source.get("domain")
                        suffix = jurisdiction
                        if domain:
                            suffix = f"{suffix}, {domain}"
                        safe_title = _format_text_html(title)
                        safe_suffix = _format_text_html(suffix)
                        safe_id = html.escape(str(source_id))
                        safe_url = html.escape(url, quote=True) if url else ""
                        link_html = f' — <a href="{safe_url}" target="_blank" rel="noopener">{safe_url}</a>' if safe_url else ""
                        citation_html = f"""
                        <div class="source-citation">
                            <strong>{safe_id}</strong> · {safe_title} ({safe_suffix}){link_html}
                        </div>
                        """
                        st.markdown(citation_html, unsafe_allow_html=True)
            request_id = item.get("request_id") or f"turn_{idx}"
            st.markdown("**Feedback**")
            feedback_done = st.session_state.get(f"feedback_done_{request_id}")
            if feedback_done:
                st.success("Feedback already submitted. Thank you!")
                summary = st.session_state.get(f"feedback_summary_{request_id}")
                if summary:
                    st.code(summary)
            else:
                choice_key = f"feedback_choice_{request_id}"
                comment_key = f"feedback_comment_{request_id}"
                options = ["Select...", "Helpful", "Not helpful"]
                selection = st.selectbox(
                    "How was this answer?",
                    options,
                    key=choice_key,
                    index=0,
                )
                comment = st.text_area("What was missing or wrong?", key=comment_key, height=100)
                if st.button("Send feedback", key=f"send_feedback_{request_id}"):
                    if selection == "Select...":
                        st.warning("Please select whether the answer was helpful.")
                    else:
                        helpful = selection == "Helpful"
                        _submit_feedback(item, helpful, comment, api_base, user_id, session_id)
        if show_raw:
            raw_payload = item.get("raw_payload")
            if isinstance(raw_payload, (dict, list)):
                st.json(raw_payload)
            elif item.get("raw_text"):
                st.code(item["raw_text"])


def _send_question(question: str, api_base: str, user_id: str, session_id: str) -> None:
    payload = {"message": question, "user_id": user_id, "session_id": session_id}
    ok, response_payload, status_code, raw_text, err = call_api("POST", "/chat", api_base, json=payload)

    if ok:
        answer = _extract_answer(response_payload)
        citations = _extract_citations(response_payload)
        _append_history(
            {
                "question": question,
                "answer": answer,
                "citations": citations,
                "raw_payload": response_payload,
                "raw_text": raw_text,
                "request_id": response_payload.get("request_id"),
                "session_id": response_payload.get("session_id") or session_id,
                "user_id": user_id,
            }
        )
        if st.session_state.get("auto_rotate_session"):
            st.session_state["session_id"] = _random_id("session")
    else:
        error_text = err or "Request failed"
        if status_code == 429:
            error_text = "Rate limit hit (HTTP 429). Please wait before asking again."
        _append_history(
            {
                "question": question,
                "error": error_text,
                "raw_payload": response_payload,
                "raw_text": raw_text,
            }
        )
        st.error(error_text)


def main() -> None:
    st.set_page_config(page_title="Mortgage Agent Test UI", layout="wide")
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    _ensure_state()
    if st.session_state.get("clear_question_input"):
        st.session_state["question_input"] = ""
        st.session_state["clear_question_input"] = False

    api_base, user_id, session_id, show_raw = render_sidebar()

    st.markdown(
        """
        <div class="main-header">
          <h1>Mortgage Agent</h1>
          <p>Grounded answers backed by official Canadian sources (beta).</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if PUBLIC_UI:
        st.info(
            "Answers are grounded in vetted Canadian mortgage sources. "
            "This beta is informational only and is not financial advice or a substitute for professional guidance."
        )

    st.subheader("Conversation")
    if st.button("Clear chat"):
        st.session_state["chat_history"] = []
        st.rerun()

    _render_history(api_base, user_id, session_id, show_raw)

    st.subheader("Ask a question")
    question_key = "question_input"
    question = st.text_area("Question", key=question_key, height=150)
    ask_disabled = not question.strip()
    if st.button("Ask", type="primary", disabled=ask_disabled):
        cleaned_question = question.strip()
        if not cleaned_question:
            st.warning("Please enter a question before submitting.")
        else:
            _send_question(cleaned_question, api_base, user_id, session_id)
            st.session_state["clear_question_input"] = True
            st.rerun()


if __name__ == "__main__":
    main()
