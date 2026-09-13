"""One-job Greenhouse analysis workflow for the personal MVP."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from career_agent.ingestion import (
    GreenhouseJobError,
    build_greenhouse_job_posting,
    fetch_greenhouse_job,
)
from career_agent.matching import RequirementMatchError, match_job_requirements


class GreenhouseAnalysisError(RuntimeError):
    """Raised when the end-to-end Greenhouse analysis cannot be completed."""


def analyze_greenhouse_job(
    profile_document: dict[str, Any],
    *,
    board_token: str,
    job_id: str | int,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    """Fetch, normalize, match, and package one public Greenhouse job."""

    analysis_time = created_at or datetime.now().astimezone()
    try:
        source_job = fetch_greenhouse_job(board_token, job_id)
        posting_document = build_greenhouse_job_posting(
            source_job,
            board_token=board_token,
            collected_at=analysis_time.date(),
        )
        raw_match_result = match_job_requirements(
            profile_document,
            posting_document,
        )
        match_result = build_persistable_match_result(
            profile_document,
            posting_document,
            raw_match_result,
            created_at=analysis_time,
        )
    except (GreenhouseJobError, RequirementMatchError) as error:
        raise GreenhouseAnalysisError(str(error)) from error

    return {
        "job_posting": posting_document["job_posting"],
        "match_result": match_result,
    }


def build_persistable_match_result(
    profile_document: dict[str, Any],
    posting_document: dict[str, Any],
    match_result: dict[str, Any],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    """Add stable identity and audit fields without copying the full profile."""

    if not isinstance(created_at, datetime) or created_at.tzinfo is None:
        raise GreenhouseAnalysisError("created_at은 시간대가 포함된 datetime이어야 함")
    profile = _required_mapping(profile_document, "profile")
    posting = _required_mapping(posting_document, "job_posting")
    result = deepcopy(match_result)
    if not isinstance(result, dict):
        raise GreenhouseAnalysisError("매칭 결과는 JSON 객체여야 함")

    profile_id = _required_text(_required_mapping(profile, "basic"), "profile_id")
    posting_id = _required_text(_required_mapping(posting, "identity"), "posting_id")
    source = _required_mapping(posting, "source")
    source_url = _required_text(source, "url")
    collected_at = _required_text(source, "collected_at")
    created_text = created_at.isoformat(timespec="seconds")
    created_key = created_at.strftime("%Y%m%dT%H%M%S%z")

    result["identity"] = {
        "analysis_id": f"analysis-{posting_id}-{profile_id}-{created_key}",
        "status": "completed",
        "created_at": created_text,
    }
    existing_inputs = result.get("inputs")
    if not isinstance(existing_inputs, dict):
        raise GreenhouseAnalysisError("매칭 결과 inputs 객체가 필요함")
    existing_inputs.update(
        {
            "profile_id": profile_id,
            "profile_schema_version": _schema_version(profile_document),
            "posting_id": posting_id,
            "posting_source_url": source_url,
            "posting_collected_at": collected_at,
        }
    )

    posting_notes = posting.get("analysis_notes")
    facts = _string_list(posting_notes, "facts")
    posting_unknowns = _string_list(posting_notes, "unknowns")
    result_unknowns = result.get("unknowns", [])
    if not isinstance(result_unknowns, list):
        raise GreenhouseAnalysisError("매칭 결과 unknowns 배열이 필요함")
    unknown_subjects = [
        item.get("subject")
        for item in result_unknowns
        if isinstance(item, dict)
        and isinstance(item.get("subject"), str)
        and item["subject"].strip()
    ]
    result["analysis_notes"] = {
        "facts": facts,
        "interpretations": [
            "현재 사용자 프로필과 구조화된 공고를 MVP 규칙으로 비교한 결과",
            "지원 판단은 합격 가능성 예측이 아님",
        ],
        "unknowns": list(dict.fromkeys([*posting_unknowns, *unknown_subjects])),
    }
    result.setdefault("learning_recommendations", [])
    result.setdefault("portfolio_recommendations", [])

    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        raise GreenhouseAnalysisError("매칭 결과 metadata 객체가 필요함")
    metadata.update(
        {
            "schema_version": "0.1",
            "generated_by": "career-agent",
            "human_review_status": "not_reviewed",
        }
    )
    metadata["incomplete_sections"] = [
        section
        for section in metadata.get("incomplete_sections", [])
        if section not in {"identity", "analysis_notes"}
    ]
    return result


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise GreenhouseAnalysisError(f"'{key}' 객체가 필요함")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseAnalysisError(f"'{key}' 문자열이 필요함")
    return value.strip()


def _schema_version(profile_document: dict[str, Any]) -> str:
    metadata = profile_document.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("schema_version")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unknown"


def _string_list(document: Any, key: str) -> list[str]:
    if not isinstance(document, dict):
        return []
    value = document.get(key, [])
    if not isinstance(value, list):
        raise GreenhouseAnalysisError(f"analysis_notes.{key}는 배열이어야 함")
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]
