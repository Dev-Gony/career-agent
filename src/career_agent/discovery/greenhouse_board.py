"""Normalize Greenhouse board metadata into discovery records."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping
from urllib.parse import urlsplit

from .ranking import build_profile_relevance


PROVIDER = "greenhouse"
DEFAULT_UNKNOWNS = ["경력", "학력", "주요 업무", "필수 조건", "우대 조건"]


class GreenhouseBoardParseError(ValueError):
    """Raised when Greenhouse board metadata cannot be normalized safely."""


def build_greenhouse_discovery_records(
    jobs: list[dict[str, Any]],
    search_plan: Mapping[str, Any],
    *,
    board_token: str,
    discovered_at: datetime,
    policy_checked_at: date,
    is_example: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Build discovery records while isolating invalid jobs."""

    if not isinstance(jobs, list):
        raise GreenhouseBoardParseError("Greenhouse jobs는 배열이어야 함")
    _require_timezone(discovered_at)
    if not isinstance(board_token, str) or not board_token.strip():
        raise GreenhouseBoardParseError("board_token이 필요함")

    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item_number, job in enumerate(jobs, start=1):
        try:
            records.append(
                _build_record(
                    job,
                    search_plan,
                    board_token=board_token,
                    discovered_at=discovered_at,
                    policy_checked_at=policy_checked_at,
                    is_example=is_example,
                )
            )
        except GreenhouseBoardParseError as error:
            errors.append({"item_number": item_number, "error": str(error)})
    return {"records": records, "errors": errors}


def _build_record(
    job: dict[str, Any],
    search_plan: Mapping[str, Any],
    *,
    board_token: str,
    discovered_at: datetime,
    policy_checked_at: date,
    is_example: bool,
) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise GreenhouseBoardParseError("Greenhouse 공고 항목은 객체여야 함")
    external_id = str(job.get("id", "")).strip()
    if not external_id.isdigit():
        raise GreenhouseBoardParseError("Greenhouse 공고 ID가 숫자가 아님")
    title = _required_text(job, "title")
    company = _required_text(job, "company_name")
    source_url = _required_text(job, "absolute_url")
    _validate_https_url(source_url)
    location = job.get("location")
    if not isinstance(location, dict):
        raise GreenhouseBoardParseError("Greenhouse location 객체가 필요함")
    location_text = _required_text(location, "name")
    employment_text = _employment_from_title(title)
    published_at = _optional_text(job.get("first_published"))
    deadline_text = _optional_text(job.get("application_deadline"))

    summary = {
        "title": title,
        "company": company,
        "experience_text": None,
        "education_text": None,
        "employment_text": employment_text,
        "location_text": location_text,
        "deadline_text": deadline_text,
    }
    unknowns = list(DEFAULT_UNKNOWNS)
    if employment_text is None:
        unknowns.append("고용 형태")
    if deadline_text is None:
        unknowns.append("마감일")

    return {
        "identity": {
            "discovery_id": f"{PROVIDER}-{board_token}-{external_id}",
            "provider": PROVIDER,
            "external_id": external_id,
        },
        "source": {
            "source_kind": "ats_api",
            "board_token": board_token,
            "source_url": source_url,
            "published_at": published_at,
            "discovered_at": discovered_at.isoformat(timespec="seconds"),
            "policy_checked_at": policy_checked_at.isoformat(),
        },
        "summary": summary,
        "availability": {
            "content_scope": "metadata_only",
            "detail_status": "available",
            "match_ready": False,
            "reason": "공식 ATS 상세 API가 있으나 목록 단계에서는 본문을 가져오지 않음",
        },
        "profile_relevance": build_profile_relevance(summary, search_plan),
        "deduplication": {
            "key": f"{PROVIDER}:{board_token}:{external_id}",
            "strategy": "provider_board_external_id",
        },
        "parse_notes": {
            "warnings": [],
            "unknowns": unknowns,
        },
        "metadata": {
            "schema_version": "1.0",
            "is_example": is_example,
            "contains_real_posting_content": not is_example,
        },
    }


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseBoardParseError(f"Greenhouse '{key}' 문자열이 필요함")
    return " ".join(value.split())


def _optional_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _validate_https_url(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise GreenhouseBoardParseError("Greenhouse 원문 URL은 인증정보 없는 HTTPS여야 함")


def _require_timezone(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise GreenhouseBoardParseError("discovered_at은 시간대가 포함되어야 함")


def _employment_from_title(title: str) -> str | None:
    normalized = title.casefold()
    if "intern" in normalized or "인턴" in title:
        return "internship"
    if "contract" in normalized or "계약직" in title:
        return "contract"
    if "part-time" in normalized or "part time" in normalized or "파트타임" in title:
        return "part_time"
    return None
