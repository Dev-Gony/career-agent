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

    def __init__(
        self,
        message: str,
        *,
        discovery: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.discovery = discovery


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
    """Run the global one-detail-analysis workflow for a single board."""

    return run_greenhouse_portfolio_agent(
        profile_document,
        search_plan,
        store_path,
        boards=[
            {
                "board_token": board_token,
                "policy_checked_at": policy_checked_at,
            }
        ],
        executed_at=executed_at,
        previous_runs=previous_runs,
    )


def run_greenhouse_portfolio_agent(
    profile_document: dict[str, Any],
    search_plan: Mapping[str, Any],
    store_path: str | Path,
    *,
    boards: Iterable[Mapping[str, Any]],
    executed_at: datetime | None = None,
    previous_runs: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Discover many boards but analyze at most one current high candidate."""

    execution_time = executed_at or datetime.now().astimezone()
    board_list = list(boards)
    if not board_list:
        raise GreenhouseAgentError("실행할 Greenhouse 보드가 필요함")

    board_results: list[dict[str, Any]] = []
    board_errors: list[dict[str, str]] = []
    board_attempts: list[dict[str, Any]] = []
    current_records: list[dict[str, Any]] = []
    for board in board_list:
        if not isinstance(board, Mapping):
            raise GreenhouseAgentError("Greenhouse 보드 설정은 객체여야 함")
        board_token = board.get("board_token")
        policy_checked_at = board.get("policy_checked_at")
        if not isinstance(board_token, str) or not board_token.strip():
            raise GreenhouseAgentError("board_token 문자열이 필요함")
        if not isinstance(policy_checked_at, date):
            raise GreenhouseAgentError("policy_checked_at 날짜가 필요함")
        try:
            discovery = run_greenhouse_discovery(
                search_plan,
                store_path,
                board_token=board_token,
                policy_checked_at=policy_checked_at,
                discovered_at=execution_time,
            )
        except DiscoveryStoreError as error:
            raise GreenhouseAgentError(str(error)) from error
        except (GreenhouseBoardParseError, GreenhouseJobError) as error:
            board_errors.append(
                {"board_token": board_token, "error": str(error)}
            )
            board_attempts.append(
                {
                    "board_token": board_token,
                    "status": "failed",
                    "error": str(error),
                }
            )
            continue

        records = discovery.get("current_records")
        if not isinstance(records, list) or not all(
            isinstance(item, dict) for item in records
        ):
            raise GreenhouseAgentError("현재 Greenhouse 발견 레코드 목록이 필요함")
        board_results.append(discovery)
        board_attempts.append(
            {
                "board_token": board_token,
                "status": "succeeded",
                "fetched_records": discovery.get("fetched_records", 0),
                "item_errors": len(discovery.get("item_errors", [])),
                "new_records": discovery.get("new_records", 0),
                "duplicate_records": discovery.get("duplicate_records", 0),
            }
        )
        current_records.extend(records)

    discovery_summary = {
        "boards_requested": len(board_list),
        "boards_succeeded": len(board_results),
        "boards_failed": len(board_errors),
        "fetched_records": sum(
            result.get("fetched_records", 0) for result in board_results
        ),
        "board_results": board_results,
        "board_errors": board_errors,
        "board_attempts": board_attempts,
        "executed_at": execution_time.isoformat(timespec="seconds"),
    }
    if not board_results:
        failed_tokens = ", ".join(
            error["board_token"] for error in board_errors
        )
        raise GreenhouseAgentError(
            f"모든 Greenhouse 보드 목록 조회가 실패함: {failed_tokens}",
            discovery=discovery_summary,
        )

    candidates = _current_high_candidates(current_records)
    if not candidates:
        return {
            "status": "no_high_candidate",
            "discovery": discovery_summary,
            "selection": None,
            "analysis": None,
            "reuse": None,
        }

    try:
        selected = candidates[0]
        identity = selected["identity"]
        job_id = identity["external_id"]
        board_token = selected["source"]["board_token"]
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
                "discovery": discovery_summary,
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
        raise GreenhouseAgentError(
            str(error), discovery=discovery_summary
        ) from error

    return {
        "status": "analyzed",
        "discovery": discovery_summary,
        "selection": selection,
        "analysis": analysis,
        "reuse": None,
    }


def _current_high_candidates(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    candidates = [
        record
        for record in records
        if record.get("identity", {}).get("provider") == "greenhouse"
        and record.get("profile_relevance", {}).get("priority") == "high"
    ]
    candidates.sort(
        key=_published_timestamp,
        reverse=True,
    )
    return candidates


def _published_timestamp(record: Mapping[str, Any]) -> float:
    value = record.get("source", {}).get("published_at")
    if not isinstance(value, str) or not value.strip():
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return float("-inf")
    return parsed.timestamp()


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
        "policy": "newest_current_high_across_boards_only",
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
