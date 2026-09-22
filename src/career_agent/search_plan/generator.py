"""Generate a conservative discovery plan from confirmed profile fields."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence


JOB_SEARCH_PLAN_SCHEMA_VERSION = "1.0"
JOB_SEARCH_PLAN_RULES_VERSION = "profile-evidence-v2"

_DEMONSTRATED_SKILL_LEVELS = frozenset({"basic", "project", "work"})
_LOCATION_NORMALIZATION = {
    "수도권": ("서울", "경기", "인천"),
}
_ROLE_DISCOVERY_TERM_TAXONOMY = {
    "role-ai-automation": (
        "AI 자동화",
        "업무 자동화",
        "워크플로 자동화",
        "Automation Engineer",
        "AI Agent",
    ),
    "role-ai-solutions": (
        "AI 솔루션",
        "AI Solutions Engineer",
        "Solutions Engineer",
        "AI 엔지니어",
        "LLM 응용",
    ),
    "role-enterprise-solution": (
        "엔터프라이즈 솔루션",
        "ITSM",
        "솔루션 엔지니어",
        "기술 컨설턴트",
    ),
    "role-cloud-finops": (
        "FinOps",
        "클라우드 자동화",
        "클라우드 비용 최적화",
        "Cloud Automation",
    ),
    "role-data-analytics-automation": (
        "데이터 자동화",
        "분석 자동화",
        "Analytics Engineer",
        "BI 자동화",
    ),
}


class JobSearchPlanError(ValueError):
    """Raised when a profile cannot produce an evidence-bound search plan."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JobSearchPlanError(f"{name} 객체가 필요함")
    return value


