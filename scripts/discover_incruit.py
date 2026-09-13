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
    IncruitFeedError,
    IncruitRssParseError,
    run_incruit_discovery,
)


DEFAULT_FEED_URL = "https://www.incruit.com/rss/job.asp?occ1=150"
DEFAULT_SEARCH_PLAN = REPOSITORY_ROOT / "data/job_search_plan.example.json"
DEFAULT_STORE_PATH = REPOSITORY_ROOT / "private-data/discoveries.json"
POLICY_CHECKED_AT = date(2026, 9, 13)


def _configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main() -> int:
    _configure_console_encoding()
    parser = argparse.ArgumentParser(
        description="공식 인크루트 RSS에서 신규 채용 후보를 발견합니다."
    )
    parser.add_argument("--feed-url", default=DEFAULT_FEED_URL)
    parser.add_argument("--search-plan", type=Path, default=DEFAULT_SEARCH_PLAN)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    args = parser.parse_args()

    try:
        search_plan = json.loads(args.search_plan.read_text(encoding="utf-8"))
        summary = run_incruit_discovery(
            search_plan,
            args.store,
            feed_url=args.feed_url,
            policy_checked_at=POLICY_CHECKED_AT,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": f"검색 계획을 읽을 수 없음: {error}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1
    except (DiscoveryStoreError, IncruitFeedError, IncruitRssParseError) as error:
        print(
            json.dumps(
                {"status": "failed", "error": str(error)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    print(
        json.dumps({"status": "ok", **summary}, ensure_ascii=False, indent=2)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
