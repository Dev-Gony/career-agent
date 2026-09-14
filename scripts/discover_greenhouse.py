from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import (  # noqa: E402
    DiscoveryStoreError,
    GreenhouseBoardParseError,
    format_discovery_records,
    load_discovery_records,
    run_greenhouse_discovery,
)
from career_agent.ingestion import GreenhouseJobError  # noqa: E402


DEFAULT_BOARD = "sendbird"
DEFAULT_SEARCH_PLAN = REPOSITORY_ROOT / "data/job_search_plan.example.json"
DEFAULT_STORE_PATH = REPOSITORY_ROOT / "private-data/discoveries.json"
POLICY_CHECKED_AT = date(2026, 9, 14)


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main() -> int:
    _configure_console_encoding()
    parser = argparse.ArgumentParser(
        description="Greenhouse 공식 보드에서 프로필 관련 채용 후보를 발견합니다."
    )
    parser.add_argument("--board", default=DEFAULT_BOARD)
    parser.add_argument("--search-plan", type=Path, default=DEFAULT_SEARCH_PLAN)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--include-review",
        action="store_true",
        help="프로필 직접 관련성이 확인되지 않은 review 후보도 표시",
    )
    args = parser.parse_args()

    try:
        search_plan = json.loads(args.search_plan.read_text(encoding="utf-8"))
        summary = run_greenhouse_discovery(
            search_plan,
            args.store,
            board_token=args.board,
            policy_checked_at=POLICY_CHECKED_AT,
        )
        board_records = [
            record
            for record in load_discovery_records(args.store)
            if record.get("identity", {}).get("provider") == "greenhouse"
            and record.get("source", {}).get("board_token") == args.board
        ]
        display_records = board_records
        if not args.include_review:
            display_records = [
                record
                for record in board_records
                if record.get("profile_relevance", {}).get("priority")
                in {"high", "medium"}
            ]
        report = format_discovery_records(display_records, limit=args.limit)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(f"검색 계획을 읽을 수 없음: {error}", file=sys.stderr)
        return 1
    except (
        DiscoveryStoreError,
        GreenhouseBoardParseError,
        GreenhouseJobError,
        ValueError,
    ) as error:
        print(f"Greenhouse 후보 발견 실패: {error}", file=sys.stderr)
        return 1

    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False, indent=2))
    print()
    if not args.include_review:
        print("표시 기준: 프로필 관련성이 확인된 high/medium 후보")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
