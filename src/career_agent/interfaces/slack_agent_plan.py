"""Provider-neutral contract for a bounded Slack career-agent plan.

The planning request is intentionally transient. This module performs no file,
database, or logging operation and exposes no serializer for the user's message.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol


SLACK_AGENT_PLAN_CONTRACT_VERSION = "slack-agent-plan-v1"
MAX_SLACK_AGENT_MESSAGE_CHARS = 4_000

SLACK_AGENT_TOOLS = frozenset(
    {
        "find_next_job",
        "analyze_profile_attachment",
        "show_profile_summary",
        "start_profile_review",
    }
)

SLACK_AGENT_TOOL_REASON_CODES = {
    "find_next_job": "job_search_requested",
    "analyze_profile_attachment": "profile_attachment_received",
    "show_profile_summary": "profile_summary_requested",
    "start_profile_review": "profile_review_requested",
}

SLACK_AGENT_CLARIFICATION_CODES = frozenset(
    {
        "request_unclear",
        "attachment_required",
    }
)


class SlackAgentPlanError(ValueError):
    """Raised when a planning request or model plan crosses the safe contract."""


class SlackAgentPlannerProvider(Protocol):
    """Minimal provider contract for one transient natural-language turn."""

    sends_data_externally: bool

    def plan(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Return one plan matching the supplied strict JSON Schema."""


def slack_agent_plan_json_schema() -> dict[str, Any]:
    """Return a schema with no argument or free-text output channel."""

    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "contract_version",
            "intent",
            "steps",
            "clarification_code",
        ],
        "properties": {
            "contract_version": {
                "type": "string",
                "const": SLACK_AGENT_PLAN_CONTRACT_VERSION,
            },
            "intent": {
                "type": "string",
                "enum": ["execute", "clarify"],
            },
            "steps": {
                "type": "array",
                "minItems": 0,
                "maxItems": 3,
                "uniqueItems": True,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["tool", "reason_code"],
                    "properties": {
                        "tool": {
                            "type": "string",
                            "enum": sorted(SLACK_AGENT_TOOLS),
                        },
                        "reason_code": {
                            "type": "string",
                            "enum": sorted(
                                set(SLACK_AGENT_TOOL_REASON_CODES.values())
                            ),
                        },
                    },
                },
            },
            "clarification_code": {
                "type": ["string", "null"],
                "enum": [None, *sorted(SLACK_AGENT_CLARIFICATION_CODES)],
            },
        },
    }


def build_slack_agent_planning_request(
    message_text: str,
    *,
    has_validated_attachment: bool,
) -> dict[str, Any]:
    """Build an in-memory-only provider request from one Slack turn."""

    if not isinstance(message_text, str) or not message_text.strip():
        raise SlackAgentPlanError("Slack Agent 계획에는 비어 있지 않은 메시지가 필요함")
    if len(message_text) > MAX_SLACK_AGENT_MESSAGE_CHARS:
        raise SlackAgentPlanError("Slack Agent 계획 메시지가 허용 길이를 초과함")
    if any(
        ord(character) < 32 and character not in {"\n", "\r", "\t"}
        for character in message_text
    ):
        raise SlackAgentPlanError("Slack Agent 계획 메시지에 제어 문자가 포함됨")
    if not isinstance(has_validated_attachment, bool):
        raise SlackAgentPlanError("has_validated_attachment는 bool이어야 함")
    return {
        "contract_version": SLACK_AGENT_PLAN_CONTRACT_VERSION,
        "message_text": message_text,
        "has_validated_attachment": has_validated_attachment,
    }


