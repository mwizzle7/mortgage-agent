from __future__ import annotations

from fetch_urls_to_txt import build_parser, fetch_and_save, _load_sources_from_args


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    specs = _load_sources_from_args(args)
    fetch_and_save(specs)


if __name__ == "__main__":
    main()
