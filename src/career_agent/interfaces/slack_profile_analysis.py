"""Render a validated profile analysis draft without exposing candidate text."""

from __future__ import annotations

from typing import Any, Mapping

from career_agent.profile_input import (
    PROFILE_ANALYSIS_DRAFT_SCHEMA_VERSION,
    ProfileDocumentError,
    select_latest_profile_analysis_draft,
    select_latest_profile_analysis_reviews,
    select_latest_profile_text_extraction,
    validate_profile_analysis_draft,
)

from .slack_events import SlackEventError


_SUMMARY_FIELDS = (
    ("career_evidence_count", "경력 근거"),
    ("achievement_evidence_count", "성과 근거"),
    ("technology_evidence_count", "기술 사용 근거"),
    ("unknown_count", "추가 확인 질문"),
)
_ANALYSIS_FIELDS = {
    "career_evidence_count": "career_evidence",
    "achievement_evidence_count": "achievement_evidence",
    "technology_evidence_count": "technology_evidence",
    "unknown_count": "unknowns",
}
NO_PROFILE_EXTRACTION_REPLY = (
    "아직 확인할 프로필 문서 추출 결과가 없습니다. "
    "먼저 `프로필 분석해줘`와 함께 파일 1개를 첨부해주세요."
)
NO_PROFILE_ANALYSIS_DRAFT_REPLY = (
    "가장 최근 프로필 문서는 확인했지만 검증된 분석 초안이 아직 없습니다. "
    "현재 문단 분류 결과만 저장되어 있으며 개인 프로필에는 반영되지 않았습니다."
)
NO_PROFILE_ANALYSIS_ITEMS_REPLY = (
    "최신 프로필 분석 초안에 검토할 항목이 없습니다. "
    "개인 프로필과 검색 조건은 변경되지 않았습니다."
)
ALL_PROFILE_ANALYSIS_ITEMS_REVIEWED_REPLY = (
    "최신 프로필 분석 초안의 모든 항목을 이미 검토했습니다. "
    "아직 개인 프로필과 공고 검색 조건에는 자동 반영하지 않았습니다."
)
_REVIEW_ITEM_TYPES = (
    "career_evidence",
    "achievement_evidence",
    "technology_evidence",
    "unknowns",
)
_CONFIDENCE_LABELS = {"high": "높음", "medium": "보통", "low": "낮음"}
_REVIEW_ITEM_TYPE_LABELS = {
    "career_evidence": "경력 근거",
    "achievement_evidence": "성과 근거",
    "technology_evidence": "기술 사용 근거",
    "unknowns": "추가 확인 질문",
}


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _safe_slack_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlackEventError(f"{name} 문자열이 필요함")
    normalized = " ".join(value.split())
    return (
        normalized.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _optional_line(
    lines: list[str],
    item: Mapping[str, Any],
    field: str,
    label: str,
) -> None:
    value = item.get(field)
    if value is not None:
        lines.append(f"- {label}: {_safe_slack_text(value, field)}")


def build_slack_profile_analysis_review_item_result(
    draft: Mapping[str, Any],
    *,
    reviewed_items: frozenset[tuple[str, int]] = frozenset(),
) -> dict[str, Any]:
    """Render the first pending review item and return its private target."""

    try:
        validated = validate_profile_analysis_draft(draft)
    except ProfileDocumentError as error:
        raise SlackEventError("프로필 분석 초안을 안전하게 검토할 수 없음") from error
    root = _mapping(validated.get("profile_analysis_draft"), "profile_analysis_draft")
    if root.get("status") != "needs_review":
        raise SlackEventError("검토 대기 상태인 프로필 분석 초안이 아님")
    analysis = _mapping(validated.get("analysis"), "analysis")
    flattened: list[tuple[str, int, Mapping[str, Any]]] = []
    for item_type in _REVIEW_ITEM_TYPES:
        items = analysis.get(item_type)
        if not isinstance(items, list):
            raise SlackEventError(f"analysis.{item_type} 배열이 필요함")
        for item_position, raw_item in enumerate(items, start=1):
            flattened.append(
                (
                    item_type,
                    item_position,
                    _mapping(raw_item, f"analysis.{item_type}[{item_position - 1}]"),
                )
            )
    if not flattened:
        return {"public_message": NO_PROFILE_ANALYSIS_ITEMS_REPLY, "review_target": None}

    pending = [
        entry for entry in flattened if (entry[0], entry[1]) not in reviewed_items
    ]
    if not pending:
        return {
            "public_message": ALL_PROFILE_ANALYSIS_ITEMS_REVIEWED_REPLY,
            "review_target": None,
        }

    item_type, item_position, item = pending[0]
    overall_position = flattened.index(pending[0]) + 1
    confidence = item.get("confidence")
    confidence_label = _CONFIDENCE_LABELS.get(confidence)
    if confidence_label is None:
        raise SlackEventError("프로필 분석 항목 신뢰도가 올바르지 않음")
    lines = [
        f"프로필 분석 항목 {overall_position}/{len(flattened)}",
        "",
    ]
    if item_type == "career_evidence":
        lines.append("유형: 경력 근거")
        _optional_line(lines, item, "role_or_context", "역할 또는 맥락")
        _optional_line(lines, item, "period_expression", "기간 표현")
        _optional_line(lines, item, "responsibility_evidence", "수행 내용")
    elif item_type == "achievement_evidence":
        lines.append("유형: 성과 근거")
        _optional_line(lines, item, "problem_evidence", "문제 또는 배경")
        _optional_line(lines, item, "action_evidence", "행동")
        _optional_line(lines, item, "result_evidence", "결과")
    elif item_type == "technology_evidence":
        lines.append("유형: 기술 사용 근거")
        _optional_line(lines, item, "technology_name", "기술")
        _optional_line(lines, item, "usage_evidence", "사용 근거")
        lines.append("- 숙련도: 사용자 확인 전 미확정")
    else:
        lines.append("유형: 추가 확인 질문")
        _optional_line(lines, item, "question", "질문")
        _optional_line(lines, item, "reason", "확인 이유")
    lines.extend(
        [
            f"- AI 판단 신뢰도: {confidence_label}",
            "",
            f"검토 항목: {_REVIEW_ITEM_TYPE_LABELS[item_type]} {item_position}번",
            "현재는 내용 확인 단계이며 승인 또는 거부는 기록하지 않았습니다.",
            "아직 개인 프로필과 공고 검색 조건에는 반영하지 않았습니다.",
        ]
    )
    return {
        "public_message": "\n".join(lines),
        "review_target": {
            "draft_id": root["draft_id"],
            "extraction_id": root["source_extraction_id"],
            "item_type": item_type,
            "item_position": item_position,
        },
    }


def build_slack_profile_analysis_review_item(draft: Mapping[str, Any]) -> str:
    """Render the first review item without exposing internal identifiers."""

    return str(build_slack_profile_analysis_review_item_result(draft)["public_message"])


def build_slack_profile_analysis_summary(draft: Mapping[str, Any]) -> str:
    """Build a count-only Slack summary for one reviewable analysis draft."""

    root = _mapping(draft.get("profile_analysis_draft"), "profile_analysis_draft")
    summary = _mapping(draft.get("summary"), "summary")
    analysis = _mapping(draft.get("analysis"), "analysis")
    metadata = _mapping(draft.get("metadata"), "metadata")
    if root.get("status") != "needs_review":
        raise SlackEventError("검토 대기 상태인 프로필 분석 초안이 아님")
    if metadata.get("schema_version") != PROFILE_ANALYSIS_DRAFT_SCHEMA_VERSION:
        raise SlackEventError("현재 버전의 프로필 분석 초안이 아님")
    if metadata.get("provider_output_validated") is not True:
        raise SlackEventError("공급자 출력 검증이 완료되지 않은 초안임")
    if metadata.get("profile_updated") is not False:
        raise SlackEventError("이미 프로필에 반영된 초안은 표시할 수 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise SlackEventError("프로필 분석 초안의 비공개 표시가 없음")

    lines = ["프로필 분석 초안이 준비되었습니다.", ""]
    for field, label in _SUMMARY_FIELDS:
        count = summary.get(field)
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or not 0 <= count <= 50
        ):
            raise SlackEventError(f"프로필 분석 초안 {field}가 올바르지 않음")
        analysis_items = analysis.get(_ANALYSIS_FIELDS[field])
        if not isinstance(analysis_items, list) or len(analysis_items) != count:
            raise SlackEventError(f"프로필 분석 초안 {field} 합계가 일치하지 않음")
        lines.append(f"- {label}: {count}개")

    lines.extend(
        [
            "",
            "검토 상태: 사용자 확인 필요",
            "이 요약에는 이력서 문장 원문을 표시하지 않았습니다.",
            "아직 개인 프로필과 공고 검색 조건에는 반영하지 않았습니다.",
        ]
    )
    return "\n".join(lines)


def build_latest_slack_profile_analysis_summary(
    extraction_directory: str,
    draft_directory: str,
) -> str:
    """Load the latest verified private draft and return a count-only summary."""

    try:
        extraction = select_latest_profile_text_extraction(extraction_directory)
        if extraction is None:
            return NO_PROFILE_EXTRACTION_REPLY
        extraction_id = extraction["profile_extraction"]["extraction_id"]
        draft = select_latest_profile_analysis_draft(
            extraction_id,
            draft_directory,
        )
    except ProfileDocumentError as error:
        raise SlackEventError("저장된 프로필 분석 초안을 안전하게 확인할 수 없음") from error
    if draft is None:
        return NO_PROFILE_ANALYSIS_DRAFT_REPLY
    return build_slack_profile_analysis_summary(draft)


def build_latest_slack_profile_analysis_review_item(
    extraction_directory: str,
    draft_directory: str,
    review_directory: str | None = None,
) -> str:
    """Load the latest verified draft and render its first review item."""

    return str(
        build_latest_slack_profile_analysis_review_item_result(
            extraction_directory,
            draft_directory,
            review_directory,
        )["public_message"]
    )


def build_latest_slack_profile_analysis_review_item_result(
    extraction_directory: str,
    draft_directory: str,
    review_directory: str | None = None,
) -> dict[str, Any]:
    """Load the latest draft and return its first pending item and target."""

    try:
        extraction = select_latest_profile_text_extraction(extraction_directory)
        if extraction is None:
            return {"public_message": NO_PROFILE_EXTRACTION_REPLY, "review_target": None}
        extraction_id = extraction["profile_extraction"]["extraction_id"]
        draft = select_latest_profile_analysis_draft(
            extraction_id,
            draft_directory,
        )
    except ProfileDocumentError as error:
        raise SlackEventError("저장된 프로필 분석 초안을 안전하게 확인할 수 없음") from error
    if draft is None:
        return {"public_message": NO_PROFILE_ANALYSIS_DRAFT_REPLY, "review_target": None}
    reviewed_items: frozenset[tuple[str, int]] = frozenset()
    if review_directory is not None:
        try:
            draft_id = draft["profile_analysis_draft"]["draft_id"]
            reviews = select_latest_profile_analysis_reviews(
                draft_id,
                review_directory,
            )
            reviewed_items = frozenset(reviews)
        except ProfileDocumentError as error:
            raise SlackEventError(
                "저장된 프로필 분석 검토 기록을 안전하게 확인할 수 없음"
            ) from error
    return build_slack_profile_analysis_review_item_result(
        draft,
        reviewed_items=reviewed_items,
    )