def _sequence(value: Any, name: str) -> Sequence[Any]:
    if not isinstance(value, list):
        raise JobSearchPlanError(f"{name} 배열이 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JobSearchPlanError(f"{name} 문자열이 필요함")
    return value.strip()


def _optional_text_list(value: Any, name: str) -> list[str]:
    if value is None:
        return []
    result: list[str] = []
    for index, item in enumerate(_sequence(value, name)):
        text = _text(item, f"{name}[{index}]")
        if text not in result:
            result.append(text)
    return result


def _role_terms(target_role_id: str, role: str) -> list[str]:
    """Expand one confirmed role with the reviewed discovery-term taxonomy."""

    terms = [role]
    candidates = (
        *(part.strip() for part in role.split("/")),
        *_ROLE_DISCOVERY_TERM_TAXONOMY.get(target_role_id, ()),
    )
    for candidate in candidates:
        part = candidate.strip()
        if part and part not in terms:
            terms.append(part)
    return terms


def _normalized_locations(values: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        terms = _LOCATION_NORMALIZATION.get(value, (value,))
        for term in terms:
            if term not in normalized:
                normalized.append(term)
    return normalized


def _profile_sha256(profile_document: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        profile_document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def build_job_search_plan(
    profile_document: Mapping[str, Any],
    *,
    generated_at: datetime,
) -> dict[str, Any]:
    """Build one immutable plan without inventing roles, skills, or preferences."""

    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise JobSearchPlanError("generated_at은 시간대가 포함되어야 함")
    document = _mapping(profile_document, "profile_document")
    profile = _mapping(document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")

    demonstrated_skills: list[dict[str, Any]] = []
    for index, item in enumerate(_sequence(profile.get("skills", []), "profile.skills")):
        skill = _mapping(item, f"profile.skills[{index}]")
        level = _text(skill.get("level"), f"profile.skills[{index}].level")
        if level not in _DEMONSTRATED_SKILL_LEVELS:
            continue
        evidence = _optional_text_list(
            skill.get("evidence"), f"profile.skills[{index}].evidence"
        )
        if not evidence:
            continue
        demonstrated_skills.append(
            {
                "skill_id": _text(
                    skill.get("skill_id"), f"profile.skills[{index}].skill_id"
                ),
                "name": _text(skill.get("name"), f"profile.skills[{index}].name"),
                "level": level,
            }
        )

    target_roles = _sequence(profile.get("target_roles"), "profile.target_roles")
    if not target_roles:
        raise JobSearchPlanError("검색 계획에는 확인된 목표 직무가 1개 이상 필요함")
    role_axes: list[dict[str, Any]] = []
    target_role_ids: list[str] = []
    for index, item in enumerate(target_roles):
        target = _mapping(item, f"profile.target_roles[{index}]")
        target_role_id = _text(
            target.get("target_role_id"),
            f"profile.target_roles[{index}].target_role_id",
        )
        if target_role_id in target_role_ids:
            raise JobSearchPlanError("목표 직무 ID는 중복될 수 없음")
        target_role_ids.append(target_role_id)
        priority = target.get("priority")
        if (
            isinstance(priority, bool)
            or not (
                isinstance(priority, int)
                and priority > 0
                or priority == "conditional"
            )
        ):
            raise JobSearchPlanError("목표 직무 우선순위가 올바르지 않음")
        role = _text(target.get("role"), f"profile.target_roles[{index}].role")
        hypothesis = target.get("hypothesis")
        rationale = (
            _text(hypothesis, f"profile.target_roles[{index}].hypothesis")
            if hypothesis is not None
            else "프로필의 목표 직무로 확인됨"
        )
        role_axes.append(
            {
                "target_role_id": target_role_id,
                "priority": priority,
                "canonical_role": role,
                "discovery_terms": _role_terms(target_role_id, role),
                "supporting_terms": [skill["name"] for skill in demonstrated_skills],
                "rationale": rationale,
            }
        )

    locations = _optional_text_list(
        basic.get("location_preference"), "profile.basic.location_preference"
    )
    employment_types = _optional_text_list(
        basic.get("employment_type_preference"),
        "profile.basic.employment_type_preference",
    )
    career_goals = _mapping(profile.get("career_goals", {}), "profile.career_goals")
    work_preferences = _mapping(
        profile.get("work_preferences", {}), "profile.work_preferences"
    )
    preferred = _optional_text_list(
        work_preferences.get("preferred"), "profile.work_preferences.preferred"
    )
    less_preferred = _optional_text_list(
        work_preferences.get("less_preferred"),
        "profile.work_preferences.less_preferred",
    )
    avoid = _optional_text_list(
        career_goals.get("avoid_if_possible"),
        "profile.career_goals.avoid_if_possible",
    )
    rank_down = []
    for signal, source_field in (
        *((value, "career_goals.avoid_if_possible") for value in avoid),
        *((value, "work_preferences.less_preferred") for value in less_preferred),
    ):
        if any(item["signal"] == signal for item in rank_down):
            continue
        rank_down.append(
            {
                "signal": signal,
                "source_field": source_field,
                "action": "rank_down_only",
            }
        )

    profile_hash = _profile_sha256(document)
    plan_id = "search-plan-" + sha256(
        f"{profile_hash}|{JOB_SEARCH_PLAN_RULES_VERSION}".encode("utf-8")
    ).hexdigest()[:24]
    preference_fields = []
    if locations:
        preference_fields.append("basic.location_preference")
    if employment_types:
        preference_fields.append("basic.employment_type_preference")
    if avoid:
        preference_fields.append("career_goals.avoid_if_possible")
    if preferred:
        preference_fields.append("work_preferences.preferred")
    if less_preferred:
        preference_fields.append("work_preferences.less_preferred")

    return {
        "job_search_plan": {
            "identity": {
                "plan_id": plan_id,
                "profile_id": profile_id,
                "profile_content_sha256": profile_hash,
                "version": 1,
                "generated_at": generated_at.isoformat(timespec="microseconds"),
            },
            "source_profile": {
                "target_role_ids": target_role_ids,
                "evidence_ids": [skill["skill_id"] for skill in demonstrated_skills],
                "preference_fields": preference_fields,
            },
            "role_axes": role_axes,
            "capability_signals": [
                {
                    "signal": skill["name"],
                    "importance": (
                        "high" if skill["level"] in {"project", "work"} else "medium"
                    ),
                    "evidence_ids": [skill["skill_id"]],
                }
                for skill in demonstrated_skills
            ],
            "preference_signals": {
                "positive": [
                    {
                        "signal": signal,
                        "source_field": "work_preferences.preferred",
                    }
                    for signal in preferred
                ],
                "rank_down": rank_down,
            },
            "objective_preferences": {
                "locations": {
                    "values": locations,
                    "normalized_values": _normalized_locations(locations),
                    "handling": "soft_preference",
                    "unknown_policy": "keep",
                },
                "employment_types": {
                    "values": employment_types,
                    "handling": "soft_preference",
                    "unknown_policy": "keep",
                },
            },
            "unknown_constraints": [
                {
                    "field": "career_years",
                    "reason": "프로필에 전체 경력 연수가 확정 필드로 없음",
                    "action": "do_not_filter",
                },
                {
                    "field": "remote_preference",
                    "reason": "프로필에 확정된 재택 선호가 없음",
                    "action": "ignore_for_discovery",
                },
            ],
            "discovery_sources": [
                {
                    "provider": "incruit",
                    "source_kind": "rss",
                    "status": "first_candidate",
                    "usage": "broad_discovery_and_metadata_ranking",
                    "detail_strategy": "official_or_employer_source_only",
                },
                {
                    "provider": "employer_ats",
                    "source_kind": "ats_api",
                    "status": "planned",
                    "usage": "target_company_discovery_and_detail",
                    "detail_strategy": "documented_public_api_only",
                },
            ],
            "ranking_policy": {
                "retrieval_mode": "broad_then_rank",
                "hard_exclusions": ["이미 본 동일 provider/external_id"],
                "rank_up_order": [
                    "우선순위가 높은 목표 직무 축과 관련됨",
                    "프로필에서 증거가 확인된 기술 신호가 있음",
                    "명시된 지역 또는 고용 형태 선호와 일치함",
                ],
                "rank_down_order": [
                    "낮은 선호 업무 방식이 상세 공고에 명시됨",
                    "명시된 지역 또는 고용 형태 선호와 다름",
                ],
                "keep_when_unknown": ["지역", "고용형태", "경력 연차", "재택 여부"],
            },
            "metadata": {
                "schema_version": JOB_SEARCH_PLAN_SCHEMA_VERSION,
                "rules_version": JOB_SEARCH_PLAN_RULES_VERSION,
                "generated_by": "profile_derived_rule",
                "requires_manual_keywords": False,
                "requires_manual_exclusions": False,
                "requires_remote_preference": False,
                "is_example": False,
                "contains_personal_data": True,
                "git_tracking_allowed": False,
            },
        }
    }
