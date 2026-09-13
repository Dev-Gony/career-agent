from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import (  # noqa: E402
    DiscoveryStoreError,
    format_discovery_records,
    load_discovery_records,
)


DEFAULT_STORE_PATH = REPOSITORY_ROOT / "private-data/discoveries.json"


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main() -> int:
    _configure_console_encoding()
    parser = argparse.ArgumentParser(
        description="로컬에 저장된 채용 발견 후보를 표시합니다."
    )
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument(
        "--priority",
        choices=("high", "medium", "review", "low"),
        default=None,
    )
    args = parser.parse_args()

    try:
        records = load_discovery_records(args.store)
        report = format_discovery_records(
            records,
            limit=args.limit,
            priority=args.priority,
        )
    except (DiscoveryStoreError, ValueError) as error:
        print(f"후보 목록을 만들 수 없음: {error}", file=sys.stderr)
        return 1

    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
