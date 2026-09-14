"""Discover and analyze at most one current high-priority Greenhouse job."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from career_agent.discovery import (
    DiscoveryStoreError,
    GreenhouseBoardParseError,
    run_greenhouse_discovery,
)
from career_agent.ingestion import GreenhouseJobError
from career_agent.matching import MATCHING_RULES_VERSION

from .greenhouse_analysis import (
    ANALYSIS_PIPELINE_VERSION,
    GreenhouseAnalysisError,
    analyze_greenhouse_job,
    profile_content_sha256,
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
    previous_runs: Iterable[Mapping[str, Any]] = (),
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
        current_records = discovery.get("current_records")
        if not isinstance(current_records, list) or not all(
            isinstance(item, dict) for item in current_records
        ):
            raise GreenhouseAgentError("현재 Greenhouse 발견 레코드 목록이 필요함")
        candidates = _current_high_candidates(
            current_records,
            board_token=board_token,
        )
        if not candidates:
            return {
                "status": "no_high_candidate",
                "discovery": discovery,
                "selection": None,
                "analysis": None,
                "reuse": None,
            }

        selected = candidates[0]
        identity = selected["identity"]
        job_id = identity["external_id"]
        selection = _build_selection(selected, board_token=board_token)
        reusable = _find_reusable_analysis(
            previous_runs,
            selected=selected,
            profile_document=profile_document,
            board_token=board_token,
        )
        if reusable is not None:
            analysis_id = reusable["match_result"]["identity"]["analysis_id"]
            return {
                "status": "reused",
                "discovery": discovery,
                "selection": selection,
                "analysis": reusable,
                "reuse": {
                    "analysis_id": analysis_id,
                    "reason": "공고 갱신 시각, 프로필 내용과 분석 규칙 버전이 동일함",
                },
            }

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
        "selection": selection,
        "analysis": analysis,
        "reuse": None,
    }


def _current_high_candidates(
    records: list[dict[str, Any]],
    *,
    board_token: str,
) -> list[dict[str, Any]]:
    candidates = [
        record
        for record in records
        if record.get("identity", {}).get("provider") == "greenhouse"
        and record.get("source", {}).get("board_token") == board_token
        and record.get("profile_relevance", {}).get("priority") == "high"
    ]
    candidates.sort(
        key=lambda record: record.get("source", {}).get("published_at") or "",
        reverse=True,
    )
    return candidates


def _build_selection(
    selected: Mapping[str, Any], *, board_token: str
) -> dict[str, Any]:
    identity = selected["identity"]
    summary = selected["summary"]
    source = selected["source"]
    relevance = selected["profile_relevance"]
    return {
        "board_token": board_token,
        "external_job_id": identity["external_id"],
        "title": summary.get("title"),
        "company": summary.get("company"),
        "source_url": source.get("source_url"),
        "source_updated_at": source.get("updated_at"),
        "priority": relevance.get("priority"),
        "reason": relevance.get("reason"),
        "policy": "newest_current_high_only",
    }


def _find_reusable_analysis(
    previous_runs: Iterable[Mapping[str, Any]],
    *,
    selected: Mapping[str, Any],
    profile_document: dict[str, Any],
    board_token: str,
) -> dict[str, Any] | None:
    source_updated_at = selected.get("source", {}).get("updated_at")
    external_job_id = selected.get("identity", {}).get("external_id")
    if not isinstance(source_updated_at, str) or not source_updated_at.strip():
        return None
    profile_hash = profile_content_sha256(profile_document)

    for previous in previous_runs:
        selection = previous.get("selection")
        analysis = previous.get("analysis")
        if not isinstance(selection, Mapping) or not isinstance(analysis, Mapping):
            continue
        job_posting = analysis.get("job_posting")
        if not isinstance(job_posting, Mapping):
            continue
        posting_source = job_posting.get("source", {})
        match_result = analysis.get("match_result")
        if not isinstance(match_result, Mapping):
            continue
        inputs = match_result.get("inputs", {})
        metadata = match_result.get("metadata", {})
        identity = match_result.get("identity", {})
        if (
            selection.get("board_token") == board_token
            and selection.get("external_job_id") == external_job_id
            and isinstance(posting_source, Mapping)
            and posting_source.get("updated_at") == source_updated_at
            and isinstance(inputs, Mapping)
            and inputs.get("profile_content_sha256") == profile_hash
            and isinstance(metadata, Mapping)
            and metadata.get("matching_rules_version") == MATCHING_RULES_VERSION
            and metadata.get("analysis_pipeline_version")
            == ANALYSIS_PIPELINE_VERSION
            and isinstance(identity, Mapping)
            and isinstance(identity.get("analysis_id"), str)
        ):
            return deepcopy(dict(analysis))
    return None
