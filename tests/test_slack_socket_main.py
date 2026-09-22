from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from scripts import run_slack_socket  # noqa: E402


class SlackSocketMainTest(unittest.TestCase):
    def test_next_job_does_not_fall_back_to_public_example_profile(self) -> None:
        with (
            patch.object(
                run_slack_socket,
                "resolve_active_profile_path",
                return_value=None,
            ),
            patch.object(run_slack_socket, "run_slack_career_action") as run_action,
            patch.object(
                run_slack_socket,
                "_build_latest_provisional_search_profile",
                side_effect=run_slack_socket.SlackEventError("no draft"),
            ),
        ):
            result = run_slack_socket._run_slack_action(
                "analyze_next_greenhouse_review",
                {},
            )

        self.assertEqual("missing_personal_profile", result["status"])
        self.assertIn("활성 개인 프로필이나 승인된 최신", result["public_message"])
        self.assertIn("공개 예제 프로필로 대신 분석하지 않았습니다", result["public_message"])
        run_action.assert_not_called()

    def test_next_job_uses_latest_approved_provisional_profile(self) -> None:
        provisional = {"profile": {"basic": {"profile_id": "temporary"}}}
        with (
            patch.object(
                run_slack_socket,
                "resolve_active_profile_path",
                return_value=None,
            ),
            patch.object(
                run_slack_socket,
                "_build_latest_provisional_search_profile",
                return_value=provisional,
            ),
            patch.object(
                run_slack_socket,
                "run_slack_career_action",
                return_value={"status": "no_candidate", "public_message": "none"},
            ) as run_action,
        ):
            result = run_slack_socket._run_slack_action(
                "analyze_next_greenhouse_review",
                {},
            )

        self.assertEqual("no_candidate", result["status"])
        self.assertEqual(provisional, run_action.call_args.kwargs["provisional_profile"])

    def test_registers_enabled_gemini_consent_flow(self) -> None:
        register = Mock()
        planner = object()
        with (
            patch.object(sys, "argv", ["run_slack_socket.py"]),
            patch.object(run_slack_socket, "load_slack_interface_config", return_value={}),
            patch.object(run_slack_socket, "load_slack_tokens", return_value=("app", "bot")),
            patch.object(run_slack_socket, "create_slack_bolt_app", return_value=object()),
            patch.object(run_slack_socket, "load_gemini_api_key", return_value="key"),
            patch.object(
                run_slack_socket,
                "GeminiSlackAgentPlanner",
                return_value=planner,
            ),
            patch.object(run_slack_socket, "register_slack_app_mention_listener", register),
            patch.object(run_slack_socket, "run_slack_socket_mode"),
            redirect_stdout(StringIO()),
            redirect_stderr(StringIO()),
        ):
            result = run_slack_socket.main()

        self.assertEqual(0, result)
        self.assertIn(
            "profile_analysis_consent_session_creator",
            register.call_args.kwargs,
        )
        self.assertIs(
            run_slack_socket._create_profile_analysis_consent_session,
            register.call_args.kwargs["profile_analysis_consent_session_creator"],
        )
        self.assertIs(planner, register.call_args.kwargs["agent_planner"])
        self.assertTrue(
            register.call_args.kwargs["agent_external_transfer_approved"]
        )


if __name__ == "__main__":
    unittest.main()
