"""Deterministic matching for explicit technology requirements."""

from __future__ import annotations

from collections import Counter
from typing import Any


class TechnologyMatchError(ValueError):
    """Raised when profile or posting data cannot be matched safely."""


_TECHNOLOGY_TYPES = {"skill", "cloud"}
_STRONG_LEVELS = {"work", "real_work", "project"}
_PARTIAL_LEVELS = {"basic", "learning"}
_GAP_LEVELS = {"exposure", "none"}
_ALIASES = {
    "rest api integration": "rest api",
    "restful api": "rest api",
}


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise TechnologyMatchError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise TechnologyMatchError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TechnologyMatchError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _canonical_name(name: str) -> str:
    normalized = " ".join(name.casefold().split())
    return _ALIASES.get(normalized, normalized)


def _build_skill_index(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    skills = _required_list(profile, "skills")
    index: dict[str, dict[str, Any]] = {}

    for position, raw_skill in enumerate(skills):
        if not isinstance(raw_skill, dict):
            raise TechnologyMatchError(
                f"profile.skills[{position}]는 객체여야 합니다."
            )

        skill_id = _required_text(raw_skill, "skill_id")
        name = _required_text(raw_skill, "name")
        level = _required_text(raw_skill, "level")
        canonical = _canonical_name(name)
        if canonical in index:
            raise TechnologyMatchError(
                f"중복 기술 이름을 안전하게 판정할 수 없습니다: {name}"
            )

        evidence = raw_skill.get("evidence", [])
        if not isinstance(evidence, list) or not all(
            isinstance(item, str) and item.strip() for item in evidence
        ):
            raise TechnologyMatchError(
                f"'{skill_id}'의 evidence는 비어 있지 않은 문자열 배열이어야 합니다."
            )

        index[canonical] = {
            "skill_id": skill_id,
            "name": name,
            "level": level,
            "evidence": [item.strip() for item in evidence],
            "notes": str(raw_skill.get("notes", "")).strip(),
        }

    return index


def _classify_skill(skill: dict[str, Any] | None) -> tuple[str, str, str]:
    if skill is None:
        return (
            "unknown",
            "none",
            "프로필에 해당 기술의 보유 수준을 확인할 정보가 없습니다.",
        )

    level = skill["level"]
    if level in _STRONG_LEVELS:
        return (
            "strong_match",
            "exact",
            "실무 또는 동작이 확인된 프로젝트 수준의 직접 증거가 있습니다.",
        )
    if level in _PARTIAL_LEVELS:
        return (
            "partial",
            "exact",
            "학습 또는 기본 사용 경험은 있으나 실무·프로젝트 수준의 증거가 부족합니다.",
        )
    if level in _GAP_LEVELS:
        return (
            "gap",
            "exact",
            "노출 경험만 있거나 실제 사용 경험이 없다고 프로필에서 확인됩니다.",
        )
    return (
        "unknown",
        "none",
        f"프로필의 기술 수준 '{level}'을 현재 규칙으로 안전하게 해석할 수 없습니다.",
    )


def _build_evidence(skill: dict[str, Any] | None) -> list[dict[str, str]]:
    if skill is None:
        return []

    details = skill["evidence"] or [skill["notes"]]
    return [
        {
            "source_type": "skill",
            "source_name": skill["name"],
            "source_id": skill["skill_id"],
            "evidence_level": skill["level"],
            "detail": detail,
        }
        for detail in details
        if detail
    ]


def _assess_items(
    items: list[Any],
    *,
    source_section: str,
    id_field: str,
    skill_index: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []

    for position, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise TechnologyMatchError(
                f"job_posting.{source_section}[{position}]는 객체여야 합니다."
            )
        if raw_item.get("type") not in _TECHNOLOGY_TYPES:
            continue

        source_id = _required_text(raw_item, id_field)
        name = _required_text(raw_item, "name")
        evidence_text = _required_text(raw_item, "evidence_text")
        skill = skill_index.get(_canonical_name(name))
        result, directness, reason = _classify_skill(skill)

        unknowns = []
        next_action = None
        if result == "unknown":
            unknowns.append(f"{name}의 실제 사용 경험")
            next_action = f"프로필 자료에서 {name} 사용 경험을 추가 확인"
        elif result == "gap":
            next_action = f"기존 프로젝트에서 {name}을 실제로 사용해 증거 확보"

        matches.append(
            {
                "requirement": {
                    "source_section": source_section,
                    "source_id": source_id,
                    "type": raw_item["type"],
                    "name": name,
                    "evidence_text": evidence_text,
                },
                "assessment": {
                    "result": result,
                    "directness": directness,
                    "confidence": "high" if result != "unknown" else "low",
                    "reason": reason,
                },
                "user_evidence": _build_evidence(skill),
                "unknowns": unknowns,
                "next_action": next_action,
            }
        )

    return matches


def _summarize(matches: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(item["assessment"]["result"] for item in matches)
    return {
        "total": len(matches),
        "strong_match": counts["strong_match"],
        "match": counts["match"],
        "partial": counts["partial"],
        "gap": counts["gap"],
        "unknown": counts["unknown"],
    }


def match_technology_requirements(
    profile_document: dict[str, Any],
    posting_document: dict[str, Any],
) -> dict[str, Any]:
    """Match explicit skill/cloud items without inferring missing experience."""

    if not isinstance(profile_document, dict) or not isinstance(posting_document, dict):
        raise TechnologyMatchError("프로필과 채용공고는 JSON 객체여야 합니다.")

    profile = _required_mapping(profile_document, "profile")
    posting = _required_mapping(posting_document, "job_posting")
    skill_index = _build_skill_index(profile)

    required_matches = _assess_items(
        _required_list(posting, "requirements"),
        source_section="requirements",
        id_field="requirement_id",
        skill_index=skill_index,
    )
    preferred_matches = _assess_items(
        _required_list(posting, "preferred_qualifications"),
        source_section="preferred_qualifications",
        id_field="qualification_id",
        skill_index=skill_index,
    )

    return {
        "scope": "technology_requirements_only",
        "summary": {
            "required": _summarize(required_matches),
            "preferred": _summarize(preferred_matches),
        },
        "required_matches": required_matches,
        "preferred_matches": preferred_matches,
    }
