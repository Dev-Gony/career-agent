"""Render a validated profile analysis draft without exposing candidate text."""

from __future__ import annotations

from typing import Any, Mapping

from career_agent.profile_input import PROFILE_ANALYSIS_DRAFT_SCHEMA_VERSION

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


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


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
