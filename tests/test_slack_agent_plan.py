from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces.slack_agent_plan import (  # noqa: E402
    SLACK_AGENT_PLAN_CONTRACT_VERSION,
    SlackAgentPlanError,
    build_slack_agent_planning_request,
    plan_slack_agent_turn,
    slack_agent_plan_json_schema,
    validate_slack_agent_plan,
    validate_slack_agent_planning_request,
)


def _execute_plan(*tools: str, search_focus_roles: tuple[str, ...] = ()) -> dict:
    reasons = {
        "find_next_job": "job_search_requested",
        "analyze_profile_attachment": "profile_attachment_received",
        "show_profile_summary": "profile_summary_requested",
        "start_profile_review": "profile_review_requested",
    }
    return {
        "contract_version": SLACK_AGENT_PLAN_CONTRACT_VERSION,
        "intent": "execute",
        "steps": [
            {"tool": tool, "reason_code": reasons[tool]}
            for tool in tools
        ],
        "search_focus_roles": list(search_focus_roles),
        "clarification_code": None,
    }


class _Provider:
    def __init__(self, response: dict, *, external: bool) -> None:
        self.sends_data_externally = external
        self.response = response
        self.calls = []

    def plan(self, request, response_schema):
        self.calls.append((request, response_schema))
        return deepcopy(self.response)


