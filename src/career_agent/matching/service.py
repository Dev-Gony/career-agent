"""Composition service for requirement-level matching."""

from __future__ import annotations

from collections import Counter
from typing import Any

from .eligibility import EligibilityMatchError, assess_eligibility
from .experience import ExperienceMatchError, match_experience_requirements
from .insights import MatchInsightsError, build_match_insights
from .job_posting_information import (
    JobPostingInformationError,
    assess_job_posting_information,
)
from .learning import LearningRecommendationError, build_learning_recommendations
from .portfolio import PortfolioRecommendationError, build_portfolio_recommendations
from .recommendation import RecommendationError, build_application_recommendation
from .responsibility import ResponsibilityMatchError, match_responsibilities
from .technology import TechnologyMatchError, match_technology_requirements


MATCHING_RULES_VERSION = "0.5"


class RequirementMatchError(ValueError):
    """Raised when a combined requirement result cannot be built safely."""


def _required_mapping(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise RequirementMatchError(f"'{key}' 객체가 필요합니다.")
    return value


def _required_list(document: dict[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise RequirementMatchError(f"'{key}' 배열이 필요합니다.")
    return value


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RequirementMatchError(f"'{key}' 문자열이 필요합니다.")
    return value.strip()


def _index_assessments(
    matches: list[dict[str, Any]], source_section: str
) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for match in matches:
        requirement = _required_mapping(match, "requirement")
        source_id = _required_text(requirement, "source_id")
        if requirement.get("source_section") != source_section:
            raise RequirementMatchError(
                f"'{source_id}' 판정의 source_section이 일치하지 않습니다."
            )
        if source_id in index:
            raise RequirementMatchError(f"중복 판정 ID가 있습니다: {source_id}")
        index[source_id] = match
    return index


def _unknown_assessment(
    raw_item: dict[str, Any], *, source_section: str, source_id: str
) -> dict[str, Any]:
    item_type = _required_text(raw_item, "type")
    name = _required_text(raw_item, "name")
    evidence_text = _required_text(raw_item, "evidence_text")
    return {
        "requirement": {
            "source_section": source_section,
            "source_id": source_id,
            "type": item_type,
            "name": name,
            "evidence_text": evidence_text,
        },
        "assessment": {
            "result": "unknown",
            "directness": "none",
            "confidence": "low",
            "reason": "현재 MVP 규칙이 이 조건 유형을 아직 평가하지 못합니다.",
        },
        "user_evidence": [],
        "unknowns": [f"{name} 조건 충족 여부"],
        "next_action": f"{name} 조건의 의미와 사용자 근거를 추가 확인",
    }


def _merge_section(
    items: list[Any],
    *,
    source_section: str,
    id_field: str,
    assessment_groups: list[list[dict[str, Any]]],
    seen_source_ids: set[str],
) -> list[dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for group in assessment_groups:
        for source_id, assessment in _index_assessments(
            group, source_section
        ).items():
            if source_id in indexed:
                raise RequirementMatchError(
                    f"둘 이상의 매처가 같은 항목을 판정했습니다: {source_id}"
                )
            indexed[source_id] = assessment

    merged: list[dict[str, Any]] = []
    for position, raw_item in enumerate(items):
        if not isinstance(raw_item, dict):
            raise RequirementMatchError(
                f"job_posting.{source_section}[{position}]는 객체여야 합니다."
            )
        source_id = _required_text(raw_item, id_field)
        if source_id in seen_source_ids:
            raise RequirementMatchError(f"중복 공고 항목 ID가 있습니다: {source_id}")
        seen_source_ids.add(source_id)
        merged.append(
            indexed.get(source_id)
            or _unknown_assessment(
                raw_item, source_section=source_section, source_id=source_id
            )
        )
    return merged


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


def _confirmed_matches(
    required_matches: list[dict[str, Any]],
    preferred_matches: list[dict[str, Any]],
    responsibility_matches: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    confirmed: list[dict[str, Any]] = []
    for match in [*required_matches, *responsibility_matches, *preferred_matches]:
        assessment = _required_mapping(match, "assessment")
        if assessment.get("result") not in {"strong_match", "match"}:
            continue
        requirement = _required_mapping(match, "requirement")
        user_evidence = match.get("user_evidence")
        if not isinstance(user_evidence, list) or not user_evidence:
            raise RequirementMatchError("확인된 일치에는 사용자 근거가 필요합니다.")
        confirmed.append(
            {
                "source_section": _required_text(requirement, "source_section"),
                "name": _required_text(requirement, "name"),
                "result": str(assessment["result"]),
                "posting_evidence": _required_text(requirement, "evidence_text"),
                "user_evidence": user_evidence,
            }
        )
    return confirmed


def match_job_requirements(
    profile_document: dict[str, Any],
    posting_document: dict[str, Any],
) -> dict[str, Any]:
    """Combine specialized matchers while preserving posting order and omissions."""

    if not isinstance(profile_document, dict) or not isinstance(posting_document, dict):
        raise RequirementMatchError("프로필과 채용공고는 JSON 객체여야 합니다.")

    profile = _required_mapping(profile_document, "profile")
    posting = _required_mapping(posting_document, "job_posting")
    profile_id = _required_text(_required_mapping(profile, "basic"), "profile_id")
    posting_id = _required_text(_required_mapping(posting, "identity"), "posting_id")

    try:
        job_posting_information = assess_job_posting_information(posting_document)
        technology = match_technology_requirements(profile_document, posting_document)
        experience = match_experience_requirements(profile_document, posting_document)
        eligibility = assess_eligibility(profile_document, posting_document)
        responsibility = match_responsibilities(profile_document, posting_document)
    except (
        TechnologyMatchError,
        ExperienceMatchError,
        EligibilityMatchError,
        JobPostingInformationError,
        ResponsibilityMatchError,
    ) as error:
        raise RequirementMatchError(str(error)) from error

    seen_source_ids: set[str] = set()
    required_matches = _merge_section(
        _required_list(posting, "requirements"),
        source_section="requirements",
        id_field="requirement_id",
        assessment_groups=[
            technology["required_matches"],
            experience["required_matches"],
        ],
        seen_source_ids=seen_source_ids,
    )
    preferred_matches = _merge_section(
        _required_list(posting, "preferred_qualifications"),
        source_section="preferred_qualifications",
        id_field="qualification_id",
        assessment_groups=[
            technology["preferred_matches"],
            experience["preferred_matches"],
        ],
        seen_source_ids=seen_source_ids,
    )
    try:
        insights = build_match_insights(
            required_matches,
            preferred_matches,
            responsibility["responsibility_matches"],
            eligibility,
        )
        application_recommendation = build_application_recommendation(
            required_matches,
            preferred_matches,
            eligibility,
            job_posting_information=job_posting_information,
            responsibility_matches=responsibility["responsibility_matches"],
            responsibilities_evaluated=True,
        )
        learning_recommendations = build_learning_recommendations(
            profile_document,
            required_matches,
            preferred_matches,
        )
        portfolio_recommendations = build_portfolio_recommendations(
            profile_document,
            learning_recommendations,
            responsibility["responsibility_matches"],
        )
    except (
        LearningRecommendationError,
        MatchInsightsError,
        PortfolioRecommendationError,
        RecommendationError,
    ) as error:
        raise RequirementMatchError(str(error)) from error

    confirmed_matches = _confirmed_matches(
        required_matches,
        preferred_matches,
        responsibility["responsibility_matches"],
    )

    return {
        "scope": "requirements_responsibilities_eligibility_and_recommendation",
        "inputs": {
            "profile_id": profile_id,
            "posting_id": posting_id,
        },
        "summary": {
            "required": _summarize(required_matches),
            "preferred": _summarize(preferred_matches),
            "responsibilities": responsibility["summary"],
        },
        "eligibility": eligibility,
        "job_posting_information": job_posting_information,
        "jd_information_level": job_posting_information["level"],
        "required_matches": required_matches,
        "preferred_matches": preferred_matches,
        "responsibility_matches": responsibility["responsibility_matches"],
        "strengths": insights["strengths"],
        "confirmed_matches": confirmed_matches,
        "gaps": insights["gaps"],
        "unknowns": insights["unknowns"],
        "learning_recommendations": learning_recommendations,
        "portfolio_recommendations": portfolio_recommendations,
        "application_recommendation": application_recommendation,
        "recommendation": application_recommendation["status"],
        "recommendation_reason": application_recommendation[
            "recommendation_reason"
        ],
        "metadata": {
            "matching_rules_version": MATCHING_RULES_VERSION,
            "analysis_mode": "mvp_rule_based",
            "incomplete_sections": [
                "identity",
                "analysis_notes",
            ],
        },
    }
