from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Sequence

from app.corpus.fetcher import SourceSpec, fetch_sources, _load_specs_from_payload


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fetch approved mortgage sources into the local corpus.")
    parser.add_argument("--urls-file", action="append", help="Path to a JSON file describing source_name, jurisdiction, and urls")
    parser.add_argument("--urls-json", action="append", help="Inline JSON payload describing source packs")
    return parser


def load_specs_from_args(args: argparse.Namespace) -> Sequence[SourceSpec]:
    specs: List[SourceSpec] = []
    json_strings = args.urls_json or []
    for payload in json_strings:
        specs.extend(_load_specs_from_payload(json.loads(payload)))
    file_paths = args.urls_file or []
    for path in file_paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        specs.extend(_load_specs_from_payload(payload))
    return specs


def main() -> None:
    args = build_parser().parse_args()
    specs = load_specs_from_args(args)
    if not specs:
        raise SystemExit("No URLs provided. Pass --urls-file or --urls-json.")
    written, failed = fetch_sources(specs)
    print(f"---\nSummary: wrote {len(written)} files")
    for path in written:
        print(f" - {path}")
    if failed:
        print(f"[warn] {len(failed)} failures:")
        for item in failed:
            print(f" - {item['url']}: {item['error']}")


if __name__ == "__main__":
    main()
