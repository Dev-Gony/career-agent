"""Application recommendation rules based on completed match sections."""

from __future__ import annotations

from typing import Any


class RecommendationError(ValueError):
    """Raised when a recommendation cannot be generated safely."""


_MATCH_RESULTS = {"strong_match", "match", "partial", "gap", "unknown"}
_ELIGIBILITY_STATUSES = {"eligible", "conditional", "ineligible", "unknown"}
_INFORMATION_LEVELS = {"sufficient", "partial", "insufficient"}


def _require_match_list(value: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise RecommendationError(f"'{name}' 배열이 필요합니다.")
    for position, item in enumerate(value):
        if not isinstance(item, dict):
            raise RecommendationError(f"{name}[{position}]는 객체여야 합니다.")
        requirement = item.get("requirement")
        assessment = item.get("assessment")
        if not isinstance(requirement, dict) or not isinstance(assessment, dict):
            raise RecommendationError(
                f"{name}[{position}]에 requirement와 assessment 객체가 필요합니다."
            )
        result = assessment.get("result")
        if result not in _MATCH_RESULTS:
            raise RecommendationError(
                f"{name}[{position}]의 판정 값을 해석할 수 없습니다: {result}"
            )
        if not isinstance(requirement.get("name"), str) or not requirement["name"].strip():
            raise RecommendationError(f"{name}[{position}]에 조건 이름이 필요합니다.")
    return value


def _require_eligibility(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RecommendationError("'eligibility' 객체가 필요합니다.")
    status = value.get("status")
    if status not in _ELIGIBILITY_STATUSES:
        raise RecommendationError(f"지원 가능 상태를 해석할 수 없습니다: {status}")
    conditions = value.get("conditions")
    if not isinstance(conditions, list):
        raise RecommendationError("eligibility.conditions 배열이 필요합니다.")
    return value


def _require_information_level(value: Any) -> str:
    if not isinstance(value, dict):
        raise RecommendationError("'job_posting_information' 객체가 필요합니다.")
    level = value.get("level")
    if level not in _INFORMATION_LEVELS:
        raise RecommendationError(f"공고 정보 충분도를 해석할 수 없습니다: {level}")
    return str(level)


def _names_with_result(matches: list[dict[str, Any]], results: set[str]) -> list[str]:
    return [
        item["requirement"]["name"]
        for item in matches
        if item["assessment"]["result"] in results
    ]


def _eligibility_condition_names(
    eligibility: dict[str, Any], result: str
) -> list[str]:
    names: list[str] = []
    for condition in eligibility["conditions"]:
        if not isinstance(condition, dict):
            raise RecommendationError("eligibility.conditions 항목은 객체여야 합니다.")
        if condition.get("result") == result:
            condition_type = condition.get("type")
            names.append(str(condition_type or "미분류 조건"))
    return names


def _join_names(names: list[str]) -> str:
    return ", ".join(names)


def _preferred_cautions(preferred_matches: list[dict[str, Any]]) -> list[str]:
    cautions: list[str] = []
    gaps = _names_with_result(preferred_matches, {"gap"})
    uncertain = _names_with_result(preferred_matches, {"partial", "unknown"})
    if gaps:
        cautions.append(
            f"{_join_names(gaps)}는 우대 조건이지만 현재 요구 수준의 직접 증거가 부족합니다."
        )
    if uncertain:
        cautions.append(
            f"{_join_names(uncertain)} 우대 조건은 추가 확인 또는 증거 보강이 필요합니다."
        )
    return cautions


def _recommendation_for(
    required_matches: list[dict[str, Any]], eligibility: dict[str, Any]
) -> tuple[str, str, list[str], list[str]]:
    eligibility_status = eligibility["status"]
    required_gaps = _names_with_result(required_matches, {"gap"})
    required_uncertain = _names_with_result(required_matches, {"partial", "unknown"})
    strong_count = len(_names_with_result(required_matches, {"strong_match"}))
    matched_count = len(_names_with_result(required_matches, {"strong_match", "match"}))

    if eligibility_status == "ineligible":
        blockers = _eligibility_condition_names(eligibility, "not_met")
        return (
            "현재는 우선순위 낮음",
            "high",
            [f"확인된 지원 불가 조건이 있습니다: {_join_names(blockers)}."],
            ["지원 전 공고 조건 또는 사용자 정보를 다시 확인합니다."],
        )

    if required_gaps:
        return (
            "역량 보완 후 지원",
            "high",
            [f"필수 조건에 확인된 역량 부족이 있습니다: {_join_names(required_gaps)}."],
            ["기존 프로젝트 확장으로 필수 역량을 증명할 수 있는지 먼저 검토합니다."],
        )

    if eligibility_status in {"conditional", "unknown"} or required_uncertain:
        reasons: list[str] = []
        next_steps: list[str] = []
        if required_uncertain:
            reasons.append(
                f"필수 조건의 충족 여부를 추가 확인해야 합니다: {_join_names(required_uncertain)}."
            )
            next_steps.append("지원 판단을 바꿀 수 있는 필수 조건부터 확인합니다.")
        if eligibility_status in {"conditional", "unknown"}:
            pending = _eligibility_condition_names(eligibility, "needs_confirmation")
            reasons.append(
                f"지원 가능 조건을 추가 확인해야 합니다: {_join_names(pending) or '미확인 조건'}."
            )
            next_steps.append("경력·학력·근무 조건 중 미확인 항목을 공고와 대조합니다.")
        return "조건부 지원", "medium", reasons, next_steps

    if required_matches and strong_count == len(required_matches):
        return (
            "적극 지원",
            "high",
            [
                f"필수 조건 {len(required_matches)}건 모두 실무 또는 프로젝트 기반 직접 증거가 있습니다.",
                "확인된 지원 불가 조건이 없습니다.",
            ],
            ["지원 준비를 진행하고 직접 증거를 자기소개서와 포트폴리오에 연결합니다."],
        )

    if required_matches and matched_count == len(required_matches):
        return (
            "지원 추천",
            "medium",
            [
                "필수 조건에 확인된 부족은 없고 관련 경험이 연결됩니다.",
                "확인된 지원 불가 조건이 없습니다.",
            ],
            ["직접성이 낮은 필수 조건의 근거를 지원 문서에서 구체화합니다."],
        )

    return (
        "조건부 지원",
        "low",
        ["필수 조건 판정이 충분하지 않아 현재 정보만으로 추천을 확정하기 어렵습니다."],
        ["공고의 필수 조건과 사용자 근거를 추가 확인합니다."],
    )


def build_application_recommendation(
    required_matches: Any,
    preferred_matches: Any,
    eligibility: Any,
    *,
    job_posting_information: Any,
    responsibility_matches: Any = None,
    responsibilities_evaluated: bool = False,
) -> dict[str, Any]:
    """Create a recommendation without treating it as hiring probability."""

    required = _require_match_list(required_matches, "required_matches")
    preferred = _require_match_list(preferred_matches, "preferred_matches")
    eligibility_result = _require_eligibility(eligibility)
    information_level = _require_information_level(job_posting_information)
    responsibilities = (
        _require_match_list(responsibility_matches, "responsibility_matches")
        if responsibilities_evaluated
        else []
    )
    decision, confidence, reasons, next_steps = _recommendation_for(
        required, eligibility_result
    )
    cautions = _preferred_cautions(preferred)
    if responsibilities_evaluated:
        responsibility_uncertain = _names_with_result(
            responsibilities, {"partial", "gap", "unknown"}
        )
        if responsibilities and not responsibility_uncertain:
            reasons.append(
                f"주요 업무 {len(responsibilities)}건 모두 프로젝트 또는 행동 증거와 연결됩니다."
            )
        else:
            cautions.append(
                "직접 근거가 부족한 주요 업무가 있습니다: "
                f"{_join_names(responsibility_uncertain) or '주요 업무 미확인'}."
            )
            if decision == "적극 지원":
                decision = "지원 추천"
                confidence = "medium"
            next_steps.append("근거가 부족한 주요 업무를 실제 프로젝트·경력 자료와 대조합니다.")
    else:
        cautions.append("공고의 주요 업무 적합도는 아직 별도로 평가하지 않았습니다.")
        next_steps.append("주요 업무와 사용자 프로젝트·경력 증거를 추가로 비교합니다.")

    if decision in {"현재는 우선순위 낮음", "역량 보완 후 지원"}:
        status = "NOT_RECOMMEND"
    elif information_level in {"partial", "insufficient"}:
        status = "HOLD"
        decision = "판단 보류"
        confidence = "low" if information_level == "insufficient" else "medium"
        reasons.insert(
            0,
            (
                "공고의 주요 업무와 필수 조건을 확인할 수 없어 추천을 확정하지 않습니다."
                if information_level == "insufficient"
                else "공고의 핵심 정보가 일부 부족해 확인 전에는 추천을 확정하지 않습니다."
            ),
        )
        next_steps.insert(0, "공고 원문에서 누락된 핵심 조건을 먼저 확인합니다.")
    elif decision == "조건부 지원":
        status = "HOLD"
    else:
        status = "RECOMMEND"

    return {
        "status": status,
        "decision": decision,
        "confidence": confidence,
        "reasons": reasons,
        "recommendation_reason": reasons[0],
        "cautions": cautions,
        "next_steps": next_steps,
        "interpretation": "현재 프로필과 공고 조건의 비교 결과이며 합격 가능성 예측이 아닙니다.",
    }
