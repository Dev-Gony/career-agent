"""Rule-based assessment of non-skill application conditions."""

from __future__ import annotations

from typing import Any


class EligibilityMatchError(ValueError):
    """Raised when eligibility data cannot be assessed safely."""


_EMPLOYMENT_LABELS = {
    "full_time": "정규직",
    "contract": "계약직",
    "internship": "인턴",
    "freelance": "프리랜서",
    "part_time": "파트타임",
    "unknown": "미확인",
}

_REGION_GROUPS = {
    "수도권": {"서울", "경기", "인천"},
}

_EDUCATION_LEVELS = {
    "고졸": 1,
    "high_school": 1,
    "전문학사": 2,
    "associate": 2,
    "학사": 3,
    "bachelor": 3,
    "석사": 4,
    "master": 4,
    "박사": 5,
    "doctorate": 5,
}


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise EligibilityMatchError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise EligibilityMatchError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EligibilityMatchError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _optional_number(document: dict[str, Any], key: str) -> float | None:
    value = document.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise EligibilityMatchError(f"'{key}'는 0 이상의 숫자 또는 null이어야 합니다.")
    return float(value)


def _display_years(value: float) -> str:
    return str(int(value)) if value.is_integer() else str(value)


def _profile_experience(profile: dict[str, Any]) -> tuple[float | None, bool, str]:
    history = profile.get("career_history")
    if isinstance(history, dict):
        years = _optional_number(history, "total_years")
        if years is None:
            years = _optional_number(history, "duration_years")
        has_history = bool(
            history.get("role")
            or history.get("responsibilities")
            or history.get("achievements")
        )
        if years is not None:
            return years, has_history or years > 0, f"총 경력 {_display_years(years)}년"
        if has_history:
            return None, True, "실무 경력 있음, 연수 미확인"
        return None, False, "경력 정보 미확인"

    if isinstance(history, list):
        if not history:
            return None, False, "경력 정보 미확인"
        durations: list[float] = []
        has_history = False
        for position, item in enumerate(history):
            if not isinstance(item, dict):
                raise EligibilityMatchError(
                    f"profile.career_history[{position}]는 객체여야 합니다."
                )
            duration = _optional_number(item, "duration_years")
            if duration is not None:
                durations.append(duration)
            has_history = has_history or bool(
                item.get("role")
                or item.get("responsibilities")
                or item.get("achievements")
            )
        if len(durations) == len(history):
            total = sum(durations)
            return total, has_history or total > 0, f"총 경력 {_display_years(total)}년"
        if has_history:
            return None, True, "실무 경력 있음, 연수 미확인"
        return None, False, "경력 정보 미확인"

    if history is None:
        return None, False, "경력 정보 미확인"
    raise EligibilityMatchError("'career_history'는 객체 또는 배열이어야 합니다.")


def _assess_experience(profile: dict[str, Any], posting: dict[str, Any]) -> dict[str, str]:
    condition = _required_mapping(posting, "experience")
    minimum = _optional_number(condition, "minimum_years")
    maximum = _optional_number(condition, "maximum_years")
    level_text = _required_text(condition, "level_text")
    years, has_history, user_value = _profile_experience(profile)

    if minimum is not None and maximum is not None and minimum > maximum:
        raise EligibilityMatchError("최소 경력 연수가 최대 경력 연수보다 큽니다.")

    if minimum == 0 and maximum is None:
        reason = "최소 경력 연수 제한이 없고 신입 또는 경력 지원이 가능합니다."
        if has_history:
            reason = "최소 경력 연수 제한이 없고 사용자 프로필에 실무 경력이 있습니다."
        return {
            "type": "experience",
            "posting_value": level_text,
            "user_value": user_value,
            "result": "met",
            "reason": reason,
        }

    if years is None:
        return {
            "type": "experience",
            "posting_value": level_text,
            "user_value": user_value,
            "result": "needs_confirmation",
            "reason": "공고에 경력 연수 조건이 있지만 사용자 경력 연수는 확인되지 않았습니다.",
        }

    if minimum is not None and years < minimum:
        return {
            "type": "experience",
            "posting_value": level_text,
            "user_value": user_value,
            "result": "not_met",
            "reason": f"확인된 경력 {_display_years(years)}년이 최소 요구 {_display_years(minimum)}년보다 짧습니다.",
        }
    if maximum is not None and years > maximum:
        return {
            "type": "experience",
            "posting_value": level_text,
            "user_value": user_value,
            "result": "not_met",
            "reason": f"확인된 경력 {_display_years(years)}년이 공고 최대 {_display_years(maximum)}년을 초과합니다.",
        }
    if minimum is None and maximum is None:
        return {
            "type": "experience",
            "posting_value": level_text,
            "user_value": user_value,
            "result": "needs_confirmation",
            "reason": "공고의 경력 연수 기준이 구조화되지 않아 추가 확인이 필요합니다.",
        }
    return {
        "type": "experience",
        "posting_value": level_text,
        "user_value": user_value,
        "result": "met",
        "reason": "확인된 경력 연수가 공고의 경력 범위에 포함됩니다.",
    }


