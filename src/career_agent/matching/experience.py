"""Deterministic matching for explicit experience requirements."""

from __future__ import annotations

from collections import Counter
from typing import Any


class ExperienceMatchError(ValueError):
    """Raised when profile or posting data cannot be matched safely."""


_STRONG_SKILL_LEVELS = {"work", "real_work", "project"}
_PARTIAL_SKILL_LEVELS = {"basic", "learning"}
_GAP_SKILL_LEVELS = {"exposure", "none"}

_EXPERIENCE_ALIASES = {
    "rest api integration": "rest_api_integration",
    "rest api 연동": "rest_api_integration",
    "api integration": "rest_api_integration",
    "automation project": "automation_project",
    "업무 자동화": "automation_project",
    "자동화 프로젝트": "automation_project",
}


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ExperienceMatchError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise ExperienceMatchError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ExperienceMatchError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _experience_concept(item: dict[str, Any]) -> str | None:
    name = _normalized(_required_text(item, "name"))
    if name in _EXPERIENCE_ALIASES:
        return _EXPERIENCE_ALIASES[name]

    evidence_text = _normalized(_required_text(item, "evidence_text"))
    if "api" in evidence_text and ("연동" in evidence_text or "integration" in evidence_text):
        return "rest_api_integration"
    if "자동화" in evidence_text and ("경험" in evidence_text or "프로젝트" in evidence_text):
        return "automation_project"
    return None


def _validate_skill(raw_skill: Any, position: int) -> dict[str, Any]:
    if not isinstance(raw_skill, dict):
        raise ExperienceMatchError(f"profile.skills[{position}]는 객체여야 합니다.")
    evidence = raw_skill.get("evidence", [])
    if not isinstance(evidence, list) or not all(
        isinstance(item, str) and item.strip() for item in evidence
    ):
        raise ExperienceMatchError("기술 evidence는 문자열 배열이어야 합니다.")
    return {
        "skill_id": _required_text(raw_skill, "skill_id"),
        "name": _required_text(raw_skill, "name"),
        "level": _required_text(raw_skill, "level"),
        "evidence": [item.strip() for item in evidence],
        "notes": str(raw_skill.get("notes", "")).strip(),
    }


def _validate_project(raw_project: Any, position: int) -> dict[str, Any]:
    if not isinstance(raw_project, dict):
        raise ExperienceMatchError(f"profile.projects[{position}]는 객체여야 합니다.")

    technologies = raw_project.get("technologies", [])
    capabilities = raw_project.get("capabilities_demonstrated", [])
    if not isinstance(technologies, list) or not all(
        isinstance(item, str) for item in technologies
    ):
        raise ExperienceMatchError("프로젝트 technologies는 문자열 배열이어야 합니다.")
    if not isinstance(capabilities, list) or not all(
        isinstance(item, str) for item in capabilities
    ):
        raise ExperienceMatchError(
            "프로젝트 capabilities_demonstrated는 문자열 배열이어야 합니다."
        )

    return {
        "project_id": _required_text(raw_project, "project_id"),
        "name": _required_text(raw_project, "name"),
        "status": _required_text(raw_project, "status"),
        "problem": str(raw_project.get("problem", "")).strip(),
        "solution": str(raw_project.get("solution", "")).strip(),
        "technologies": [item.strip() for item in technologies if item.strip()],
        "capabilities": [item.strip() for item in capabilities if item.strip()],
    }


def _validate_behavior(raw_behavior: Any, position: int) -> dict[str, Any]:
    if not isinstance(raw_behavior, dict):
        raise ExperienceMatchError(
            f"profile.behavior_evidence[{position}]는 객체여야 합니다."
        )
    pattern = raw_behavior.get("pattern", [])
    if not isinstance(pattern, list) or not all(isinstance(item, str) for item in pattern):
        raise ExperienceMatchError("행동 근거 pattern은 문자열 배열이어야 합니다.")
    return {
        "behavior_id": _required_text(raw_behavior, "behavior_id"),
        "situation": _required_text(raw_behavior, "situation"),
        "pattern": [item.strip() for item in pattern if item.strip()],
        "interpretation": str(raw_behavior.get("interpretation", "")).strip(),
        "evidence_level": _required_text(raw_behavior, "evidence_level"),
    }


