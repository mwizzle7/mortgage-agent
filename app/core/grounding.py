from __future__ import annotations

import re
from typing import Dict, Iterable, List


_CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


def extract_source_citations(text: str) -> List[str]:
    if not text:
        return []
    seen: set[str] = set()
    ordered: List[str] = []
    for match in _CITATION_PATTERN.finditer(text):
        citation_id = match.group(1)
        if citation_id not in seen:
            seen.add(citation_id)
            ordered.append(citation_id)
    return ordered


def filter_citations(citations: Iterable[dict], used_ids: Iterable[str]) -> List[dict]:
    if not citations or not used_ids:
        return []
    lookup = {}
    for citation in citations:
        citation_id = citation.get("id") or citation.get("source_id")
        if citation_id:
            lookup[citation_id] = citation
    filtered: List[dict] = []
    for cid in used_ids:
        item = lookup.get(cid)
        if item:
            filtered.append(item)
    return filtered


def enforce_grounding(
    text: str,
    allowed: Iterable[str],
    citations_required: bool,
    strict: bool,
) -> Dict:
    allowed_set = set(allowed or [])
    extracted_ordered = extract_source_citations(text)
    extracted_set = set(extracted_ordered)
    payload: Dict = {
        "citations": extracted_ordered,
    }

    if citations_required and not extracted_ordered:
        payload["ok"] = False
        payload["reason"] = "NO_CITATIONS"
        return payload

    invalid = extracted_set - allowed_set
    if invalid and strict:
        payload["ok"] = False
        payload["reason"] = "INVALID_CITATIONS"
        payload["invalid"] = sorted(invalid)
        return payload

    payload["ok"] = True
    payload["text"] = text
    if invalid:
        payload["warning"] = {
            "invalid_citations": sorted(invalid),
        }
    return payload
