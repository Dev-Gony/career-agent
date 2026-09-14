"""Discover and analyze at most one current high-priority Greenhouse job."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from career_agent.discovery import (
    DiscoveryStoreError,
    GreenhouseBoardParseError,
    load_discovery_records,
    run_greenhouse_discovery,
)
from career_agent.ingestion import GreenhouseJobError

from .greenhouse_analysis import (
    GreenhouseAnalysisError,
    analyze_greenhouse_job,
)


class GreenhouseAgentError(RuntimeError):
    """Raised when the constrained discovery-to-analysis run fails."""


def run_greenhouse_agent(
    profile_document: dict[str, Any],
    search_plan: Mapping[str, Any],
    store_path: str | Path,
    *,
    board_token: str,
    policy_checked_at: date,
    executed_at: datetime | None = None,
) -> dict[str, Any]:
    """Analyze the newest current high candidate, or stop without a candidate."""

    execution_time = executed_at or datetime.now().astimezone()
    try:
        discovery = run_greenhouse_discovery(
            search_plan,
            store_path,
            board_token=board_token,
            policy_checked_at=policy_checked_at,
            discovered_at=execution_time,
        )
        current_ids = discovery.get("current_external_ids")
        if not isinstance(current_ids, list) or not all(
            isinstance(item, str) and item for item in current_ids
        ):
            raise GreenhouseAgentError("현재 Greenhouse 공고 ID 목록이 필요함")
        candidates = _current_high_candidates(
            load_discovery_records(store_path),
            board_token=board_token,
            current_external_ids=set(current_ids),
        )
        if not candidates:
            return {
                "status": "no_high_candidate",
                "discovery": discovery,
                "selection": None,
                "analysis": None,
            }

        selected = candidates[0]
        identity = selected["identity"]
        summary = selected["summary"]
        source = selected["source"]
        job_id = identity["external_id"]
        analysis = analyze_greenhouse_job(
            profile_document,
            board_token=board_token,
            job_id=job_id,
            created_at=execution_time,
        )
    except (
        DiscoveryStoreError,
        GreenhouseBoardParseError,
        GreenhouseAnalysisError,
        GreenhouseJobError,
        KeyError,
        TypeError,
    ) as error:
        raise GreenhouseAgentError(str(error)) from error

    return {
        "status": "analyzed",
        "discovery": discovery,
        "selection": {
            "board_token": board_token,
            "external_job_id": job_id,
            "title": summary.get("title"),
            "company": summary.get("company"),
            "source_url": source.get("source_url"),
            "priority": selected["profile_relevance"].get("priority"),
            "reason": selected["profile_relevance"].get("reason"),
            "policy": "newest_current_high_only",
        },
        "analysis": analysis,
    }


def _current_high_candidates(
    records: list[dict[str, Any]],
    *,
    board_token: str,
    current_external_ids: set[str],
) -> list[dict[str, Any]]:
    candidates = [
        record
        for record in records
        if record.get("identity", {}).get("provider") == "greenhouse"
        and record.get("identity", {}).get("external_id") in current_external_ids
        and record.get("source", {}).get("board_token") == board_token
        and record.get("profile_relevance", {}).get("priority") == "high"
    ]
    candidates.sort(
        key=lambda record: record.get("source", {}).get("published_at") or "",
        reverse=True,
    )
    return candidates
