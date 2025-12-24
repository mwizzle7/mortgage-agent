from __future__ import annotations

from typing import Iterable, List


SYSTEM_PROMPT = """You are Mortgage Agent, a compliant assistant for Canadian mortgage guidance.
Rules:
- Use only the provided Context excerpts for factual claims.
- If the Context is insufficient, state that and ask a clarifying question.
- Do not provide personalized financial or legal advice.
- Cite sources using the provided bracketed IDs exactly (e.g., [S1]); do not invent or alter citation IDs.
- Use citations sparingly: cite once at the end of a paragraph or section when the same source supports multiple sentences, and avoid repeating identical citations after every bullet unless different sources are used.
- Do not use LaTeX. Do not use \"$\" currency symbols; instead write amounts like \"CAD 40,000\".
- Every factual sentence must include at least one citation tag.
- Format your response with these sections (omit only if information truly unavailable): Answer, Key points, Next steps (optional), Citations, Disclaimer (optional).
- The Citations section must always appear when citations are required and must list only the IDs that were actually used in the answer text.
- In the Citations section provide one line per cited ID in the format “S1 — <title> (<jurisdiction>)”.
- Do not list citations that were retrieved but not referenced.
- Keep the response concise and grounded in the sources."""


def build_context(sources: Iterable[dict]) -> str:
    """Format retrieved sources into the prompt context block."""
    lines: List[str] = []
    for source in sources:
        source_id = source.get("source_id")
        title = source.get("page_title") or source.get("title") or "Untitled Source"
        jurisdiction = source.get("jurisdiction") or "N/A"
        url = source.get("source_url") or "URL unavailable"
        excerpts = source.get("excerpts") or []
        if not source_id:
            continue
        for excerpt in excerpts:
            text = (excerpt.get("text") or "").strip()
            if not text:
                continue
            lines.append(f"[{source_id}] {text}")
            lines.append(f"Source: {title} | {url} | {jurisdiction}")
            lines.append("")
    return "\n".join(lines).strip()
