from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.core.config import settings

USER_AGENT = "MortgageAgentFetcher/2.1 (+https://github.com/)"
TIMEOUT = 30


@dataclass(frozen=True)
class SourceSpec:
    url: str
    source_name: str
    jurisdiction: str


STOP_HEADING_TEXT = {
    "related links",
    "related information",
    "you may also like",
    "resources",
    "top of page",
    "report a problem",
    "share this page",
}

STOP_CONTAINS = [
    "date modified",
    "government of canada",
    "report a problem on this page",
    "page details",
    "share this page",
    "save",
    "share",
    "print",
    "back to top",
    "on this page",
    "skip to main content",
    "contact us",
    "terms and conditions",
    "privacy",
    "feedback",
    "social media",
]


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    segments = [seg for seg in parsed.path.split("/") if seg]
    slug = segments[-1] if segments else parsed.netloc.replace(".", "-")
    slug = slug.rsplit(".", 1)[0]
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")
    return slug or "source"


def _host_prefix(url: str) -> str:
    host = urlparse(url).netloc.lower()
    host = host.split(":", 1)[0]
    if host.startswith(("www2.", "www.", "m.")):
        host = host.split(".", 1)[1]
    parts = [p for p in host.split(".") if p]
    prefix = parts[0] if parts else "source"
    if prefix == "canada" and any(part == "ca" for part in parts[1:]):
        return "canadaca"
    return prefix


def _source_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().split(":", 1)[0]
    if host.startswith(("www2.", "www.", "m.")):
        host = host.split(".", 1)[1]
    return host or "unknown"


def _select_content_root(soup: BeautifulSoup):
    candidates = []
    main = soup.find("main")
    if main:
        candidates.append(main)
    candidates.extend(soup.find_all(attrs={"role": "main"}))
    candidates.extend(soup.find_all("article"))
    candidates = [c for c in candidates if c]
    if candidates:
        return max(candidates, key=lambda tag: len(tag.get_text(" ", strip=True)))
    return soup.body or soup


def _should_skip_line(text_lower: str) -> bool:
    if any(stop in text_lower for stop in STOP_CONTAINS):
        return True
    stripped = text_lower.strip()
    if len(stripped) <= 6 and stripped.isalpha():
        return True
    return False