def _education_label(level: Any) -> str:
    if isinstance(level, str) and level.strip():
        return level.strip()
    return "미확인"


def _assess_education(profile: dict[str, Any], posting: dict[str, Any]) -> dict[str, str]:
    condition = _required_mapping(posting, "education")
    required = condition.get("required")
    if not isinstance(required, bool):
        raise EligibilityMatchError("education.required는 true 또는 false여야 합니다.")
    posting_level = _education_label(condition.get("level"))

    if not required:
        return {
            "type": "education",
            "posting_value": "학력 필수 아님",
            "user_value": "확인하지 않음",
            "result": "not_applicable",
            "reason": "공고가 필수 학력 조건을 제시하지 않습니다.",
        }

    profile_education = profile.get("education")
    user_level = (
        _education_label(profile_education.get("level"))
        if isinstance(profile_education, dict)
        else "미확인"
    )
    required_rank = _EDUCATION_LEVELS.get(posting_level.casefold())
    user_rank = _EDUCATION_LEVELS.get(user_level.casefold())
    if required_rank is None or user_rank is None:
        return {
            "type": "education",
            "posting_value": posting_level,
            "user_value": user_level,
            "result": "needs_confirmation",
            "reason": "필수 학력 조건 또는 사용자 학력을 안전하게 비교할 정보가 부족합니다.",
        }
    if user_rank < required_rank:
        return {
            "type": "education",
            "posting_value": posting_level,
            "user_value": user_level,
            "result": "not_met",
            "reason": "확인된 사용자 학력이 공고의 필수 학력 수준보다 낮습니다.",
        }
    return {
        "type": "education",
        "posting_value": posting_level,
        "user_value": user_level,
        "result": "met",
        "reason": "확인된 사용자 학력이 공고의 필수 학력 수준을 충족합니다.",
    }


def _normalize_location(value: str) -> str:
    normalized = value.strip()
    suffixes = ("특별시", "광역시", "특별자치시", "특별자치도")
    for suffix in suffixes:
        if normalized.endswith(suffix):
            return normalized[: -len(suffix)]
    if normalized.endswith("도") and len(normalized) > 1:
        return normalized[:-1]
    return normalized


def _location_matches(preference: str, region: str) -> bool:
    normalized_preference = _normalize_location(preference)
    normalized_region = _normalize_location(region)
    if normalized_preference == normalized_region:
        return True
    return normalized_region in _REGION_GROUPS.get(normalized_preference, set())


