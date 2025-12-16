from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable, List, Sequence
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup


@dataclass(frozen=True)
class SourceSpec:
    url: str
    slug: str | None = None


SOURCES: Sequence[SourceSpec] = [
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/mortgages/down-payment.html"),
    SourceSpec("https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account.html"),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/tax-free-savings-account/what.html",
        slug="tax-free-savings-account-what",
    ),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/registered-retirement-savings-plan-rrsp.html"
    ),
    SourceSpec("https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/setting-rrsp.html"),
    SourceSpec("https://www.canada.ca/en/revenue-agency/services/tax/individuals/segments/homeowners.html"),
    SourceSpec("https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account.html"),
    SourceSpec("https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/opening-your-fhsas.html"),
    SourceSpec("https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/first-home-savings-account/contributing-your-fhsa.html"),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/deductions-credits-expenses/line-31270-home-buyers-amount.html"
    ),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/gst-hst-businesses/gst-hst-rebates/new-housing-rebate.html"
    ),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/what-home-buyers-plan/definitions-home-buyer-s-plan.html"
    ),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/rrsps-related-plans/what-home-buyers-plan/participate-home-buyers-plan.html"
    ),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/businesses/topics/rental-income/you-have-rental-income-business-income.html"
    ),
    SourceSpec(
        "https://www.canada.ca/en/revenue-agency/services/tax/individuals/topics/about-your-tax-return/tax-return/completing-a-tax-return/personal-income/line-12700-capital-gains/principal-residence-other-real-estate.html"
    ),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/corporate/federal-oversight-bodies-regulators.html"),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/mortgages/preapproval-qualify-mortgage.html"),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/mortgages/preparing-mortgage.html"),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/mortgages/choose-mortgage.html"),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/insurance/home.html"),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/retirement-planning/cost-seniors-housing.html"),
    SourceSpec("https://www.canada.ca/en/financial-consumer-agency/services/real-estate-fraud.html"),
]

USER_AGENT = "MortgageAgentFetcher/1.0 (+https://github.com/)"
TIMEOUT = 20
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data" / "corpus" / "raw"


def _normalize_whitespace(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _slug_from_url(url: str) -> str:
    parsed = urlparse(url)
    segments = [seg for seg in parsed.path.split("/") if seg]
    slug = segments[-1] if segments else "canadaca"
    slug = slug.rsplit(".", 1)[0] or slug
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", slug).strip("-")
    return slug or "canadaca"


def _extract_lines(soup: BeautifulSoup) -> List[str]:
    main = soup.find("main")
    if not main:
        main = soup.body or soup

    lines: List[str] = []
    for tag in main.find_all(["h1", "h2", "h3", "p", "li"], recursive=True):
        if tag.name in {"script", "style", "noscript"}:
            continue
        text = _normalize_whitespace(tag.get_text(" ", strip=True))
        if not text:
            continue
        if tag.name in {"h1", "h2", "h3"}:
            lines.append(text.upper())
        else:
            lines.append(text)
    return lines


def _write_file(url: str, lines: Iterable[str], slug_override: str | None = None) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    retrieved = date.today().isoformat()
    slug = slug_override or _slug_from_url(url)
    filename = f"canadaca__{slug}__CA__{retrieved}.txt"
    path = OUTPUT_DIR / filename

    header = (
        "SOURCE_NAME: Canada.ca\n"
        f"SOURCE_URL: {url}\n"
        "JURISDICTION: CA\n"
        f"RETRIEVED_DATE: {retrieved}\n"
        "CONTENT_TYPE: extracted\n"
        "---\n\n"
    )
    content = "\n".join(line for line in lines if line)
    path.write_text(header + content + "\n", encoding="utf-8")
    return path


def fetch_and_save() -> None:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for spec in SOURCES:
        url = spec.url
        try:
            response = session.get(url, timeout=TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"[error] Failed to fetch {url}: {exc}")
            continue

        soup = BeautifulSoup(response.text, "html.parser")
        lines = _extract_lines(soup)
        if not lines:
            print(f"[warn] No textual content extracted for {url}")
            continue

        out_path = _write_file(url, lines, slug_override=spec.slug)
        print(f"[ok] Wrote {out_path}")


if __name__ == "__main__":
    fetch_and_save()
