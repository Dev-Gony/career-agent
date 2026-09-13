"""Match job responsibilities to explicit profile evidence."""

from __future__ import annotations

from collections import Counter
from typing import Any


class ResponsibilityMatchError(ValueError):
    """Raised when responsibility evidence cannot be matched safely."""


_STRONG_LEVELS = {"work", "real_work", "project"}
_PARTIAL_LEVELS = {"basic", "learning"}


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ResponsibilityMatchError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise ResponsibilityMatchError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ResponsibilityMatchError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


def _contains(text: str, terms: tuple[str, ...]) -> bool:
    normalized = _normalized(text)
    return any(term in normalized for term in terms)


def _concept(text: str) -> str | None:
    normalized = _normalized(text)
    if "api" in normalized and ("연동" in normalized or "integration" in normalized):
        return "api_integration"
    if "llm" in normalized and ("도구" in normalized or "개발" in normalized):
        return "llm_tool"
    if "자동화" in normalized and (
        "모니터링" in normalized or "monitor" in normalized or "개선" in normalized
    ):
        return "automation_monitoring"
    if "자동화" in normalized or "automation" in normalized:
        return "workflow_automation"
    return None


def _validated_skills(profile: dict[str, Any]) -> list[dict[str, Any]]:
    skills: list[dict[str, Any]] = []
    for position, item in enumerate(_required_list(profile, "skills")):
        if not isinstance(item, dict):
            raise ResponsibilityMatchError(
                f"profile.skills[{position}]는 객체여야 합니다."
            )
        evidence = item.get("evidence", [])
        if not isinstance(evidence, list) or not all(
            isinstance(value, str) for value in evidence
        ):
            raise ResponsibilityMatchError("기술 evidence는 문자열 배열이어야 합니다.")
        skills.append(
            {
                "id": _required_text(item, "skill_id"),
                "name": _required_text(item, "name"),
                "level": _required_text(item, "level"),
                "evidence": [value.strip() for value in evidence if value.strip()],
                "notes": str(item.get("notes", "")).strip(),
            }
        )
    return skills


def _validated_projects(profile: dict[str, Any]) -> list[dict[str, Any]]:
    projects: list[dict[str, Any]] = []
    for position, item in enumerate(_required_list(profile, "projects")):
        if not isinstance(item, dict):
            raise ResponsibilityMatchError(
                f"profile.projects[{position}]는 객체여야 합니다."
            )
        technologies = item.get("technologies", [])
        capabilities = item.get("capabilities_demonstrated", [])
        if not isinstance(technologies, list) or not all(
            isinstance(value, str) for value in technologies
        ):
            raise ResponsibilityMatchError(
                "프로젝트 technologies는 문자열 배열이어야 합니다."
            )
        if not isinstance(capabilities, list) or not all(
            isinstance(value, str) for value in capabilities
        ):
            raise ResponsibilityMatchError(
                "프로젝트 capabilities_demonstrated는 문자열 배열이어야 합니다."
            )
        projects.append(
            {
                "id": _required_text(item, "project_id"),
                "name": _required_text(item, "name"),
                "status": _required_text(item, "status"),
                "problem": str(item.get("problem", "")).strip(),
                "solution": str(item.get("solution", "")).strip(),
                "technologies": [value.strip() for value in technologies if value.strip()],
                "capabilities": [value.strip() for value in capabilities if value.strip()],
            }
        )
    return projects


def _validated_behaviors(profile: dict[str, Any]) -> list[dict[str, Any]]:
    behaviors: list[dict[str, Any]] = []
    for position, item in enumerate(_required_list(profile, "behavior_evidence")):
        if not isinstance(item, dict):
            raise ResponsibilityMatchError(
                f"profile.behavior_evidence[{position}]는 객체여야 합니다."
            )
        pattern = item.get("pattern", [])
        if not isinstance(pattern, list) or not all(
            isinstance(value, str) for value in pattern
        ):
            raise ResponsibilityMatchError("행동 근거 pattern은 문자열 배열이어야 합니다.")
        behaviors.append(
            {
                "id": _required_text(item, "behavior_id"),
                "name": _required_text(item, "situation"),
                "level": _required_text(item, "evidence_level"),
                "pattern": [value.strip() for value in pattern if value.strip()],
                "interpretation": str(item.get("interpretation", "")).strip(),
            }
        )
    return behaviors


