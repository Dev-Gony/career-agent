"""Build one evidence-backed learning action for the personal MVP."""

from __future__ import annotations

from typing import Any


class LearningRecommendationError(ValueError):
    """Raised when a learning recommendation cannot be built safely."""


_LEARNABLE_TYPES = {"skill", "cloud"}
_MAX_RECOMMENDATIONS = 1


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise LearningRecommendationError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise LearningRecommendationError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise LearningRecommendationError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _completed_projects(profile: dict[str, Any]) -> list[dict[str, Any]]:
    projects = _required_list(profile, "projects")
    completed: list[dict[str, Any]] = []
    for position, project in enumerate(projects):
        if not isinstance(project, dict):
            raise LearningRecommendationError(
                f"profile.projects[{position}]는 객체여야 합니다."
            )
        if project.get("status") == "completed":
            _required_text(project, "project_id")
            _required_text(project, "name")
            completed.append(project)
    return completed


def _skill_index(profile: dict[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for position, skill in enumerate(_required_list(profile, "skills")):
        if not isinstance(skill, dict):
            raise LearningRecommendationError(
                f"profile.skills[{position}]는 객체여야 합니다."
            )
        name = _required_text(skill, "name")
        index[" ".join(name.casefold().split())] = skill
    return index


def _project_score(project: dict[str, Any], requirement_name: str) -> tuple[int, str]:
    searchable_parts = [
        str(project.get("problem", "")),
        str(project.get("solution", "")),
        *[str(item) for item in project.get("technologies", [])],
        *[str(item) for item in project.get("capabilities_demonstrated", [])],
    ]
    searchable = " ".join(searchable_parts).casefold()
    tokens = {
        token for token in requirement_name.casefold().replace("/", " ").split() if token
    }
    overlap = sum(token in searchable for token in tokens)
    return overlap, _required_text(project, "project_id")


def _select_project(
    projects: list[dict[str, Any]], requirement_name: str
) -> dict[str, Any] | None:
    if not projects:
        return None
    return max(projects, key=lambda item: _project_score(item, requirement_name))


def _profile_evidence(skill: dict[str, Any] | None) -> str:
    if skill is None:
        return "해당 기술의 실제 적용 증거가 없음"

    evidence = skill.get("evidence", [])
    if not isinstance(evidence, list):
        raise LearningRecommendationError("profile.skills.evidence는 배열이어야 합니다.")
    evidence_text = ", ".join(
        item.strip() for item in evidence if isinstance(item, str) and item.strip()
    )
    notes = str(skill.get("notes", "")).strip()
    return notes or evidence_text or "실제 적용 증거가 부족함"


def _eligible_gap_matches(
    required_matches: list[dict[str, Any]],
    preferred_matches: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], str]]:
    candidates: list[tuple[dict[str, Any], str]] = []
    for priority, matches in (
        ("immediate", required_matches),
        ("preferred_only", preferred_matches),
    ):
        for position, match in enumerate(matches):
            if not isinstance(match, dict):
                raise LearningRecommendationError(
                    f"매칭 결과[{position}]는 객체여야 합니다."
                )
            requirement = _required_mapping(match, "requirement")
            assessment = _required_mapping(match, "assessment")
            if assessment.get("result") != "gap":
                continue
            requirement_type = _required_text(requirement, "type")
            if requirement_type not in _LEARNABLE_TYPES:
                continue
            if priority == "preferred_only" and requirement_type == "cloud":
                continue
            candidates.append((match, priority))
    return candidates


def build_learning_recommendations(
    profile_document: dict[str, Any],
    required_matches: list[dict[str, Any]],
    preferred_matches: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Turn confirmed skill gaps into a small, verifiable project action.

    Unknown facts and unsupported partial matches are intentionally excluded. A
    preferred-only cloud gap is also deferred until repeated posting demand can
    be measured, because the first personal MVP does not track that frequency yet.
    """

    if not isinstance(profile_document, dict):
        raise LearningRecommendationError("프로필은 JSON 객체여야 합니다.")
    if not isinstance(required_matches, list) or not isinstance(
        preferred_matches, list
    ):
        raise LearningRecommendationError("필수·우대 판정은 배열이어야 합니다.")

    profile = _required_mapping(profile_document, "profile")
    projects = _completed_projects(profile)
    skills = _skill_index(profile)
    recommendations: list[dict[str, str]] = []

    for match, priority in _eligible_gap_matches(
        required_matches, preferred_matches
    )[:_MAX_RECOMMENDATIONS]:
        requirement = _required_mapping(match, "requirement")
        topic = _required_text(requirement, "name")
        skill = skills.get(" ".join(topic.casefold().split()))
        evidence = _profile_evidence(skill)
        project = _select_project(projects, topic)

        if project is None:
            action = f"{topic}의 최소 동작 예제를 만들고 공고 요구와 연결"
            deliverable = f"{topic} 적용 코드·설정과 짧은 실행 문서"
            completion_evidence = f"새 환경에서 {topic} 최소 예제 실행 성공 로그"
        else:
            project_name = _required_text(project, "name")
            action = f"기존 {project_name} 프로젝트에 {topic} 적용 후 핵심 흐름 재실행"
            deliverable = f"{project_name}의 {topic} 적용 코드·설정과 실행 문서"
            completion_evidence = (
                f"새 환경에서 {project_name} 핵심 흐름을 재현한 성공 로그"
            )

        condition = "필수" if priority == "immediate" else "우대"
        recommendations.append(
            {
                "topic": topic,
                "priority": priority,
                "based_on": f"공고의 {condition} 조건이며 프로필에는 {evidence}",
                "action": action,
                "deliverable": deliverable,
                "completion_evidence": completion_evidence,
            }
        )

    return recommendations