def _looks_like_breadcrumb(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > 30 or not stripped:
        return False
    if any(ch.isdigit() for ch in stripped):
        return False
    tokens = stripped.split()
    if len(tokens) <= 4 and all(token[0].isupper() for token in tokens if token):
        return True
    return False


def _clean_lines(lines: List[str]) -> List[str]:
    cleaned: List[str] = []
    nav_buffer: List[str] = []

    def _flush_buffer():
        nonlocal nav_buffer
        if len(nav_buffer) == 1:
            cleaned.append(nav_buffer[0])
        nav_buffer.clear()

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped:
            _flush_buffer()
            continue
        if _should_skip_line(lower):
            nav_buffer.clear()
            continue
        if _looks_like_breadcrumb(stripped):
            nav_buffer.append(stripped)
            continue
        _flush_buffer()
        if cleaned and cleaned[-1] == stripped:
            continue
        cleaned.append(stripped)

    _flush_buffer()
    deduped: List[str] = []
    for line in cleaned:
        if deduped and deduped[-1] == line:
            continue
        deduped.append(line)
    return deduped


def _extract_lines_and_title(root) -> Tuple[List[str], str]:
    lines: List[str] = []
    first_h1 = ""
    for tag in root.find_all(["h1", "h2", "h3", "p", "li"], recursive=True):
        if tag.name in {"script", "style", "noscript"}:
            continue
        text = _normalize_whitespace(tag.get_text(" ", strip=True))
        if not text:
            continue
        lower = text.lower()
        if tag.name == "h1" and not first_h1:
            first_h1 = text
        if tag.name in {"h1", "h2", "h3"}:
            if lower in STOP_HEADING_TEXT:
                break
            if _should_skip_line(lower):
                continue
            lines.append(text.upper())
        else:
            if _should_skip_line(lower):
                continue
            lines.append(text)
    return _clean_lines(lines), first_h1


def _write_file(
    spec: SourceSpec,
    url: str,
    host_prefix: str,
    slug: str,
    lines: Iterable[str],
    source_domain: str,
    page_title: str,
) -> Path:
    corpus_path = Path(settings.corpus_raw_path)
    corpus_path.mkdir(parents=True, exist_ok=True)
    retrieved = date.today().isoformat()
    jurisdiction = (spec.jurisdiction or "NA").upper()
    filename = f"{host_prefix}__{slug}__{jurisdiction}__{retrieved}.txt"
    path = corpus_path / filename
    header = (
        f"SOURCE_NAME: {spec.source_name}\n"
        f"SOURCE_URL: {url}\n"
        f"SOURCE_DOMAIN: {source_domain}\n"
        f"JURISDICTION: {jurisdiction}\n"
        f"RETRIEVED_DATE: {retrieved}\n"
        "CONTENT_TYPE: extracted\n"
        f"PAGE_TITLE: {page_title}\n"
        "---\n\n"
    )
    content = "\n".join(line for line in lines if line)
    path.write_text(header + content + "\n", encoding="utf-8")
    return path


def _load_specs_from_payload(data) -> List[SourceSpec]:
    entries = data if isinstance(data, list) else [data]
    specs: List[SourceSpec] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        source_name = entry.get("source_name") or "Unknown Source"
        jurisdiction = entry.get("jurisdiction") or "NA"
        urls = entry.get("urls") or []
        if not isinstance(urls, list):
            continue
        for url in urls:
            if not isinstance(url, str):
                continue
            normalized = url.strip()
            if normalized.endswith(".htmlz"):
                normalized = normalized[:-1]
            specs.append(SourceSpec(url=normalized, source_name=source_name, jurisdiction=jurisdiction))
    return specs


def load_seed_packs(pack: str | None = None) -> Tuple[List[SourceSpec], List[str]]:
    seeds_dir = Path(settings.seed_urls_dir).resolve()
    if not seeds_dir.exists():
        raise FileNotFoundError(
            f"Seed directory not found: {seeds_dir} (ensure repo packs exist; corpus_raw_path={settings.corpus_raw_path})"
        )

    if not pack or pack.strip().lower() == "all":
        files = sorted(seeds_dir.glob("*.json"))
    else:
        target = pack if pack.endswith(".json") else f"{pack}.json"
        candidate = seeds_dir / target
        files = [candidate]

    specs: List[SourceSpec] = []
    loaded_files: List[str] = []
    for file_path in files:
        if not file_path.exists():
            raise FileNotFoundError(f"Seed pack not found: {file_path.name}")
        payload = json.loads(file_path.read_text(encoding="utf-8"))
        loaded_files.append(file_path.name)
        specs.extend(_load_specs_from_payload(payload))
    return specs, loaded_files


def fetch_sources(specs: Sequence[SourceSpec]) -> Tuple[List[Path], List[dict]]:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    written: List[Path] = []
    failed: List[dict] = []

    for spec in specs:
        url = spec.url
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            failed.append({"url": url, "error": str(exc)})
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        root = _select_content_root(soup)
        lines, first_heading = _extract_lines_and_title(root)
        if not lines:
            failed.append({"url": url, "error": "No content extracted"})
            continue

        host_prefix = _host_prefix(url)
        slug = _slug_from_url(url)
        domain = _source_domain(url)
        html_title = ""
        if soup.title and soup.title.string:
            html_title = _normalize_whitespace(soup.title.string)
        page_title = first_heading or html_title or slug.replace("-", " ").strip().title() or "Untitled Page"
        out_path = _write_file(spec, url, host_prefix, slug, lines, domain, page_title)
        written.append(out_path)

    return written, failed


def _self_test() -> None:
    sample = [
        "Save",
        "Share",
        "On this page",
        "Learn more about mortgage insurance.",
    ]
    cleaned = _clean_lines(sample)
    assert cleaned == ["Learn more about mortgage insurance."], cleaned


_self_test()