def _project_text(project: dict[str, Any]) -> str:
    return " ".join(
        [
            project["name"],
            project["problem"],
            project["solution"],
            *project["technologies"],
            *project["capabilities"],
        ]
    )


def _behavior_text(behavior: dict[str, Any]) -> str:
    return " ".join(
        [behavior["name"], behavior["interpretation"], *behavior["pattern"]]
    )


def _skill_is_related(skill: dict[str, Any], concept: str) -> bool:
    name = _normalized(skill["name"])
    if concept == "api_integration":
        return name in {"rest api", "restful api", "api integration"}
    if concept == "llm_tool":
        return name in {"llm api", "large language model api"}
    if concept == "automation_monitoring":
        return name == "github actions"
    return False


def _project_is_related(project: dict[str, Any], concept: str) -> bool:
    text = _project_text(project)
    if concept == "workflow_automation":
        return _contains(text, ("자동화", "automation", "예약 자동 실행"))
    if concept == "api_integration":
        return _contains(" ".join(project["technologies"]), ("api", "webhook"))
    if concept == "llm_tool":
        return _contains(text, ("llm", "gemini api", "요약 자동화"))
    if concept == "automation_monitoring":
        return _contains(
            text,
            ("실행 상태", "로그 확인", "상태 관리", "재시도", "모니터링"),
        )
    return False


def _behavior_is_related(behavior: dict[str, Any], concept: str) -> bool:
    text = _behavior_text(behavior)
    if concept == "workflow_automation":
        return _contains(text, ("자동화", "예약 자동 실행"))
    if concept == "automation_monitoring":
        return _contains(text, ("로그 확인", "원인 추적", "가설 검증", "정상 운영 확인"))
    return False


def _skill_evidence(skill: dict[str, Any]) -> dict[str, str]:
    detail = ", ".join(skill["evidence"]) or skill["notes"] or "프로필 기술 근거"
    return {
        "source_type": "skill",
        "source_name": skill["name"],
        "source_id": skill["id"],
        "evidence_level": skill["level"],
        "detail": detail,
    }


def _project_evidence(project: dict[str, Any]) -> dict[str, str]:
    detail = project["solution"] or ", ".join(project["capabilities"])
    return {
        "source_type": "project",
        "source_name": project["name"],
        "source_id": project["id"],
        "evidence_level": "project" if project["status"] == "completed" else "learning",
        "detail": detail,
    }


def _behavior_evidence(behavior: dict[str, Any]) -> dict[str, str]:
    return {
        "source_type": "behavior",
        "source_name": behavior["name"],
        "source_id": behavior["id"],
        "evidence_level": "observed_behavior",
        "detail": behavior["interpretation"] or ", ".join(behavior["pattern"]),
    }


def _assessment_reason(concept: str, result: str) -> str:
    if result == "strong_match":
        return {
            "workflow_automation": "반복 작업을 예약 실행되는 자동화 흐름으로 전환한 완료 프로젝트 증거가 있습니다.",
            "api_integration": "외부 API와 Webhook을 실제 프로젝트에서 연동한 직접 증거가 있습니다.",
            "llm_tool": "LLM API를 사용해 실제 업무형 자동화 도구를 구현한 증거가 있습니다.",
            "automation_monitoring": "자동화 실패를 능동적으로 감지하고 알리는 운영 증거가 있습니다.",
        }[concept]
    if result == "match" and concept == "automation_monitoring":
        return "실행 상태와 로그 확인, 상태 관리 및 재시도 증거는 있지만 별도 실패 요약이나 능동 알림은 없습니다."
    if result == "partial":
        return "관련 학습 또는 계획 중 프로젝트는 있으나 동작이 확인된 직접 증거가 부족합니다."
    return "프로필에서 이 주요 업무를 수행했다는 근거를 확인할 수 없습니다."