def _contains_any(values: list[str], terms: tuple[str, ...]) -> bool:
    text = " ".join(_normalized(value) for value in values)
    return any(term in text for term in terms)


def _project_supports(project: dict[str, Any], concept: str) -> bool:
    if concept == "rest_api_integration":
        return _contains_any(project["technologies"], ("api", "webhook"))
    if concept == "automation_project":
        return _contains_any(
            [
                project["name"],
                project["problem"],
                project["solution"],
                *project["capabilities"],
            ],
            ("자동화", "automation", "예약 자동 실행"),
        )
    return False


def _behavior_supports(behavior: dict[str, Any], concept: str) -> bool:
    values = [
        behavior["situation"],
        behavior["interpretation"],
        *behavior["pattern"],
    ]
    if concept == "rest_api_integration":
        return _contains_any(values, ("api", "webhook", "외부 서비스 연동"))
    if concept == "automation_project":
        return _contains_any(values, ("자동화", "automation", "예약 자동 실행"))
    return False


def _skill_supports(skill: dict[str, Any], concept: str) -> bool:
    if concept != "rest_api_integration":
        return False
    return _normalized(skill["name"]) in {"rest api", "restful api", "api integration"}


def _skill_evidence(skill: dict[str, Any]) -> dict[str, str]:
    detail = ", ".join(skill["evidence"]) or skill["notes"] or "프로필 기술 항목"
    return {
        "source_type": "skill",
        "source_name": skill["name"],
        "source_id": skill["skill_id"],
        "evidence_level": skill["level"],
        "detail": detail,
    }


def _project_evidence(project: dict[str, Any], concept: str) -> dict[str, str]:
    if concept == "rest_api_integration":
        details = [
            technology
            for technology in project["technologies"]
            if "api" in _normalized(technology) or "webhook" in _normalized(technology)
        ]
        detail = f"외부 연동 기술 사용: {', '.join(details)}"
    else:
        detail = project["solution"] or ", ".join(project["capabilities"])
    return {
        "source_type": "project",
        "source_name": project["name"],
        "source_id": project["project_id"],
        "evidence_level": "project" if project["status"] == "completed" else "learning",
        "detail": detail,
    }


def _behavior_evidence(behavior: dict[str, Any]) -> dict[str, str]:
    detail = behavior["interpretation"] or ", ".join(behavior["pattern"])
    return {
        "source_type": "behavior",
        "source_name": behavior["situation"],
        "source_id": behavior["behavior_id"],
        "evidence_level": "observed_behavior",
        "detail": detail,
    }


def _assess_experience(
    concept: str | None,
    skills: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    behaviors: list[dict[str, Any]],
) -> tuple[str, str, str, list[dict[str, str]]]:
    if concept is None:
        return (
            "unknown",
            "none",
            "요구 경험의 의미를 현재 규칙으로 안전하게 해석할 수 없습니다.",
            [],
        )

    related_skills = [skill for skill in skills if _skill_supports(skill, concept)]
    related_projects = [
        project for project in projects if _project_supports(project, concept)
    ]
    related_behaviors = [
        behavior for behavior in behaviors if _behavior_supports(behavior, concept)
    ]
    completed_projects = [
        project for project in related_projects if project["status"] == "completed"
    ]
    strong_skills = [
        skill for skill in related_skills if skill["level"] in _STRONG_SKILL_LEVELS
    ]

    evidence = [*(_skill_evidence(skill) for skill in related_skills)]
    evidence.extend(_project_evidence(project, concept) for project in related_projects)
    evidence.extend(_behavior_evidence(behavior) for behavior in related_behaviors)

    if completed_projects or strong_skills:
        reason = (
            "완료된 프로젝트에서 외부 API 또는 Webhook을 연동한 직접 증거가 있습니다."
            if concept == "rest_api_integration"
            else "반복 작업을 동작하는 자동화 흐름으로 전환한 완료 프로젝트 증거가 있습니다."
        )
        return "strong_match", "exact", reason, evidence

    partial_skills = [
        skill for skill in related_skills if skill["level"] in _PARTIAL_SKILL_LEVELS
    ]
    planned_projects = [
        project for project in related_projects if project["status"] != "completed"
    ]
    if partial_skills or planned_projects:
        return (
            "partial",
            "related",
            "관련 학습 또는 계획 중 프로젝트는 있으나 완료된 사용 증거가 부족합니다.",
            evidence,
        )

    if related_behaviors:
        return (
            "match",
            "related",
            "관련 행동 사례는 있으나 완료 프로젝트의 직접 증거는 확인되지 않습니다.",
            evidence,
        )

    gap_skills = [
        skill for skill in related_skills if skill["level"] in _GAP_SKILL_LEVELS
    ]
    if gap_skills:
        return (
            "gap",
            "exact",
            "실제 사용 경험이 없다고 프로필에서 확인됩니다.",
            evidence,
        )

    return (
        "unknown",
        "none",
        "프로필에서 해당 경험의 보유 여부를 확인할 근거가 없습니다.",
        [],
    )


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


