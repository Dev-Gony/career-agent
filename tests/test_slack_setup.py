from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import SlackEventError, check_slack_setup  # noqa: E402


EXAMPLE_CONFIG = REPOSITORY_ROOT / "data/slack_interface.example.json"
EXAMPLE_MANIFEST = REPOSITORY_ROOT / "data/slack_app_manifest.example.json"
EXAMPLE_ENV = REPOSITORY_ROOT / ".env.example"


class SlackSetupTest(unittest.TestCase):
    def test_manifest_has_only_minimum_socket_mode_permissions(self) -> None:
        manifest = json.loads(EXAMPLE_MANIFEST.read_text(encoding="utf-8"))

        self.assertEqual(1, manifest["_metadata"]["major_version"])
        self.assertEqual(
            ["app_mentions:read", "chat:write"],
            manifest["oauth_config"]["scopes"]["bot"],
        )
        self.assertEqual(
            ["app_mention"],
            manifest["settings"]["event_subscriptions"]["bot_events"],
        )
        self.assertTrue(manifest["settings"]["socket_mode_enabled"])
        self.assertFalse(manifest["settings"]["interactivity"]["is_enabled"])
        serialized = json.dumps(manifest)
        self.assertNotIn("xapp-", serialized)
        self.assertNotIn("xoxb-", serialized)

    def test_reports_ready_without_returning_token_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_path = Path(directory) / ".env"
            env_path.write_text(
                "SLACK_APP_TOKEN=xapp-123456789012\n"
                "SLACK_BOT_TOKEN=xoxb-123456789012\n",
                encoding="utf-8",
            )
            result = check_slack_setup(
                EXAMPLE_CONFIG,
                env_path,
                environment={},
            )

        self.assertEqual(
            {
                "config_ready": True,
                "app_token_ready": True,
                "bot_token_ready": True,
            },
            result,
        )
        serialized = json.dumps(result)
        self.assertNotIn("xapp-123456789012", serialized)
        self.assertNotIn("xoxb-123456789012", serialized)

    def test_process_environment_can_supply_tokens(self) -> None:
        result = check_slack_setup(
            EXAMPLE_CONFIG,
            REPOSITORY_ROOT / "missing.env",
            environment={
                "SLACK_APP_TOKEN": "xapp-123456789012",
                "SLACK_BOT_TOKEN": "xoxb-123456789012",
            },
        )
        self.assertTrue(result["app_token_ready"])
        self.assertTrue(result["bot_token_ready"])

    def test_rejects_missing_config_without_reading_tokens(self) -> None:
        with self.assertRaisesRegex(SlackEventError, "설정 파일이 없음"):
            check_slack_setup(
                REPOSITORY_ROOT / "private-data/missing-slack-config.json",
                EXAMPLE_ENV,
                environment={},
            )

    def test_rejects_missing_or_placeholder_tokens(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            missing_bot = Path(directory) / ".env"
            missing_bot.write_text(
                "SLACK_APP_TOKEN=xapp-123456789012\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SlackEventError, "SLACK_BOT_TOKEN"):
                check_slack_setup(
                    EXAMPLE_CONFIG,
                    missing_bot,
                    environment={},
                )

        with self.assertRaisesRegex(SlackEventError, "SLACK_APP_TOKEN 형식"):
            check_slack_setup(
                EXAMPLE_CONFIG,
                EXAMPLE_ENV,
                environment={},
            )

    def test_rejects_duplicate_or_malformed_env_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            duplicate = Path(directory) / "duplicate.env"
            duplicate.write_text(
                "SLACK_APP_TOKEN=xapp-123456789012\n"
                "SLACK_APP_TOKEN=xapp-abcdefghijkl\n"
                "SLACK_BOT_TOKEN=xoxb-123456789012\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SlackEventError, "중복"):
                check_slack_setup(EXAMPLE_CONFIG, duplicate, environment={})

            malformed = Path(directory) / "malformed.env"
            malformed.write_text("NOT_AN_ASSIGNMENT", encoding="utf-8")
            with self.assertRaisesRegex(SlackEventError, "줄 형식"):
                check_slack_setup(EXAMPLE_CONFIG, malformed, environment={})


if __name__ == "__main__":
    unittest.main()
