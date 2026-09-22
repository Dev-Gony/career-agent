"""Render a final, still non-applied profile change proposal for Slack."""

from __future__ import annotations

from typing import Any, Mapping

from career_agent.profile_input import (
    ProfileDocumentError,
    profile_content_sha256,
    validate_profile_analysis_final_proposal,
)

from .slack_events import SlackEventError


_MAX_MESSAGE_CHARS = 3800


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _safe_text(value: Any, name: str, *, max_chars: int = 160) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlackEventError(f"{name} 문자열이 필요함")
    normalized = " ".join(value.split())
    if len(normalized) > max_chars:
        normalized = normalized[: max_chars - 3].rstrip() + "..."
    return normalized.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_slack_profile_final_proposal_result(
    profile_document: Mapping[str, Any],
    final_proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a readable final summary and a private proposal identifier."""

    try:
        validated = validate_profile_analysis_final_proposal(final_proposal)
    except ProfileDocumentError as error:
        raise SlackEventError("최종 프로필 변경안을 안전하게 표시할 수 없음") from error
    root = _mapping(validated.get("profile_analysis_final_proposal"), "proposal")
    if root.get("base_profile_content_sha256") != profile_content_sha256(profile_document):
        raise SlackEventError("최종 변경안의 기준 프로필이 현재 프로필과 다름")
    summary = _mapping(validated.get("summary"), "summary")
    lines = [
        "프로필 최종 변경안",
        "",
        f"- 전체 변경: {summary['change_count']}개",
        f"- 경력 수행 근거 추가: {summary['career_evidence_count']}개",
        f"- 경력 성과 근거 추가: {summary['achievement_evidence_count']}개",
        f"- 기존 기술 근거 추가: {summary['existing_skill_evidence_count']}개",
        f"- 새 기술 추가: {summary['new_skill_count']}개",
        "",
        "변경 상세",
    ]
    for index, raw_change in enumerate(validated["resolved_changes"], start=1):
        change = _mapping(raw_change, f"resolved_changes[{index - 1}]")
        target = _mapping(change.get("target"), "change.target")
        value = _mapping(change.get("proposed_value"), "change.proposed_value")
        operation = target.get("operation")
        record_id = _safe_text(target.get("record_id"), "record_id", max_chars=100)
        if operation == "append_responsibility_evidence":
            detail = _safe_text(value.get("responsibility_evidence"), "responsibility")
            label = "경력 수행 근거"
        elif operation == "append_achievement_evidence":
            detail = _safe_text(
                value.get("result_evidence")
                or value.get("action_evidence")
                or value.get("problem_evidence"),
                "achievement",
            )
            label = "경력 성과 근거"
        elif operation == "append_skill_evidence":
            technology = _safe_text(value.get("technology_name"), "technology", max_chars=80)
            detail = _safe_text(value.get("usage_evidence"), "usage")
            label = f"기존 기술 {technology} 근거"
        elif operation == "add_skill_with_evidence":
            technology = _safe_text(value.get("technology_name"), "technology", max_chars=80)
            level = _safe_text(value.get("proposed_level"), "level", max_chars=20)
            detail = _safe_text(value.get("usage_evidence"), "usage")
            label = f"새 기술 {technology}, 숙련도 {level}"
        else:
            raise SlackEventError("최종 프로필 변경안에 지원하지 않는 동작이 있음")
        lines.append(f"{index}. {label} -> `{record_id}`")
        lines.append(f"   - {detail}")
    lines.extend(
        [
            "",
            "이 변경안은 아직 개인 프로필과 공고 검색 조건에 적용되지 않았습니다.",
            "다음 단계에서 전체 변경안을 명시적으로 승인한 뒤에만 새 프로필 버전을 만듭니다.",
        ]
    )
    message = "\n".join(lines)
    if len(message) > _MAX_MESSAGE_CHARS:
        raise SlackEventError("최종 프로필 변경안이 Slack 한 메시지 표시 한도를 초과함")
    return {
        "public_message": message,
        "final_target": {
            "final_proposal_id": root["final_proposal_id"],
        },
    }