def _confidence_for(result: str) -> str:
    if result in {"strong_match", "gap"}:
        return "high"
    if result in {"match", "partial"}:
        return "medium"
    return "low"


def _assess_items(
    items: list[Any],
    *,
    source_section: str,
    id_field: str,
    skills: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    behaviors: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for position, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise ExperienceMatchError(
                f"job_posting.{source_section}[{position}]는 객체여야 합니다."
            )
        if raw_item.get("type") != "experience":
            continue

        source_id = _required_text(raw_item, id_field)
        name = _required_text(raw_item, "name")
        evidence_text = _required_text(raw_item, "evidence_text")
        result, directness, reason, user_evidence = _assess_experience(
            _experience_concept(raw_item), skills, projects, behaviors
        )
        unknowns = []
        next_action = None
        if result == "unknown":
            unknowns.append(f"{name}의 실제 수행 경험")
            next_action = f"프로필 자료에서 {name} 수행 경험을 추가 확인"
        elif result in {"partial", "gap"}:
            next_action = f"기존 프로젝트에서 {name}의 동작 결과와 증거를 보강"

        matches.append(
            {
                "requirement": {
                    "source_section": source_section,
                    "source_id": source_id,
                    "type": "experience",
                    "name": name,
                    "evidence_text": evidence_text,
                },
                "assessment": {
                    "result": result,
                    "directness": directness,
                    "confidence": _confidence_for(result),
                    "reason": reason,
                },
                "user_evidence": user_evidence,
                "unknowns": unknowns,
                "next_action": next_action,
            }
        )
    return matches


def match_experience_requirements(
    profile_document: dict[str, Any],
    posting_document: dict[str, Any],
) -> dict[str, Any]:
    """Match experience requirements to skills, projects, and behavior evidence."""

    if not isinstance(profile_document, dict) or not isinstance(posting_document, dict):
        raise ExperienceMatchError("프로필과 채용공고는 JSON 객체여야 합니다.")

    profile = _required_mapping(profile_document, "profile")
    posting = _required_mapping(posting_document, "job_posting")
    skills = [
        _validate_skill(skill, position)
        for position, skill in enumerate(_required_list(profile, "skills"))
    ]
    projects = [
        _validate_project(project, position)
        for position, project in enumerate(_required_list(profile, "projects"))
    ]
    behaviors = [
        _validate_behavior(behavior, position)
        for position, behavior in enumerate(
            _required_list(profile, "behavior_evidence")
        )
    ]

    required_matches = _assess_items(
        _required_list(posting, "requirements"),
        source_section="requirements",
        id_field="requirement_id",
        skills=skills,
        projects=projects,
        behaviors=behaviors,
    )
    preferred_matches = _assess_items(
        _required_list(posting, "preferred_qualifications"),
        source_section="preferred_qualifications",
        id_field="qualification_id",
        skills=skills,
        projects=projects,
        behaviors=behaviors,
    )

    return {
        "scope": "experience_requirements_only",
        "summary": {
            "required": _summarize(required_matches),
            "preferred": _summarize(preferred_matches),
        },
        "required_matches": required_matches,
        "preferred_matches": preferred_matches,
    }
