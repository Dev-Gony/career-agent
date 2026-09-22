"""Render one pending profile-change mapping item for Slack."""

from __future__ import annotations

from typing import Any, Mapping

from career_agent.profile_input import (
    ProfileDocumentError,
    profile_content_sha256,
    validate_profile_analysis_update_proposal,
)

from .slack_events import SlackEventError


NO_PROFILE_UPDATE_PROPOSAL_REPLY = (
    "아직 확인할 프로필 변경 제안이 없습니다. "
    "먼저 분석 항목 검토를 완료해주세요."
)
INCOMPLETE_PROFILE_ANALYSIS_REVIEW_REPLY = (
    "아직 검토하지 않은 프로필 분석 항목이 있습니다. "
    "먼저 `프로필 검토 시작`으로 모든 항목을 확인해주세요."
)
NO_APPROVED_PROFILE_FACTS_REPLY = (
    "승인된 프로필 근거가 없어 변경할 내용이 없습니다. "
    "기존 개인 프로필은 변경되지 않았습니다."
)
NO_PROFILE_CHANGES_REPLY = (
    "승인된 근거가 모두 기존 프로필과 중복되어 새 변경 내용이 없습니다. "
    "기존 개인 프로필은 변경되지 않았습니다."
)
PROFILE_MAPPING_COMPLETED_REPLY = (
    "모든 프로필 변경 항목의 매핑이 준비됐습니다. "
    "아직 실제 개인 프로필에는 적용하지 않았습니다."
)
_SKILL_LEVELS = ("none", "exposure", "learning", "basic", "project", "work")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _safe_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlackEventError(f"{name} 문자열이 필요함")
    return (
        " ".join(value.split())
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _optional_line(
    lines: list[str],
    value: Any,
    label: str,
    name: str,
) -> None:
    if value is not None:
        lines.append(f"- {label}: {_safe_text(value, name)}")


def build_slack_profile_update_mapping_item_result(
    profile_document: Mapping[str, Any],
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a safe message and private target for the first pending mapping."""

    try:
        validated = validate_profile_analysis_update_proposal(proposal)
    except ProfileDocumentError as error:
        raise SlackEventError("프로필 변경 제안을 안전하게 표시할 수 없음") from error
    root = _mapping(
        validated.get("profile_analysis_update_proposal"),
        "profile_analysis_update_proposal",
    )
    if root.get("base_profile_content_sha256") != profile_content_sha256(
        profile_document
    ):
        raise SlackEventError("프로필 변경 제안의 기준 프로필이 현재 프로필과 다름")
    summary = _mapping(validated.get("summary"), "summary")
    if summary.get("unreviewed_count") != 0:
        return {
            "public_message": INCOMPLETE_PROFILE_ANALYSIS_REVIEW_REPLY,
            "mapping_target": None,
        }
    status = root.get("status")
    if status == "no_approved_profile_facts":
        return {
            "public_message": NO_APPROVED_PROFILE_FACTS_REPLY,
            "mapping_target": None,
        }
    if status == "no_changes":
        return {
            "public_message": NO_PROFILE_CHANGES_REPLY,
            "mapping_target": None,
        }

    changes = validated.get("proposed_changes")
    if not isinstance(changes, list):
        raise SlackEventError("프로필 변경 제안 항목 배열이 없음")
    pending: list[tuple[int, Mapping[str, Any]]] = []
    for position, raw_change in enumerate(changes, start=1):
        change = _mapping(raw_change, f"proposed_changes[{position - 1}]")
        target = _mapping(change.get("target"), "change.target")
        if str(target.get("mapping_status")).startswith("needs_"):
            pending.append((position, change))
    if not pending:
        return {
            "public_message": PROFILE_MAPPING_COMPLETED_REPLY,
            "mapping_target": None,
        }

    position, change = pending[0]
    source = _mapping(change.get("source"), "change.source")
    target = _mapping(change.get("target"), "change.target")
    value = _mapping(change.get("proposed_value"), "change.proposed_value")
    item_type = source.get("item_type")
    lines = [f"프로필 변경 매핑 {position}/{len(changes)}", ""]
    if item_type == "career_evidence":
        lines.append("유형: 경력 근거")
        _optional_line(lines, value.get("role_or_context"), "역할 또는 맥락", "role")
        _optional_line(lines, value.get("period_expression"), "기간 표현", "period")
        _optional_line(
            lines,
            value.get("responsibility_evidence"),
            "수행 내용",
            "responsibility",
        )
    elif item_type == "achievement_evidence":
        lines.append("유형: 성과 근거")
        _optional_line(lines, value.get("problem_evidence"), "문제 또는 배경", "problem")
        _optional_line(lines, value.get("action_evidence"), "행동", "action")
        _optional_line(lines, value.get("result_evidence"), "결과", "result")
    elif item_type == "technology_evidence":
        lines.append("유형: 새 기술 근거")
        _optional_line(lines, value.get("technology_name"), "기술", "technology")
        _optional_line(lines, value.get("usage_evidence"), "사용 근거", "usage")
    else:
        raise SlackEventError("표시할 프로필 변경 항목 종류가 올바르지 않음")

    profile = _mapping(profile_document.get("profile"), "profile")
    if target.get("mapping_status") == "needs_career_selection":
        career_history = profile.get("career_history")
        if not isinstance(career_history, list) or not career_history:
            raise SlackEventError("선택 가능한 기존 경력이 없음")
        lines.extend(["", "연결 가능한 기존 경력"])
        allowed_values: list[str] = []
        for index, raw_career in enumerate(career_history):
            career = _mapping(raw_career, f"profile.career_history[{index}]")
            career_id = _safe_text(career.get("career_id"), "career_id")
            role = _safe_text(career.get("role"), "career.role")
            period = _safe_text(career.get("period"), "career.period")
            allowed_values.append(career_id)
            lines.append(f"- `{career_id}`: {role}, {period}")
        lines.extend(
            [
                "",
                "이 스레드에서 `@career_break 경력 &lt;경력ID&gt;`로 답해주세요.",
            ]
        )
    elif target.get("mapping_status") == "needs_skill_level_confirmation":
        allowed_values = list(_SKILL_LEVELS)
        lines.extend(
            [
                "",
                "허용 숙련도: `none`, `exposure`, `learning`, `basic`, `project`, `work`",
                "이 스레드에서 `@career_break 기술수준 &lt;숙련도&gt;`로 답해주세요.",
            ]
        )
    else:
        raise SlackEventError("프로필 변경 항목의 매핑 상태가 올바르지 않음")
    lines.extend(
        [
            "",
            "현재는 매핑 확인 단계이며 실제 개인 프로필은 변경하지 않았습니다.",
        ]
    )
    return {
        "public_message": "\n".join(lines),
        "mapping_target": {
            "proposal_id": root["proposal_id"],
            "change_id": change["change_id"],
            "mapping_status": target["mapping_status"],
            "allowed_values": allowed_values,
        },
    }
