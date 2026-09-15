"""Profile-derived ranking shared by metadata discovery sources."""

from __future__ import annotations

from typing import Any, Mapping


_EMPLOYMENT_ALIASES = {
    "full_time": "full_time",
    "full-time": "full_time",
    "정규직": "full_time",
    "internship": "internship",
    "intern": "internship",
    "인턴": "internship",
    "contract": "contract",
    "contractor": "contract",
    "계약직": "contract",
    "part_time": "part_time",
    "part-time": "part_time",
    "파트타임": "part_time",
}
_LOCATION_TERMS = {
    "서울": ("서울", "seoul"),
    "경기": ("경기", "gyeonggi"),
    "인천": ("인천", "incheon"),
}
_NON_OPENING_TITLE_TERMS = (
    "expression of interest",
    "채용관심등록",
    "talent pool",
    "talent community",
    "general application",
    "인재풀",
)


def non_opening_title_signal(title: str | None) -> str | None:
    """Return an explicit title signal for talent pools or general applications."""

    normalized = (title or "").casefold()
    return next(
        (term for term in _NON_OPENING_TITLE_TERMS if term in normalized),
        None,
    )


def build_profile_relevance(
    summary: Mapping[str, str | None], search_plan: Mapping[str, Any]
) -> dict[str, Any]:
    """Rank one metadata candidate without treating it as final job fit."""

    plan = search_plan.get("job_search_plan", search_plan)
    title = (summary.get("title") or "").casefold()
    non_opening_signal = non_opening_title_signal(summary.get("title"))
    related_role_ids: list[str] = []
    matched_terms: list[str] = []
    matched_priorities: list[int | str] = []

    for axis in plan.get("role_axes", []):
        term = next(
            (
                candidate
                for candidate in axis.get("discovery_terms", [])
                if candidate.casefold() in title
            ),
            None,
        )
        if term is None:
            continue
        related_role_ids.append(axis["target_role_id"])
        matched_terms.append(term)
        matched_priorities.append(axis.get("priority", "conditional"))

    location_assessment = _assess_location(summary.get("location_text"), plan)
    employment_assessment = _assess_employment(
        summary.get("employment_text"), plan
    )
    priority = _discovery_priority(
        matched_priorities,
        location_assessment,
        employment_assessment,
    )
    confidence = "medium" if matched_terms else "low"

    if non_opening_signal is not None:
        priority = "low"
        confidence = "high"

    positive_signals = [
        f"제목에 검색 확장어 '{term}'가 포함됨" for term in matched_terms
    ]
    low_preference_signals = []
    if location_assessment == "mismatch":
        low_preference_signals.append("명시된 근무 지역이 현재 선호 지역 밖임")
    if employment_assessment == "mismatch":
        low_preference_signals.append("명시된 고용 형태가 현재 선호와 다름")
    if non_opening_signal is not None:
        low_preference_signals.append(
            "제목상 현재 모집 포지션이 아닌 인재풀 또는 채용 관심 등록임"
        )

    if non_opening_signal is not None:
        reason = (
            f"제목에 비정기 모집 신호 '{non_opening_signal}'가 명시되어 "
            "자동 상세 분석 대상에서 제외함"
        )
    elif priority == "high" and location_assessment == "match":
        reason = "최우선 목표 직무 표현이 제목에 직접 나타나고 선호 지역과 일치함"
    elif matched_terms and employment_assessment == "mismatch":
        reason = "목표 직무 표현이 제목에 있으나 명시된 고용 형태가 현재 선호와 다름"
    elif matched_terms and location_assessment == "mismatch":
        reason = "목표 직무 표현이 제목에 있으나 명시된 근무 지역이 현재 선호와 다름"
    elif matched_terms:
        reason = "목표 직무 표현이 제목에 있으나 상세 업무와 자격 요건 확인이 필요함"
    else:
        reason = "제목만으로 목표 직무 축과의 직접 관련성을 확인할 수 없음"

    return {
        "profile_id": plan["identity"]["profile_id"],
        "related_target_role_ids": related_role_ids,
        "positive_signals": positive_signals,
        "low_preference_signals": low_preference_signals,
        "location_assessment": location_assessment,
        "employment_assessment": employment_assessment,
        "priority": priority,
        "confidence": confidence,
        "reason": reason,
    }


def _assess_location(location_text: str | None, plan: Mapping[str, Any]) -> str:
    if not location_text:
        return "unknown"
    normalized_values = (
        plan.get("objective_preferences", {})
        .get("locations", {})
        .get("normalized_values", [])
    )
    normalized_location = location_text.casefold()
    for value in normalized_values:
        terms = _LOCATION_TERMS.get(str(value), (str(value),))
        if any(term.casefold() in normalized_location for term in terms):
            return "match"
    return "mismatch"


def _assess_employment(employment_text: str | None, plan: Mapping[str, Any]) -> str:
    if not employment_text:
        return "unknown"
    candidate = _EMPLOYMENT_ALIASES.get(employment_text.casefold())
    if candidate is None:
        return "unknown"
    preferences = (
        plan.get("objective_preferences", {})
        .get("employment_types", {})
        .get("values", [])
    )
    normalized_preferences = {
        _EMPLOYMENT_ALIASES.get(str(value).casefold()) for value in preferences
    }
    normalized_preferences.discard(None)
    if not normalized_preferences:
        return "unknown"
    return "match" if candidate in normalized_preferences else "mismatch"


def _discovery_priority(
    matched_priorities: list[int | str],
    location_assessment: str,
    employment_assessment: str,
) -> str:
    numeric_priorities = [value for value in matched_priorities if isinstance(value, int)]
    if not matched_priorities:
        return "review"
    if numeric_priorities and min(numeric_priorities) == 1:
        priority = "high"
    elif numeric_priorities and min(numeric_priorities) <= 3:
        priority = "medium"
    else:
        priority = "review"

    if "mismatch" in {location_assessment, employment_assessment}:
        return {"high": "medium", "medium": "low", "review": "low"}[priority]
    return priority
