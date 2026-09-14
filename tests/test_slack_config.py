from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_slack_interface_config,
    load_slack_authentication_result,
    save_slack_interface_config,
)


AUTH_ID = "slack-auth-0123456789abcdef01234567"


def _authentication_result(*, api_app_id: str | None = None) -> dict:
    return {
        "slack_authentication": {
            "auth_id": AUTH_ID,
            "verified_at": "2026-09-14T23:30:00.000000+00:00",
            "bot_token_status": "verified",
            "app_token_status": "verified",
            "socket_mode_status": "available",
        },
        "identity": {
            "team_id": "T01234567",
            "api_app_id": api_app_id,
            "bot_user_id": "U01234567",
            "bot_id": "B01234567",
        },
        "metadata": {
            "schema_version": "0.1",
            "contains_tokens": False,
            "contains_socket_url": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
        },
    }


def _config() -> dict:
    return build_slack_interface_config(
        _authentication_result(),
        api_app_id="A01234567",
        allowed_user_id="U76543210",
        allowed_channel_id="C01234567",
    )


class SlackConfigTest(unittest.TestCase):
    def test_builds_token_free_config_from_verified_identity(self) -> None:
        config = _config()

        root = config["slack_interface"]
        self.assertEqual("T01234567", root["team_id"])
        self.assertEqual("A01234567", root["api_app_id"])
        self.assertEqual("U01234567", root["bot_user_id"])
        self.assertEqual(["U76543210"], root["allowed_user_ids"])
        self.assertEqual(["C01234567"], root["allowed_channel_ids"])
        serialized = json.dumps(config)
        self.assertNotIn("xoxb-", serialized)
        self.assertNotIn("xapp-", serialized)
        self.assertFalse(config["metadata"]["contains_secrets"])
        self.assertFalse(config["metadata"]["git_tracking_allowed"])

    def test_rejects_app_id_that_disagrees_with_authentication(self) -> None:
        with self.assertRaisesRegex(SlackEventError, "App ID"):
            build_slack_interface_config(
                _authentication_result(api_app_id="A11111111"),
                api_app_id="A01234567",
                allowed_user_id="U76543210",
                allowed_channel_id="C01234567",
            )

    def test_rejects_invalid_explicit_identifiers(self) -> None:
        with self.assertRaisesRegex(SlackEventError, "api_app_id"):
            build_slack_interface_config(
                _authentication_result(),
                api_app_id="wrong",
                allowed_user_id="U76543210",
                allowed_channel_id="C01234567",
            )
        with self.assertRaisesRegex(SlackEventError, "allowed_user_ids"):
            build_slack_interface_config(
                _authentication_result(),
                api_app_id="A01234567",
                allowed_user_id="wrong",
                allowed_channel_id="C01234567",
            )

    def test_loads_only_verified_token_free_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{AUTH_ID}.json"
            path.write_text(
                json.dumps(_authentication_result()),
                encoding="utf-8",
            )
            loaded = load_slack_authentication_result(AUTH_ID, directory)
            self.assertEqual(AUTH_ID, loaded["slack_authentication"]["auth_id"])

            unsafe = _authentication_result()
            unsafe["metadata"]["contains_tokens"] = True
            path.write_text(json.dumps(unsafe), encoding="utf-8")
            with self.assertRaisesRegex(SlackEventError, "Token 제외"):
                load_slack_authentication_result(AUTH_ID, directory)

    def test_rejects_unverified_or_mismatched_authentication_result(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{AUTH_ID}.json"
            unverified = _authentication_result()
            unverified["slack_authentication"]["socket_mode_status"] = "unknown"
            path.write_text(json.dumps(unverified), encoding="utf-8")
            with self.assertRaisesRegex(SlackEventError, "Socket Mode"):
                load_slack_authentication_result(AUTH_ID, directory)

            mismatched = _authentication_result()
            mismatched["slack_authentication"]["auth_id"] = (
                "slack-auth-aaaaaaaaaaaaaaaaaaaaaaaa"
            )
            path.write_text(json.dumps(mismatched), encoding="utf-8")
            with self.assertRaisesRegex(SlackEventError, "일치하지 않음"):
                load_slack_authentication_result(AUTH_ID, directory)

    def test_rejects_unsafe_authentication_id(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SlackEventError, "auth_id 형식"):
                load_slack_authentication_result("../slack-auth-result", directory)

    def test_saves_reuses_and_refuses_to_overwrite_changed_config(self) -> None:
        config = _config()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "slack_interface.json"
            created_path, created = save_slack_interface_config(config, path)
            reused_path, reused = save_slack_interface_config(config, path)
            self.assertTrue(created)
            self.assertFalse(reused)
            self.assertEqual(created_path, reused_path)

            changed = deepcopy(config)
            changed["slack_interface"]["allowed_channel_ids"] = ["C99999999"]
            with self.assertRaisesRegex(SlackEventError, "일치하지 않음"):
                save_slack_interface_config(changed, path)


if __name__ == "__main__":
    unittest.main()