class SlackAgentPlanTest(unittest.TestCase):
    def test_schema_has_no_argument_or_free_text_output_channel(self) -> None:
        schema = slack_agent_plan_json_schema()

        self.assertFalse(schema["additionalProperties"])
        step = schema["properties"]["steps"]["items"]
        self.assertFalse(step["additionalProperties"])
        self.assertEqual({"tool", "reason_code"}, set(step["properties"]))
        serialized = repr(schema).casefold()
        for forbidden in ("argument", "approval", "reject", "shell", "path", "url"):
            self.assertNotIn(forbidden, serialized)

    def test_request_is_minimal_and_keeps_message_only_in_runtime_value(self) -> None:
        request = build_slack_agent_planning_request(
            "내 이력서를 보고 다음 공고를 찾아줘",
            has_validated_attachment=True,
        )

        self.assertEqual(
            {"contract_version", "message_text", "has_validated_attachment"},
            set(request),
        )
        self.assertEqual(request, validate_slack_agent_planning_request(request))

    def test_request_rejects_extra_persistence_metadata_and_control_text(self) -> None:
        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_planning_request(
                {
                    "contract_version": SLACK_AGENT_PLAN_CONTRACT_VERSION,
                    "message_text": "다음 공고",
                    "has_validated_attachment": False,
                    "message_log_path": "private/message.txt",
                }
            )
        with self.assertRaises(SlackAgentPlanError):
            build_slack_agent_planning_request(
                "다음\x00공고",
                has_validated_attachment=False,
            )

    def test_request_enforces_slack_message_length_boundary(self) -> None:
        accepted = build_slack_agent_planning_request(
            "가" * 4_000,
            has_validated_attachment=False,
        )
        self.assertEqual(4_000, len(accepted["message_text"]))

        with self.assertRaises(SlackAgentPlanError):
            build_slack_agent_planning_request(
                "가" * 4_001,
                has_validated_attachment=False,
            )

    def test_validates_one_to_three_unique_steps(self) -> None:
        validated = validate_slack_agent_plan(
            _execute_plan("show_profile_summary", "find_next_job"),
            has_validated_attachment=False,
        )
        self.assertEqual("execute", validated["intent"])

        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_plan(
                _execute_plan(),
                has_validated_attachment=False,
            )
        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_plan(
                _execute_plan(
                    "show_profile_summary",
                    "find_next_job",
                    "start_profile_review",
                    "show_profile_summary",
                ),
                has_validated_attachment=False,
            )
        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_plan(
                _execute_plan("find_next_job", "find_next_job"),
                has_validated_attachment=False,
            )

    def test_rejects_unknown_tool_argument_and_wrong_reason(self) -> None:
        for invalid_step in (
            {"tool": "run_shell", "reason_code": "job_search_requested"},
            {
                "tool": "find_next_job",
                "reason_code": "job_search_requested",
                "url": "https://example.invalid",
            },
            {"tool": "find_next_job", "reason_code": "profile_review_requested"},
        ):
            plan = _execute_plan("find_next_job")
            plan["steps"] = [invalid_step]
            with self.subTest(invalid_step=invalid_step):
                with self.assertRaises(SlackAgentPlanError):
                    validate_slack_agent_plan(
                        plan,
                        has_validated_attachment=False,
                    )

    def test_attachment_tool_requires_validated_attachment_and_first_position(self) -> None:
        validate_slack_agent_plan(
            _execute_plan("analyze_profile_attachment", "find_next_job"),
            has_validated_attachment=True,
        )
        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_plan(
                _execute_plan("analyze_profile_attachment"),
                has_validated_attachment=False,
            )
        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_plan(
                _execute_plan("find_next_job", "analyze_profile_attachment"),
                has_validated_attachment=True,
            )

    def test_clarify_requires_zero_steps_and_limited_code(self) -> None:
        plan = {
            "contract_version": SLACK_AGENT_PLAN_CONTRACT_VERSION,
            "intent": "clarify",
            "steps": [],
            "search_focus_roles": [],
            "clarification_code": "request_unclear",
        }
        self.assertEqual(
            "clarify",
            validate_slack_agent_plan(
                plan,
                has_validated_attachment=False,
            )["intent"],
        )

        for invalid_code in (None, "ask_for_approval", "attachment_required"):
            invalid = deepcopy(plan)
            invalid["clarification_code"] = invalid_code
            with self.subTest(invalid_code=invalid_code):
                if invalid_code == "attachment_required":
                    has_attachment = True
                else:
                    has_attachment = False
                with self.assertRaises(SlackAgentPlanError):
                    validate_slack_agent_plan(
                        invalid,
                        has_validated_attachment=has_attachment,
                    )

    def test_external_provider_is_blocked_before_call_without_explicit_approval(self) -> None:
        provider = _Provider(_execute_plan("find_next_job"), external=True)
        request = build_slack_agent_planning_request(
            "새 공고를 찾아줘",
            has_validated_attachment=False,
        )

        with self.assertRaises(SlackAgentPlanError):
            plan_slack_agent_turn(provider, request)
        self.assertEqual([], provider.calls)

        result = plan_slack_agent_turn(
            provider,
            request,
            explicit_external_transfer_approved=True,
        )
        self.assertEqual("find_next_job", result["steps"][0]["tool"])
        self.assertEqual(1, len(provider.calls))

    def test_validates_bounded_search_focus_only_for_job_search(self) -> None:
        plan = validate_slack_agent_plan(
            _execute_plan(
                "find_next_job",
                search_focus_roles=("QA Engineer", "Test Automation Engineer"),
            ),
            has_validated_attachment=False,
        )
        self.assertEqual(
            ["QA Engineer", "Test Automation Engineer"],
            plan["search_focus_roles"],
        )
        for roles in (
            ("one", "two", "three", "four"),
            ("https://example.invalid",),
            ("QA", "qa"),
        ):
            with self.subTest(roles=roles), self.assertRaises(SlackAgentPlanError):
                validate_slack_agent_plan(
                    _execute_plan("find_next_job", search_focus_roles=roles),
                    has_validated_attachment=False,
                )
        with self.assertRaises(SlackAgentPlanError):
            validate_slack_agent_plan(
                _execute_plan(
                    "show_profile_summary",
                    search_focus_roles=("QA Engineer",),
                ),
                has_validated_attachment=False,
            )

    def test_local_provider_does_not_require_external_approval(self) -> None:
        provider = _Provider(_execute_plan("show_profile_summary"), external=False)
        request = build_slack_agent_planning_request(
            "내 프로필을 요약해줘",
            has_validated_attachment=False,
        )

        result = plan_slack_agent_turn(provider, request)

        self.assertEqual("show_profile_summary", result["steps"][0]["tool"])


if __name__ == "__main__":
    unittest.main()