def _assess_concept(
    concept: str | None,
    skills: list[dict[str, Any]],
    projects: list[dict[str, Any]],
    behaviors: list[dict[str, Any]],
) -> tuple[str, str, str, list[dict[str, str]], str | None]:
    if concept is None:
        return (
            "unknown",
            "none",
            "주요 업무의 의미를 현재 규칙으로 안전하게 해석할 수 없습니다.",
            [],
            None,
        )

    related_skills = [skill for skill in skills if _skill_is_related(skill, concept)]
    related_projects = [
        project for project in projects if _project_is_related(project, concept)
    ]
    related_behaviors = [
        behavior for behavior in behaviors if _behavior_is_related(behavior, concept)
    ]
    evidence = [_skill_evidence(skill) for skill in related_skills]
    evidence.extend(_project_evidence(project) for project in related_projects)
    evidence.extend(_behavior_evidence(behavior) for behavior in related_behaviors)

    completed_projects = [
        project for project in related_projects if project["status"] == "completed"
    ]
    strong_skills = [
        skill for skill in related_skills if skill["level"] in _STRONG_LEVELS
    ]
    partial_skills = [
        skill for skill in related_skills if skill["level"] in _PARTIAL_LEVELS
    ]
    planned_projects = [
        project for project in related_projects if project["status"] != "completed"
    ]

    if concept == "automation_monitoring" and (completed_projects or strong_skills):
        combined_text = " ".join(_project_text(project) for project in completed_projects)
        has_proactive_alert = _contains(
            combined_text, ("능동 알림", "실패 알림", "실패 요약", "failure alert")
        )
        result = "strong_match" if has_proactive_alert else "match"
        directness = "exact" if has_proactive_alert else "related"
        next_action = None
        if result == "match":
            next_action = "필요하면 개별 실패 요약과 능동 실패 알림을 기존 자동화에 추가"
        return (
            result,
            directness,
            _assessment_reason(concept, result),
            evidence,
            next_action,
        )

    if completed_projects or strong_skills:
        return (
            "strong_match",
            "exact",
            _assessment_reason(concept, "strong_match"),
            evidence,
            None,
        )
    if planned_projects or partial_skills:
        return (
            "partial",
            "related",
            _assessment_reason(concept, "partial"),
            evidence,
            "기존 프로젝트에서 해당 업무의 동작 결과와 증거를 보강",
        )
    if related_behaviors:
        return (
            "match",
            "related",
            "관련 행동 증거는 있으나 완료 프로젝트의 직접 증거는 확인되지 않습니다.",
            evidence,
            "행동 사례를 실제 결과물 또는 업무 성과 근거와 연결",
        )
    return (
        "unknown",
        "none",
        _assessment_reason(concept, "unknown"),
        [],
        None,
    )


def _confidence(result: str) -> str:
    if result in {"strong_match", "match"}:
        return "high"
    if result == "partial":
        return "medium"
    return "low"


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


def match_responsibilities(
    profile_document: dict[str, Any], posting_document: dict[str, Any]
) -> dict[str, Any]:
    """Match every responsibility in source order without inventing evidence."""

    if not isinstance(profile_document, dict) or not isinstance(posting_document, dict):
        raise ResponsibilityMatchError("프로필과 채용공고는 JSON 객체여야 합니다.")
    profile = _required_mapping(profile_document, "profile")
    posting = _required_mapping(posting_document, "job_posting")
    skills = _validated_skills(profile)
    projects = _validated_projects(profile)
    behaviors = _validated_behaviors(profile)
    seen_ids: set[str] = set()
    matches: list[dict[str, Any]] = []

    for position, item in enumerate(_required_list(posting, "responsibilities")):
        if not isinstance(item, dict):
            raise ResponsibilityMatchError(
                f"job_posting.responsibilities[{position}]는 객체여야 합니다."
            )
        source_id = _required_text(item, "responsibility_id")
        if source_id in seen_ids:
            raise ResponsibilityMatchError(f"중복 주요 업무 ID가 있습니다: {source_id}")
        seen_ids.add(source_id)
        text = _required_text(item, "text")
        result, directness, reason, evidence, next_action = _assess_concept(
            _concept(text), skills, projects, behaviors
        )
        matches.append(
            {
                "requirement": {
                    "source_section": "responsibilities",
                    "source_id": source_id,
                    "type": "responsibility",
                    "name": text,
                    "evidence_text": text,
                },
                "assessment": {
                    "result": result,
                    "directness": directness,
                    "confidence": _confidence(result),
                    "reason": reason,
                },
                "user_evidence": evidence,
                "unknowns": [f"{text} 수행 경험"] if result == "unknown" else [],
                "next_action": next_action
                or (
                    f"프로필 자료에서 {text} 수행 경험을 추가 확인"
                    if result == "unknown"
                    else None
                ),
            }
        )

    return {
        "scope": "responsibilities_only",
        "summary": _summarize(matches),
        "responsibility_matches": matches,
    }
