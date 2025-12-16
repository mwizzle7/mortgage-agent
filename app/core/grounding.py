from __future__ import annotations

import re
from typing import Dict, Iterable, Set


_CITATION_PATTERN = re.compile(r"\[(S\d+)\]")


def extract_citations(text: str) -> Set[str]:
    if not text:
        return set()
    return set(match.group(1) for match in _CITATION_PATTERN.finditer(text))


def enforce_grounding(
    text: str,
    allowed: Iterable[str],
    citations_required: bool,
    strict: bool,
) -> Dict:
    allowed_set = set(allowed or [])
    extracted = extract_citations(text)
    payload: Dict = {
        "citations": sorted(extracted),
    }

    if citations_required and not extracted:
        payload["ok"] = False
        payload["reason"] = "NO_CITATIONS"
        return payload

    invalid = extracted - allowed_set
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
