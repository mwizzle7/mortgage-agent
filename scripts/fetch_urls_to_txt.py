from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = "MortgageAgentFetcher/2.1 (+https://github.com/)"
TIMEOUT = 30
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "corpus" / "raw"

DEFAULT_PACKS: Sequence[dict] = [
    {
        "source_name": "Canada.ca",
        "jurisdiction": "CA",
        "urls": [
            "https://www.canada.ca/en/financial-consumer-agency/services/mortgages/down-payment.html",
            "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html",
            "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html",
            "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/opening-your-fhsas.html",
        ],
    }
]


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
    return any(stop in text_lower for stop in STOP_CONTAINS)


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
    return lines, first_h1


def _write_file(
    spec: SourceSpec,
    url: str,
    host_prefix: str,
    slug: str,
    lines: Iterable[str],
    source_domain: str,
    page_title: str,
) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    retrieved = date.today().isoformat()
    jurisdiction = (spec.jurisdiction or "NA").upper()
    filename = f"{host_prefix}__{slug}__{jurisdiction}__{retrieved}.txt"
    path = OUTPUT_DIR / filename
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


def _load_payload(data: dict | list | None) -> List[SourceSpec]:
    if data is None:
        return []
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


def _load_sources_from_args(args: argparse.Namespace) -> Sequence[SourceSpec]:
    specs: List[SourceSpec] = []
    json_strings = args.urls_json or []
    for payload in json_strings:
        specs.extend(_load_payload(json.loads(payload)))
    file_paths = args.urls_file or []
    for path in file_paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        specs.extend(_load_payload(payload))
    if specs:
        return specs
    combined: List[SourceSpec] = []
    for pack in DEFAULT_PACKS:
        combined.extend(_load_payload(pack))
    return combined


def fetch_and_save(sources: Sequence[SourceSpec]) -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    written: List[Path] = []
    for spec in sources:
        url = spec.url
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"[error] Failed to fetch {url}: {exc}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        root = _select_content_root(soup)
        lines, first_heading = _extract_lines_and_title(root)
        if not lines:
            print(f"[warn] No textual content extracted for {url}")
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
        print(f"[ok] Wrote {out_path}")

    print(f"---\nSummary: wrote {len(written)} files")
    for path in written:
        print(f" - {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch approved mortgage sources into the local corpus.")
    parser.add_argument("--urls-file", action="append", help="Path to a JSON file describing source_name, jurisdiction, and urls")
    parser.add_argument("--urls-json", action="append", help="Inline JSON payload describing source packs")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    specs = _load_sources_from_args(args)
    fetch_and_save(specs)


if __name__ == "__main__":
    main()