def _assess_location(profile: dict[str, Any], posting: dict[str, Any]) -> dict[str, str]:
    condition = _required_mapping(posting, "location")
    region = _required_text(condition, "region")
    remote = _required_text(condition, "remote")
    basic = _required_mapping(profile, "basic")
    preferences = _required_list(basic, "location_preference")
    if not all(isinstance(item, str) and item.strip() for item in preferences):
        raise EligibilityMatchError("location_preference는 문자열 배열이어야 합니다.")

    posting_value = region if remote == "unknown" else f"{region}, {remote}"
    user_value = ", ".join(item.strip() for item in preferences) or "미확인"
    region_met = any(_location_matches(item, region) for item in preferences)
    remote_preference = basic.get("remote_preference")
    if remote != "unknown":
        if not isinstance(remote_preference, str) or not remote_preference.strip():
            return {
                "type": "location",
                "posting_value": posting_value,
                "user_value": user_value,
                "result": "needs_confirmation",
                "reason": "근무 지역은 비교했지만 공고의 원격·출근 방식에 대한 사용자 조건이 확인되지 않았습니다.",
            }
        normalized_remote_preference = remote_preference.strip().casefold()
        if normalized_remote_preference not in {"any", remote.casefold()}:
            return {
                "type": "location",
                "posting_value": posting_value,
                "user_value": f"{user_value}, {remote_preference}",
                "result": "needs_confirmation",
                "reason": "공고의 원격·출근 방식이 현재 선호와 달라 확인이 필요합니다.",
            }
    if region_met:
        return {
            "type": "location",
            "posting_value": posting_value,
            "user_value": f"{user_value} 선호",
            "result": "met",
            "reason": "근무 지역이 사용자의 선호 지역에 포함됩니다.",
        }
    return {
        "type": "location",
        "posting_value": posting_value,
        "user_value": user_value,
        "result": "needs_confirmation",
        "reason": "근무 지역이 현재 선호와 다르지만 선호는 지원 불가를 뜻하는 강제 조건이 아닙니다.",
    }


def _assess_employment(profile: dict[str, Any], posting: dict[str, Any]) -> dict[str, str]:
    condition = _required_mapping(posting, "employment")
    employment_type = _required_text(condition, "type")
    posting_label = _EMPLOYMENT_LABELS.get(employment_type, employment_type)
    basic = _required_mapping(profile, "basic")
    preferences = _required_list(basic, "employment_type_preference")
    if not all(isinstance(item, str) and item.strip() for item in preferences):
        raise EligibilityMatchError(
            "employment_type_preference는 문자열 배열이어야 합니다."
        )
    normalized_preferences = {_EMPLOYMENT_LABELS.get(item, item) for item in preferences}
    user_value = ", ".join(preferences) or "미확인"

    if employment_type == "unknown":
        return {
            "type": "employment",
            "posting_value": posting_label,
            "user_value": user_value,
            "result": "needs_confirmation",
            "reason": "공고의 고용 형태가 확인되지 않았습니다.",
        }
    if posting_label in normalized_preferences:
        return {
            "type": "employment",
            "posting_value": posting_label,
            "user_value": f"{user_value} 선호",
            "result": "met",
            "reason": "공고의 고용 형태가 사용자의 선호와 일치합니다.",
        }
    return {
        "type": "employment",
        "posting_value": posting_label,
        "user_value": user_value,
        "result": "needs_confirmation",
        "reason": "고용 형태가 현재 선호와 다르지만 선호는 지원 불가를 뜻하는 강제 조건이 아닙니다.",
    }


def _overall_status(conditions: list[dict[str, str]]) -> str:
    results = {condition["result"] for condition in conditions}
    if "not_met" in results:
        return "ineligible"
    if "needs_confirmation" in results:
        return "conditional"
    return "eligible"


def assess_eligibility(
    profile_document: dict[str, Any], posting_document: dict[str, Any]
) -> dict[str, Any]:
    """Assess experience, education, employment, and location independently."""

    if not isinstance(profile_document, dict) or not isinstance(posting_document, dict):
        raise EligibilityMatchError("프로필과 채용공고는 JSON 객체여야 합니다.")
    profile = _required_mapping(profile_document, "profile")
    posting = _required_mapping(posting_document, "job_posting")
    conditions = [
        _assess_experience(profile, posting),
        _assess_education(profile, posting),
        _assess_employment(profile, posting),
        _assess_location(profile, posting),
    ]
    return {
        "status": _overall_status(conditions),
        "conditions": conditions,
    }
