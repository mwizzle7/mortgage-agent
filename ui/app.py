from __future__ import annotations

import uuid
from typing import Any, Dict, List, Sequence

import requests
import streamlit as st

DEFAULT_API_BASE = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 60


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
    st.sidebar.header("API configuration")
    api_input = st.sidebar.text_input("API Base URL", value=st.session_state["api_base_url"])
    api_base = api_input.strip() or DEFAULT_API_BASE
    st.session_state["api_base_url"] = api_base

    if st.sidebar.button("Check health"):
        ok, payload, _, raw_text, err = call_api("GET", "/health", api_base)
        if ok and isinstance(payload, dict):
            st.session_state["health_data"] = payload
            st.sidebar.success("Health check succeeded")
        elif ok:
            st.sidebar.warning("Health endpoint did not return JSON")
            st.sidebar.code(raw_text)
        else:
            st.sidebar.error(f"Health check failed: {err or 'Unknown error'}")

    if st.sidebar.button("Run ingestion"):
        ok, payload, _, raw_text, err = call_api("POST", "/admin/ingest", api_base)
        if ok:
            st.sidebar.success("Ingestion started")
            if isinstance(payload, (dict, list)):
                st.sidebar.json(payload)
            else:
                st.sidebar.code(raw_text)
        else:
            st.sidebar.error(f"Ingestion failed: {err or 'Unknown error'}")
            if isinstance(payload, (dict, list)):
                st.sidebar.json(payload)
            elif raw_text:
                st.sidebar.code(raw_text)

    health = st.session_state.get("health_data")
    if isinstance(health, dict):
        st.sidebar.markdown("**Environment**")
        env_rows = {
            "Strict grounding": health.get("strict_grounding"),
            "Citations required": health.get("citations_required"),
            "Embedding model": health.get("embedding_model"),
            "Corpus version": health.get("corpus_version"),
        }
        for label, value in env_rows.items():
            st.sidebar.write(f"{label}: {value if value is not None else 'n/a'}")

    st.sidebar.header("Identity & limits")
    user_id_input = st.sidebar.text_input("user_id", value=st.session_state["user_id"])
    if user_id_input.strip():
        st.session_state["user_id"] = user_id_input.strip()
    if st.sidebar.button("New user_id"):
        st.session_state["user_id"] = _random_id("user")
        st.experimental_rerun()

    session_id_input = st.sidebar.text_input("session_id", value=st.session_state["session_id"])
    if session_id_input.strip():
        st.session_state["session_id"] = session_id_input.strip()
    if st.sidebar.button("New session_id"):
        st.session_state["session_id"] = _random_id("session")
        st.experimental_rerun()

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

    st.sidebar.write(f"Daily question limit: {question_limit_day if question_limit_day is not None else 'n/a'}")
    st.sidebar.write(f"Session question limit: {question_limit_session if question_limit_session is not None else 'n/a'}")
    st.sidebar.write(f"Character limit: {char_limit if char_limit is not None else 'n/a'}")

    auto_rotate = st.sidebar.checkbox(
        "Auto-rotate session_id after each question",
        value=st.session_state.get("auto_rotate_session", False),
    )
    st.session_state["auto_rotate_session"] = auto_rotate

    show_raw = st.sidebar.checkbox(
        "Show raw JSON",
        value=st.session_state.get("show_raw_json", False),
    )
    st.session_state["show_raw_json"] = show_raw

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


def _append_history(entry: Dict[str, Any]) -> None:
    st.session_state.chat_history.append(entry)


def _render_history(show_raw: bool) -> None:
    history: List[Dict[str, Any]] = st.session_state.get("chat_history", [])
    if not history:
        st.info("No questions asked yet.")
        return

    for idx, item in enumerate(history, start=1):
        with st.container():
            st.markdown(f"**You:** {item['question']}")
            if item.get("error"):
                st.error(item["error"])
            else:
                st.markdown(f"**Answer:** {item.get('answer') or 'No answer returned.'}")
                citations = item.get("citations") or []
                with st.expander("Citations", expanded=False):
                    if not citations:
                        st.write("No citations returned.")
                    else:
                        for c_idx, citation in enumerate(citations, start=1):
                            doc_id = citation.get("id") or citation.get("doc_id") or citation.get("document_id")
                            title = citation.get("title") or citation.get("document_title")
                            jurisdiction = citation.get("jurisdiction") or citation.get("scope")
                            score = citation.get("score") or citation.get("similarity")
                            st.markdown(
                                f"**Citation {c_idx}:** ID `{doc_id or 'n/a'}` · Title: {title or 'n/a'} · "
                                f"Jurisdiction: {jurisdiction or 'n/a'} · Score: {score if score is not None else 'n/a'}"
                            )
                            preview = citation.get("preview") or citation.get("text") or citation.get("chunk")
                            st.code(preview or "No preview available.")
            if show_raw:
                raw_payload = item.get("raw_payload")
                if isinstance(raw_payload, (dict, list)):
                    st.json(raw_payload)
                elif item.get("raw_text"):
                    st.code(item["raw_text"])
        st.divider()


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
    _ensure_state()

    api_base, user_id, session_id, show_raw = render_sidebar()

    st.title("Mortgage Agent Test UI")
    st.caption("Interact with the local API, inspect citations, and debug responses without leaving your browser.")

    st.subheader("Conversation")
    if st.button("Clear chat"):
        st.session_state["chat_history"] = []
        st.success("Chat history cleared.")

    _render_history(show_raw)

    st.subheader("Ask a question")
    with st.form("question_form", clear_on_submit=True):
        question = st.text_area("Question", key="question_input", height=150)
        submitted = st.form_submit_button("Ask", type="primary")

    if submitted:
        cleaned_question = question.strip()
        if cleaned_question:
            _send_question(cleaned_question, api_base, user_id, session_id)
        else:
            st.warning("Please enter a question before submitting.")


if __name__ == "__main__":
    main()
