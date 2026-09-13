"""Derive concise strengths, gaps, and unknowns from match evidence."""

from __future__ import annotations

from typing import Any


class MatchInsightsError(ValueError):
    """Raised when insight lists cannot be derived safely."""


_POSITIVE_RESULTS = {"strong_match", "match"}
_SOURCE_TYPE_PRIORITY = {
    "project": 0,
    "career": 1,
    "achievement": 1,
    "skill": 2,
    "behavior": 3,
}
_ELIGIBILITY_SUBJECT_LABELS = {
    "experience": "경력 연수",
    "education": "학력 조건",
    "employment": "고용 형태",
    "location": "근무 지역·방식",
}


def _validated_matches(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise MatchInsightsError(f"'{name}' 배열이 필요합니다.")
    for position, item in enumerate(value):
        if not isinstance(item, dict):
            raise MatchInsightsError(f"{name}[{position}]는 객체여야 합니다.")
        if not isinstance(item.get("requirement"), dict) or not isinstance(
            item.get("assessment"), dict
        ):
            raise MatchInsightsError(
                f"{name}[{position}]에 requirement와 assessment 객체가 필요합니다."
            )
        if not isinstance(item.get("user_evidence"), list):
            raise MatchInsightsError(f"{name}[{position}].user_evidence 배열이 필요합니다.")
    return value


def _validated_eligibility(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or not isinstance(value.get("conditions"), list):
        raise MatchInsightsError("eligibility와 conditions 배열이 필요합니다.")
    return value


def _source_title(source_type: str, source_name: str) -> str:
    if source_type == "project":
        return f"{source_name} 프로젝트 기반 직무 증거"
    if source_type == "skill":
        return f"{source_name} 활용 경험"
    if source_type == "behavior":
        return f"{source_name} 문제 해결 행동"
    return f"{source_name} 기반 직무 증거"


def _source_reason(source_type: str, condition_count: int) -> str:
    label = {
        "project": "완료 프로젝트",
        "skill": "기술 사용",
        "behavior": "행동 사례",
        "career": "실무 경력",
        "achievement": "업무 성과",
    }.get(source_type, "사용자")
    return f"공고 조건 {condition_count}건에 {label} 증거가 연결됩니다."


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def _build_strengths(all_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources: dict[str, dict[str, Any]] = {}
    for match in all_matches:
        if match["assessment"].get("result") not in _POSITIVE_RESULTS:
            continue
        requirement_name = str(match["requirement"].get("name", "")).strip()
        for evidence in match["user_evidence"]:
            if not isinstance(evidence, dict):
                raise MatchInsightsError("user_evidence 항목은 객체여야 합니다.")
            source_id = str(evidence.get("source_id", "")).strip()
            source_name = str(evidence.get("source_name", "")).strip()
            source_type = str(evidence.get("source_type", "")).strip()
            detail = str(evidence.get("detail", "")).strip()
            if not source_id or not source_name or not source_type:
                raise MatchInsightsError("사용자 근거에 source ID, 이름과 유형이 필요합니다.")
            source = sources.setdefault(
                source_id,
                {
                    "source_name": source_name,
                    "source_type": source_type,
                    "related_requirements": [],
                    "evidence": [],
                    "strong_count": 0,
                },
            )
            _append_unique(source["related_requirements"], requirement_name)
            _append_unique(source["evidence"], detail)
            if match["assessment"].get("result") == "strong_match":
                source["strong_count"] += 1

    ranked = sorted(
        sources.values(),
        key=lambda source: (
            -len(source["related_requirements"]),
            -source["strong_count"],
            _SOURCE_TYPE_PRIORITY.get(source["source_type"], 9),
            source["source_name"].casefold(),
        ),
    )
    return [
        {
            "title": _source_title(source["source_type"], source["source_name"]),
            "related_requirements": source["related_requirements"],
            "evidence": source["evidence"],
            "reason": _source_reason(
                source["source_type"], len(source["related_requirements"])
            ),
        }
        for source in ranked[:3]
    ]


def _gap_priority(source_section: str) -> str:
    if source_section == "preferred_qualifications":
        return "preferred_only"
    return "immediate"


def _build_gaps(
    required: list[dict[str, Any]],
    preferred: list[dict[str, Any]],
    responsibilities: list[dict[str, Any]],
    eligibility: dict[str, Any],
) -> list[dict[str, str]]:
    gaps: list[dict[str, str]] = []
    for match in [*required, *preferred, *responsibilities]:
        if match["assessment"].get("result") != "gap":
            continue
        requirement = match["requirement"]
        source_section = str(requirement.get("source_section", ""))
        gaps.append(
            {
                "name": str(requirement.get("name", "미분류 조건")),
                "priority": _gap_priority(source_section),
                "reason": str(match["assessment"].get("reason", "확인된 부족이 있습니다.")),
                "recommended_action": str(
                    match.get("next_action")
                    or "기존 프로젝트 확장으로 증명할 수 있는지 먼저 검토"
                ),
            }
        )

    for condition in eligibility["conditions"]:
        if not isinstance(condition, dict):
            raise MatchInsightsError("eligibility.conditions 항목은 객체여야 합니다.")
        if condition.get("result") != "not_met":
            continue
        condition_type = str(condition.get("type", "미분류 지원 조건"))
        gaps.append(
            {
                "name": condition_type,
                "priority": "blocking",
                "reason": str(condition.get("reason", "지원 가능 조건을 충족하지 못합니다.")),
                "recommended_action": "지원 전 공고 조건과 사용자 근거를 다시 확인",
            }
        )
    return gaps


def _unknown_impact(source_section: str) -> str:
    return {
        "requirements": "필수 조건 판정에 영향",
        "preferred_qualifications": "우대 조건 판정에만 영향",
        "responsibilities": "주요 업무 적합도 판정에 영향",
    }.get(source_section, "매칭 판정에 영향")


def _unknown_priority(source_section: str) -> str:
    return {
        "requirements": "critical",
        "eligibility": "critical",
        "responsibilities": "high",
        "preferred_qualifications": "low",
    }.get(source_section, "medium")


def _match_unknowns(
    matches: list[dict[str, Any]],
) -> list[dict[str, str]]:
    unknowns: list[dict[str, str]] = []
    for match in matches:
        result = match["assessment"].get("result")
        requirement = match["requirement"]
        source_section = str(requirement.get("source_section", "unknown"))
        requirement_name = str(requirement.get("name", "미분류 조건"))
        next_action = str(
            match.get("next_action")
            or f"{requirement_name} 관련 사용자 근거를 확인할 수 있는가"
        )
        if result == "unknown":
            subjects = [requirement_name]
        elif result == "partial":
            raw_unknowns = match.get("unknowns", [])
            if not isinstance(raw_unknowns, list) or not all(
                isinstance(item, str) for item in raw_unknowns
            ):
                raise MatchInsightsError("부분 일치 unknowns는 문자열 배열이어야 합니다.")
            subjects = [item.strip() for item in raw_unknowns if item.strip()]
        else:
            continue
        for subject in subjects:
            unknowns.append(
                {
                    "subject": subject,
                    "source": source_section,
                    "impact": _unknown_impact(source_section),
                    "priority": _unknown_priority(source_section),
                    "question": next_action,
                }
            )
    return unknowns


def _build_unknowns(
    required: list[dict[str, Any]],
    preferred: list[dict[str, Any]],
    responsibilities: list[dict[str, Any]],
    eligibility: dict[str, Any],
) -> list[dict[str, str]]:
    unknowns = _match_unknowns(required)

    for condition in eligibility["conditions"]:
        if not isinstance(condition, dict):
            raise MatchInsightsError("eligibility.conditions 항목은 객체여야 합니다.")
        if condition.get("result") != "needs_confirmation":
            continue
        condition_type = str(condition.get("type", "미분류 지원 조건"))
        subject = _ELIGIBILITY_SUBJECT_LABELS.get(condition_type, condition_type)
        unknowns.append(
            {
                "subject": subject,
                "source": "eligibility",
                "impact": "지원 가능 여부에 영향",
                "priority": _unknown_priority("eligibility"),
                "question": str(
                    condition.get("reason") or f"{subject} 조건을 확인할 수 있는가"
                ),
            }
        )
    unknowns.extend(_match_unknowns(responsibilities))
    unknowns.extend(_match_unknowns(preferred))
    return unknowns


def build_match_insights(
    required_matches: Any,
    preferred_matches: Any,
    responsibility_matches: Any,
    eligibility: Any,
) -> dict[str, Any]:
    """Build user-facing evidence lists without turning unknowns into gaps."""

    required = _validated_matches(required_matches, "required_matches")
    preferred = _validated_matches(preferred_matches, "preferred_matches")
    responsibilities = _validated_matches(
        responsibility_matches, "responsibility_matches"
    )
    eligibility_result = _validated_eligibility(eligibility)
    return {
        "strengths": _build_strengths([*required, *preferred, *responsibilities]),
        "gaps": _build_gaps(required, preferred, responsibilities, eligibility_result),
        "unknowns": _build_unknowns(
            required, preferred, responsibilities, eligibility_result
        ),
    }
