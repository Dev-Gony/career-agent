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
    def test_registers_enabled_gemini_consent_flow(self) -> None:
        register = Mock()
        with (
            patch.object(sys, "argv", ["run_slack_socket.py"]),
            patch.object(run_slack_socket, "load_slack_interface_config", return_value={}),
            patch.object(run_slack_socket, "load_slack_tokens", return_value=("app", "bot")),
            patch.object(run_slack_socket, "create_slack_bolt_app", return_value=object()),
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


if __name__ == "__main__":
    unittest.main()