def validate_slack_agent_planning_request(
    request: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the small transient request before any provider call."""

    if not isinstance(request, Mapping) or set(request) != {
        "contract_version",
        "message_text",
        "has_validated_attachment",
    }:
        raise SlackAgentPlanError("Slack Agent 계획 요청 필드가 올바르지 않음")
    if request.get("contract_version") != SLACK_AGENT_PLAN_CONTRACT_VERSION:
        raise SlackAgentPlanError("Slack Agent 계획 요청 계약 버전이 올바르지 않음")
    return build_slack_agent_planning_request(
        request.get("message_text"),
        has_validated_attachment=request.get("has_validated_attachment"),
    )


def validate_slack_agent_plan(
    plan: Mapping[str, Any],
    *,
    has_validated_attachment: bool,
) -> dict[str, Any]:
    """Validate model output again locally before any tool can run."""

    if not isinstance(has_validated_attachment, bool):
        raise SlackAgentPlanError("has_validated_attachment는 bool이어야 함")
    if not isinstance(plan, Mapping) or set(plan) != {
        "contract_version",
        "intent",
        "steps",
        "clarification_code",
    }:
        raise SlackAgentPlanError("Slack Agent 계획 필드가 올바르지 않음")
    if plan.get("contract_version") != SLACK_AGENT_PLAN_CONTRACT_VERSION:
        raise SlackAgentPlanError("Slack Agent 계획 계약 버전이 올바르지 않음")

    intent = plan.get("intent")
    if intent not in {"execute", "clarify"}:
        raise SlackAgentPlanError("Slack Agent 계획 intent가 올바르지 않음")
    raw_steps = plan.get("steps")
    if not isinstance(raw_steps, list):
        raise SlackAgentPlanError("Slack Agent 계획 steps는 배열이어야 함")
    clarification_code = plan.get("clarification_code")

    if intent == "clarify":
        if raw_steps:
            raise SlackAgentPlanError("clarify 계획은 도구 단계를 포함할 수 없음")
        if clarification_code not in SLACK_AGENT_CLARIFICATION_CODES:
            raise SlackAgentPlanError("clarify 계획의 clarification_code가 올바르지 않음")
        if clarification_code == "attachment_required" and has_validated_attachment:
            raise SlackAgentPlanError("검증된 첨부가 있어 attachment_required를 사용할 수 없음")
        return {
            "contract_version": SLACK_AGENT_PLAN_CONTRACT_VERSION,
            "intent": "clarify",
            "steps": [],
            "clarification_code": clarification_code,
        }

    if clarification_code is not None:
        raise SlackAgentPlanError("execute 계획의 clarification_code는 null이어야 함")
    if not 1 <= len(raw_steps) <= 3:
        raise SlackAgentPlanError("execute 계획은 1개 이상 3개 이하 단계여야 함")

    normalized_steps: list[dict[str, str]] = []
    seen_tools: set[str] = set()
    for index, raw_step in enumerate(raw_steps):
        if not isinstance(raw_step, Mapping) or set(raw_step) != {
            "tool",
            "reason_code",
        }:
            raise SlackAgentPlanError(
                f"Slack Agent 계획 steps[{index}] 필드가 올바르지 않음"
            )
        tool = raw_step.get("tool")
        reason_code = raw_step.get("reason_code")
        if tool not in SLACK_AGENT_TOOLS:
            raise SlackAgentPlanError(
                f"Slack Agent 계획 steps[{index}].tool이 허용되지 않음"
            )
        if reason_code != SLACK_AGENT_TOOL_REASON_CODES[tool]:
            raise SlackAgentPlanError(
                f"Slack Agent 계획 steps[{index}].reason_code가 tool과 일치하지 않음"
            )
        if tool in seen_tools:
            raise SlackAgentPlanError("Slack Agent 계획에 중복 도구가 있음")
        if tool == "analyze_profile_attachment":
            if not has_validated_attachment:
                raise SlackAgentPlanError("검증된 첨부 없이 첨부 분석을 실행할 수 없음")
            if index != 0:
                raise SlackAgentPlanError("첨부 분석은 첫 번째 단계에서만 실행할 수 있음")
        seen_tools.add(tool)
        normalized_steps.append({"tool": tool, "reason_code": reason_code})

    return {
        "contract_version": SLACK_AGENT_PLAN_CONTRACT_VERSION,
        "intent": "execute",
        "steps": normalized_steps,
        "clarification_code": None,
    }


def plan_slack_agent_turn(
    provider: SlackAgentPlannerProvider,
    request: Mapping[str, Any],
    *,
    explicit_external_transfer_approved: bool = False,
) -> dict[str, Any]:
    """Call one planner only after applying the external-transfer boundary."""

    validated_request = validate_slack_agent_planning_request(request)
    sends_data_externally = provider.sends_data_externally
    if not isinstance(sends_data_externally, bool):
        raise SlackAgentPlanError("provider.sends_data_externally는 bool이어야 함")
    if sends_data_externally and explicit_external_transfer_approved is not True:
        raise SlackAgentPlanError("외부 Agent 계획 전송 승인이 필요함")
    response = provider.plan(validated_request, slack_agent_plan_json_schema())
    return validate_slack_agent_plan(
        response,
        has_validated_attachment=validated_request["has_validated_attachment"],
    )
