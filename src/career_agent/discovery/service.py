"""Compose feed reading, normalization, ranking, and local deduplication."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from .incruit_feed import fetch_incruit_rss
from .greenhouse_board import build_greenhouse_discovery_records
from .incruit_rss import build_incruit_discovery_records
from .store import merge_discovery_records
from career_agent.ingestion import fetch_greenhouse_jobs


def run_incruit_discovery(
    search_plan: Mapping[str, Any],
    store_path: str | Path,
    *,
    feed_url: str,
    policy_checked_at: date,
    discovered_at: datetime | None = None,
) -> dict[str, Any]:
    """Run one discovery cycle and return a content-free execution summary."""

    execution_time = discovered_at or datetime.now().astimezone()
    xml_text = fetch_incruit_rss(feed_url)
    batch_result = build_incruit_discovery_records(
        xml_text,
        search_plan,
        feed_url=feed_url,
        discovered_at=execution_time,
        policy_checked_at=policy_checked_at,
    )
    store_result = merge_discovery_records(batch_result["records"], store_path)
    priorities = Counter(
        record["profile_relevance"]["priority"]
        for record in store_result["new_records"]
    )

    return {
        "fetched_records": len(batch_result["records"]),
        "item_errors": batch_result["errors"],
        "new_records": len(store_result["new_records"]),
        "duplicate_records": len(store_result["duplicate_keys"]),
        "total_stored_records": store_result["total_records"],
        "new_record_priorities": dict(priorities),
        "store_path": str(Path(store_path)),
        "executed_at": execution_time.isoformat(timespec="seconds"),
    }


def run_greenhouse_discovery(
    search_plan: Mapping[str, Any],
    store_path: str | Path,
    *,
    board_token: str,
    policy_checked_at: date,
    discovered_at: datetime | None = None,
) -> dict[str, Any]:
    """Run one metadata-only Greenhouse board discovery cycle."""

    execution_time = discovered_at or datetime.now().astimezone()
    jobs = fetch_greenhouse_jobs(board_token)
    batch_result = build_greenhouse_discovery_records(
        jobs,
        search_plan,
        board_token=board_token,
        discovered_at=execution_time,
        policy_checked_at=policy_checked_at,
    )
    store_result = merge_discovery_records(batch_result["records"], store_path)
    priorities = Counter(
        record["profile_relevance"]["priority"]
        for record in store_result["new_records"]
    )
    return {
        "board_token": board_token,
        "fetched_records": len(batch_result["records"]),
        "item_errors": batch_result["errors"],
        "new_records": len(store_result["new_records"]),
        "duplicate_records": len(store_result["duplicate_keys"]),
        "total_stored_records": store_result["total_records"],
        "new_record_priorities": dict(priorities),
        "store_path": str(Path(store_path)),
        "executed_at": execution_time.isoformat(timespec="seconds"),
    }
