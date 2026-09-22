"""Validate explicit search plans before using them with a selected profile."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import re
from typing import Any, Mapping

from career_agent.profile_input import ProfileDocumentError, profile_content_sha256

from .generator import (
    JOB_SEARCH_PLAN_RULES_VERSION,
    JOB_SEARCH_PLAN_SCHEMA_VERSION,
    JobSearchPlanError,
)


_PROFILE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_IMPORTANCE_VALUES = frozenset({"high", "medium", "supporting"})


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise JobSearchPlanError(f"{name} 객체가 필요함")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise JobSearchPlanError(f"{name} 배열이 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise JobSearchPlanError(f"{name} 문자열이 필요함")
    return value.strip()


def _required(value: Mapping[str, Any], fields: set[str], name: str) -> None:
    missing = sorted(fields - set(value))
    if missing:
        raise JobSearchPlanError(f"{name} 필수 필드 누락: {', '.join(missing)}")


def _text_list(value: Any, name: str, *, nonempty: bool = False) -> list[str]:
    items = _list(value, name)
    if nonempty and not items:
        raise JobSearchPlanError(f"{name}에는 항목이 1개 이상 필요함")
    normalized = [_text(item, f"{name}[{index}]") for index, item in enumerate(items)]
    if len(normalized) != len(set(normalized)):
        raise JobSearchPlanError(f"{name}에는 중복 문자열을 사용할 수 없음")
    return normalized


def _aware_datetime(value: Any, name: str) -> None:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise JobSearchPlanError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise JobSearchPlanError(f"{name}은 시간대가 포함되어야 함")


def _boolean(value: Any, name: str) -> None:
    if not isinstance(value, bool):
        raise JobSearchPlanError(f"{name} bool 값이 필요함")


def _validate_source_profile(value: Any) -> tuple[list[str], list[str]]:
    source = _mapping(value, "job_search_plan.source_profile")
    _required(
        source,
        {"target_role_ids", "evidence_ids", "preference_fields"},
        "job_search_plan.source_profile",
    )
    target_role_ids = _text_list(
        source["target_role_ids"],
        "job_search_plan.source_profile.target_role_ids",
        nonempty=True,
    )
    evidence_ids = _text_list(
        source["evidence_ids"], "job_search_plan.source_profile.evidence_ids"
    )
    _text_list(
        source["preference_fields"],
        "job_search_plan.source_profile.preference_fields",
    )
    return target_role_ids, evidence_ids


def _validate_role_axes(value: Any, target_role_ids: list[str]) -> None:
    axes = _list(value, "job_search_plan.role_axes")
    if not axes:
        raise JobSearchPlanError("job_search_plan.role_axes에는 항목이 1개 이상 필요함")
    seen: set[str] = set()
    for index, raw_axis in enumerate(axes):
        name = f"job_search_plan.role_axes[{index}]"
        axis = _mapping(raw_axis, name)
        _required(
            axis,
            {
                "target_role_id",
                "priority",
                "canonical_role",
                "discovery_terms",
                "supporting_terms",
                "rationale",
            },
            name,
        )
        target_role_id = _text(axis["target_role_id"], f"{name}.target_role_id")
        if target_role_id in seen:
            raise JobSearchPlanError("job_search_plan.role_axes target_role_id가 중복됨")
        if target_role_id not in target_role_ids:
            raise JobSearchPlanError(
                f"{name}.target_role_id가 source_profile에 존재하지 않음"
            )
        seen.add(target_role_id)
        priority = axis["priority"]
        if isinstance(priority, bool) or not (
            isinstance(priority, int) and priority > 0 or priority == "conditional"
        ):
            raise JobSearchPlanError(f"{name}.priority가 올바르지 않음")
        _text(axis["canonical_role"], f"{name}.canonical_role")
        _text_list(axis["discovery_terms"], f"{name}.discovery_terms", nonempty=True)
        _text_list(axis["supporting_terms"], f"{name}.supporting_terms")
        _text(axis["rationale"], f"{name}.rationale")
    if seen != set(target_role_ids):
        raise JobSearchPlanError(
            "job_search_plan.role_axes와 source_profile.target_role_ids가 일치하지 않음"
        )


def _validate_capability_signals(value: Any, evidence_ids: list[str]) -> None:
    for index, raw_signal in enumerate(_list(value, "job_search_plan.capability_signals")):
        name = f"job_search_plan.capability_signals[{index}]"
        signal = _mapping(raw_signal, name)
        _required(signal, {"signal", "importance", "evidence_ids"}, name)
        _text(signal["signal"], f"{name}.signal")
        importance = _text(signal["importance"], f"{name}.importance")
        if importance not in _IMPORTANCE_VALUES:
            raise JobSearchPlanError(f"{name}.importance가 올바르지 않음")
        references = _text_list(
            signal["evidence_ids"], f"{name}.evidence_ids", nonempty=True
        )
        if not set(references).issubset(evidence_ids):
            raise JobSearchPlanError(f"{name}.evidence_ids에 알 수 없는 근거가 있음")


def _validate_preference_signals(value: Any) -> None:
    preferences = _mapping(value, "job_search_plan.preference_signals")
    _required(preferences, {"positive", "rank_down"}, "job_search_plan.preference_signals")
    for field, required_fields in (
        ("positive", {"signal", "source_field"}),
        ("rank_down", {"signal", "source_field", "action"}),
    ):
        for index, raw_item in enumerate(
            _list(preferences[field], f"job_search_plan.preference_signals.{field}")
        ):
            name = f"job_search_plan.preference_signals.{field}[{index}]"
            item = _mapping(raw_item, name)
            _required(item, required_fields, name)
            for key in required_fields:
                _text(item[key], f"{name}.{key}")


def _validate_objective_preferences(value: Any) -> None:
    objective = _mapping(value, "job_search_plan.objective_preferences")
    _required(objective, {"locations", "employment_types"}, "job_search_plan.objective_preferences")
    locations = _mapping(objective["locations"], "job_search_plan.objective_preferences.locations")
    _required(
        locations,
        {"values", "normalized_values", "handling", "unknown_policy"},
        "job_search_plan.objective_preferences.locations",
    )
    _text_list(locations["values"], "job_search_plan.objective_preferences.locations.values")
    _text_list(
        locations["normalized_values"],
        "job_search_plan.objective_preferences.locations.normalized_values",
    )
    _text(locations["handling"], "job_search_plan.objective_preferences.locations.handling")
    _text(
        locations["unknown_policy"],
        "job_search_plan.objective_preferences.locations.unknown_policy",
    )
    employment = _mapping(
        objective["employment_types"],
        "job_search_plan.objective_preferences.employment_types",
    )
    _required(
        employment,
        {"values", "handling", "unknown_policy"},
        "job_search_plan.objective_preferences.employment_types",
    )
    _text_list(
        employment["values"],
        "job_search_plan.objective_preferences.employment_types.values",
    )
    _text(
        employment["handling"],
        "job_search_plan.objective_preferences.employment_types.handling",
    )
    _text(
        employment["unknown_policy"],
        "job_search_plan.objective_preferences.employment_types.unknown_policy",
    )


def _validate_object_list(
    value: Any,
    name: str,
    required_fields: set[str],
    *,
    nonempty: bool = False,
) -> None:
    items = _list(value, name)
    if nonempty and not items:
        raise JobSearchPlanError(f"{name}에는 항목이 1개 이상 필요함")
    for index, raw_item in enumerate(items):
        item_name = f"{name}[{index}]"
        item = _mapping(raw_item, item_name)
        _required(item, required_fields, item_name)
        for field in required_fields:
            _text(item[field], f"{item_name}.{field}")


def _validate_ranking_policy(value: Any) -> None:
    ranking = _mapping(value, "job_search_plan.ranking_policy")
    _required(
        ranking,
        {
            "retrieval_mode",
            "hard_exclusions",
            "rank_up_order",
            "rank_down_order",
            "keep_when_unknown",
        },
        "job_search_plan.ranking_policy",
    )
    _text(ranking["retrieval_mode"], "job_search_plan.ranking_policy.retrieval_mode")
    for field in (
        "hard_exclusions",
        "rank_up_order",
        "rank_down_order",
        "keep_when_unknown",
    ):
        _text_list(ranking[field], f"job_search_plan.ranking_policy.{field}")


def validate_job_search_plan(search_plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate the current required search-plan structure and return a copy."""

    document = _mapping(search_plan, "search_plan")
    if "job_search_plan" in document:
        if set(document) != {"job_search_plan"}:
            raise JobSearchPlanError("검색 계획 문서에 허용되지 않은 최상위 필드가 있음")
        plan = _mapping(document["job_search_plan"], "job_search_plan")
    else:
        plan = document
    _required(
        plan,
        {
            "identity",
            "source_profile",
            "role_axes",
            "capability_signals",
            "preference_signals",
            "objective_preferences",
            "unknown_constraints",
            "discovery_sources",
            "ranking_policy",
            "metadata",
        },
        "job_search_plan",
    )

    identity = _mapping(plan["identity"], "job_search_plan.identity")
    _required(
        identity,
        {"plan_id", "profile_id", "profile_content_sha256", "version", "generated_at"},
        "job_search_plan.identity",
    )
    _text(identity["plan_id"], "job_search_plan.identity.plan_id")
    _text(identity["profile_id"], "job_search_plan.identity.profile_id")
    profile_hash = _text(
        identity["profile_content_sha256"],
        "job_search_plan.identity.profile_content_sha256",
    )
    if _PROFILE_HASH_PATTERN.fullmatch(profile_hash) is None:
        raise JobSearchPlanError(
            "job_search_plan.identity.profile_content_sha256 형식이 올바르지 않음"
        )
    version = identity["version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise JobSearchPlanError("job_search_plan.identity.version 양의 정수가 필요함")
    _aware_datetime(identity["generated_at"], "job_search_plan.identity.generated_at")

    target_role_ids, evidence_ids = _validate_source_profile(plan["source_profile"])
    _validate_role_axes(plan["role_axes"], target_role_ids)
    _validate_capability_signals(plan["capability_signals"], evidence_ids)
    _validate_preference_signals(plan["preference_signals"])
    _validate_objective_preferences(plan["objective_preferences"])
    _validate_object_list(
        plan["unknown_constraints"],
        "job_search_plan.unknown_constraints",
        {"field", "reason", "action"},
    )
    _validate_object_list(
        plan["discovery_sources"],
        "job_search_plan.discovery_sources",
        {"provider", "source_kind", "status", "usage", "detail_strategy"},
        nonempty=True,
    )
    _validate_ranking_policy(plan["ranking_policy"])

    metadata = _mapping(plan["metadata"], "job_search_plan.metadata")
    _required(
        metadata,
        {
            "schema_version",
            "rules_version",
            "generated_by",
            "requires_manual_keywords",
            "requires_manual_exclusions",
            "requires_remote_preference",
            "is_example",
            "contains_personal_data",
            "git_tracking_allowed",
        },
        "job_search_plan.metadata",
    )
    if metadata["schema_version"] != JOB_SEARCH_PLAN_SCHEMA_VERSION:
        raise JobSearchPlanError("현재 스키마 버전의 검색 계획이 아님")
    if metadata["rules_version"] != JOB_SEARCH_PLAN_RULES_VERSION:
        raise JobSearchPlanError("현재 생성 규칙 버전의 검색 계획이 아님")
    _text(metadata["generated_by"], "job_search_plan.metadata.generated_by")
    for field in (
        "requires_manual_keywords",
        "requires_manual_exclusions",
        "requires_remote_preference",
        "is_example",
        "contains_personal_data",
        "git_tracking_allowed",
    ):
        _boolean(metadata[field], f"job_search_plan.metadata.{field}")
    is_example = metadata["is_example"] is True
    expected_personal_data = not is_example
    expected_git_tracking = is_example
    if metadata["contains_personal_data"] is not expected_personal_data:
        raise JobSearchPlanError("검색 계획의 개인정보 포함 표시가 유형과 일치하지 않음")
    if metadata["git_tracking_allowed"] is not expected_git_tracking:
        raise JobSearchPlanError("검색 계획의 Git 추적 표시가 유형과 일치하지 않음")
    return {"job_search_plan": deepcopy(dict(plan))}


def validate_job_search_plan_for_profile(
    search_plan: Mapping[str, Any],
    profile_document: Mapping[str, Any],
) -> dict[str, Any]:
    """Require an explicit plan to identify the exact selected profile content."""

    validated = validate_job_search_plan(search_plan)
    profile = _mapping(profile_document, "profile_document")
    profile_root = _mapping(profile.get("profile"), "profile")
    basic = _mapping(profile_root.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")
    identity = validated["job_search_plan"]["identity"]
    if identity["profile_id"] != profile_id:
        raise JobSearchPlanError("검색 계획의 profile_id가 선택 프로필과 다름")
    try:
        expected_hash = profile_content_sha256(profile_document)
    except ProfileDocumentError as error:
        raise JobSearchPlanError("선택 프로필의 내용 지문을 계산할 수 없음") from error
    if identity["profile_content_sha256"] != expected_hash:
        raise JobSearchPlanError("검색 계획의 프로필 내용 지문이 선택 프로필과 다름")
    return validated
