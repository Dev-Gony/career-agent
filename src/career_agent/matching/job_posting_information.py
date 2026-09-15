"""Assess whether a job posting contains enough explicit information to compare."""

from __future__ import annotations

from typing import Any


class JobPostingInformationError(ValueError):
    """Raised when job-posting information cannot be assessed safely."""


_UNKNOWN_TEXTS = {
    "",
    "unknown",
    "미상",
    "미확인",
    "경력 연수 미확인",
}


def _mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise JobPostingInformationError(f"'{key}' 객체가 필요합니다.")
    return value


def _items(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise JobPostingInformationError(f"'{key}' 배열이 필요합니다.")
    return value


def _known_text(value: Any) -> bool:
    return isinstance(value, str) and value.strip().casefold() not in _UNKNOWN_TEXTS


def _has_text_item(items: list[Any], key: str) -> bool:
    return any(isinstance(item, dict) and _known_text(item.get(key)) for item in items)


def _has_explicit_experience(experience: dict[str, Any]) -> bool:
    minimum = experience.get("minimum_years")
    maximum = experience.get("maximum_years")
    return (
        isinstance(minimum, (int, float))
        and not isinstance(minimum, bool)
        or isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        or _known_text(experience.get("level_text"))
    )


def assess_job_posting_information(posting_document: Any) -> dict[str, Any]:
    """Classify explicit JD coverage without inferring absent information."""

    if not isinstance(posting_document, dict):
        raise JobPostingInformationError("채용공고는 JSON 객체여야 합니다.")
    posting = _mapping(posting_document, "job_posting")
    identity = _mapping(posting, "identity")
    company = _mapping(posting, "company")
    experience = _mapping(posting, "experience")
    employment = _mapping(posting, "employment")
    location = _mapping(posting, "location")
    responsibilities = _items(posting, "responsibilities")
    requirements = _items(posting, "requirements")
    preferred = _items(posting, "preferred_qualifications")

    field_presence = {
        "company": _known_text(company.get("name")),
        "position": _known_text(identity.get("title")),
        "responsibilities": _has_text_item(responsibilities, "text"),
        "required_qualifications": _has_text_item(requirements, "evidence_text"),
        "preferred_qualifications": _has_text_item(preferred, "evidence_text"),
        "experience": _has_explicit_experience(experience),
        "employment": _known_text(employment.get("type")),
        "location": _known_text(location.get("region")),
    }
    confirmed_fields = [name for name, present in field_presence.items() if present]
    missing_fields = [name for name, present in field_presence.items() if not present]

    has_responsibilities = field_presence["responsibilities"]
    has_requirements = field_presence["required_qualifications"]
    supporting_count = sum(
        field_presence[name] for name in ("experience", "employment", "location")
    )

    if not has_responsibilities and not has_requirements:
        level = "insufficient"
        reasons = [
            "공고에서 주요 업무와 필수 조건을 모두 확인할 수 없어 적합도를 확정할 수 없습니다."
        ]
    elif (
        has_responsibilities
        and has_requirements
        and field_presence["company"]
        and field_presence["position"]
        and supporting_count >= 2
    ):
        level = "sufficient"
        reasons = [
            "회사·직무·주요 업무·필수 조건과 핵심 근무 조건이 명시되어 있습니다."
        ]
    else:
        level = "partial"
        reasons = [
            "일부 비교 근거는 확인되지만 핵심 공고 정보가 빠져 있어 제한적으로만 판단할 수 있습니다."
        ]

    return {
        "level": level,
        "confirmed_fields": confirmed_fields,
        "missing_fields": missing_fields,
        "reasons": reasons,
        "interpretation": "공고 정보의 명시 수준이며 사용자와의 적합도 판정이 아닙니다.",
    }
