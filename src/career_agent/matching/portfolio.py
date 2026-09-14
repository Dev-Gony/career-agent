"""Build one portfolio improvement from confirmed or direct evidence."""

from __future__ import annotations

from typing import Any


class PortfolioRecommendationError(ValueError):
    """Raised when a portfolio recommendation cannot be built safely."""


_MAX_RECOMMENDATIONS = 1


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise PortfolioRecommendationError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise PortfolioRecommendationError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PortfolioRecommendationError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _completed_project_names(profile_document: dict[str, Any]) -> list[str]:
    profile = _required_mapping(profile_document, "profile")
    names: list[str] = []
    for position, project in enumerate(_required_list(profile, "projects")):
        if not isinstance(project, dict):
            raise PortfolioRecommendationError(
                f"profile.projects[{position}]는 객체여야 합니다."
            )
        if project.get("status") == "completed":
            names.append(_required_text(project, "name"))
    return names


def _from_learning_action(
    recommendation: dict[str, Any], completed_projects: list[str]
) -> dict[str, str] | None:
    if not completed_projects:
        return None
    topic = _required_text(recommendation, "topic")
    action = _required_text(recommendation, "action")
    target_project = next(
        (name for name in completed_projects if name in action),
        completed_projects[0],
    )
    deliverable = _required_text(recommendation, "deliverable")
    completion_evidence = _required_text(recommendation, "completion_evidence")
    return {
        "target_project": target_project,
        "related_gap": f"{topic}의 실제 프로젝트 적용 증거 부족",
        "change": action,
        "reason": (
            "새 프로젝트를 추가하지 않고 기존 결과물의 재현성과 기술 증거를 "
            "함께 강화할 수 있음"
        ),
        "expected_evidence": f"{deliverable}; {completion_evidence}",
    }


def _project_evidence_name(
    match: dict[str, Any], completed_projects: list[str]
) -> str | None:
    evidence_items = match.get("user_evidence", [])
    if not isinstance(evidence_items, list):
        raise PortfolioRecommendationError("user_evidence는 배열이어야 합니다.")
    for evidence in evidence_items:
        if not isinstance(evidence, dict):
            continue
        if evidence.get("source_type") != "project":
            continue
        source_name = evidence.get("source_name")
        if isinstance(source_name, str) and source_name in completed_projects:
            return source_name
    return None


def _from_responsibility_match(
    match: dict[str, Any], completed_projects: list[str]
) -> dict[str, str] | None:
    requirement = _required_mapping(match, "requirement")
    assessment = _required_mapping(match, "assessment")
    if assessment.get("result") not in {"match", "partial"}:
        return None
    target_project = _project_evidence_name(match, completed_projects)
    if target_project is None:
        return None
    next_action = match.get("next_action")
    if not isinstance(next_action, str) or not next_action.strip():
        return None
    responsibility = _required_text(requirement, "name")
    return {
        "target_project": target_project,
        "related_gap": f"{responsibility}의 직접 증거 보강",
        "change": next_action.strip(),
        "reason": (
            f"{assessment.get('reason', '관련 경험은 있으나 증거 보강이 필요함')} "
            "기존 프로젝트에서 보강하면 새 프로젝트 없이 차이를 보여줄 수 있음"
        ),
        "expected_evidence": (
            f"{target_project} 변경 코드, 실행 방법과 개선 기능의 실제 동작 로그"
        ),
    }


def build_portfolio_recommendations(
    profile_document: dict[str, Any],
    learning_recommendations: list[dict[str, Any]],
    responsibility_matches: list[dict[str, Any]],
) -> list[dict[str, str]]:
    """Return at most one existing-project improvement with verifiable evidence."""

    if not isinstance(profile_document, dict):
        raise PortfolioRecommendationError("프로필은 JSON 객체여야 합니다.")
    if not isinstance(learning_recommendations, list) or not isinstance(
        responsibility_matches, list
    ):
        raise PortfolioRecommendationError("학습 추천과 업무 판정은 배열이어야 합니다.")

    completed_projects = _completed_project_names(profile_document)
    recommendations: list[dict[str, str]] = []

    for position, learning in enumerate(learning_recommendations):
        if not isinstance(learning, dict):
            raise PortfolioRecommendationError(
                f"learning_recommendations[{position}]는 객체여야 합니다."
            )
        recommendation = _from_learning_action(learning, completed_projects)
        if recommendation is not None:
            recommendations.append(recommendation)
            return recommendations[:_MAX_RECOMMENDATIONS]

    for position, match in enumerate(responsibility_matches):
        if not isinstance(match, dict):
            raise PortfolioRecommendationError(
                f"responsibility_matches[{position}]는 객체여야 합니다."
            )
        recommendation = _from_responsibility_match(match, completed_projects)
        if recommendation is not None:
            recommendations.append(recommendation)
            return recommendations[:_MAX_RECOMMENDATIONS]

    return recommendations
