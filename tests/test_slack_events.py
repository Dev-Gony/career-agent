from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_slack_command_request,
    save_slack_command_request,
)


RECEIVED_AT = datetime(2026, 9, 14, 23, tzinfo=timezone.utc)


def _config() -> dict:
    return {
        "slack_interface": {
            "team_id": "T01234567",
            "api_app_id": "A01234567",
            "bot_user_id": "U01234567",
            "allowed_user_ids": ["U76543210"],
            "allowed_channel_ids": ["C01234567"],
        },
        "metadata": {"schema_version": "0.1", "contains_secrets": False},
    }


def _event(text: str = "<@U01234567> 다음 공고 찾아줘") -> dict:
    return {
        "type": "event_callback",
        "team_id": "T01234567",
        "api_app_id": "A01234567",
        "event": {
            "type": "app_mention",
            "user": "U76543210",
            "text": text,
            "ts": "1789372800.000100",
            "channel": "C01234567",
            "event_ts": "1789372800.000100",
        },
        "event_id": "Ev01234567",
        "event_time": 1789372800,
    }


class SlackEventsTest(unittest.TestCase):
    def test_maps_supported_mention_without_storing_message_text(self) -> None:
        request = build_slack_command_request(
            _event(),
            _config(),
            received_at=RECEIVED_AT,
        )

        root = request["slack_command_request"]
        self.assertEqual("action_identified", root["routing_status"])
        self.assertEqual("find_next_job", root["command_name"])
        self.assertEqual("analyze_next_greenhouse_review", root["action"])
        self.assertEqual("not_executed", root["execution_status"])
        self.assertFalse(request["metadata"]["network_request_verified"])
        serialized = json.dumps(request, ensure_ascii=False)
        self.assertNotIn("다음 공고 찾아줘", serialized)
        self.assertNotIn("<@U01234567>", serialized)

    def test_normalizes_whitespace_and_mention_position(self) -> None:
        request = build_slack_command_request(
            _event("  다음   공고 찾아줘   <@U01234567> "),
            _config(),
            received_at=RECEIVED_AT,
        )
        self.assertEqual(
            "analyze_next_greenhouse_review",
            request["slack_command_request"]["action"],
        )

    def test_ignores_unsupported_command(self) -> None:
        request = build_slack_command_request(
            _event("<@U01234567> 이력서 분석해줘"),
            _config(),
            received_at=RECEIVED_AT,
        )
        root = request["slack_command_request"]
        self.assertEqual("ignored", root["routing_status"])
        self.assertEqual("unsupported_command", root["reason"])
        self.assertIsNone(root["action"])

    def test_ignores_users_and_channels_outside_allowlist(self) -> None:
        user_event = _event()
        user_event["event"]["user"] = "U11111111"
        user_request = build_slack_command_request(
            user_event, _config(), received_at=RECEIVED_AT
        )
        self.assertEqual(
            "user_not_allowed",
            user_request["slack_command_request"]["reason"],
        )

        channel_event = _event()
        channel_event["event"]["channel"] = "C11111111"
        channel_request = build_slack_command_request(
            channel_event, _config(), received_at=RECEIVED_AT
        )
        self.assertEqual(
            "channel_not_allowed",
            channel_request["slack_command_request"]["reason"],
        )

    def test_ignores_bot_event_without_requiring_user_or_text(self) -> None:
        event = _event()
        event["event"].pop("user")
        event["event"].pop("text")
        event["event"]["bot_id"] = "B01234567"
        request = build_slack_command_request(
            event, _config(), received_at=RECEIVED_AT
        )
        self.assertEqual("bot_event", request["slack_command_request"]["reason"])
        self.assertIsNone(request["source"]["user_id"])

    def test_rejects_wrong_workspace_or_app(self) -> None:
        wrong_team = _event()
        wrong_team["team_id"] = "T11111111"
        with self.assertRaisesRegex(SlackEventError, "team_id"):
            build_slack_command_request(
                wrong_team, _config(), received_at=RECEIVED_AT
            )

        wrong_app = _event()
        wrong_app["api_app_id"] = "A11111111"
        with self.assertRaisesRegex(SlackEventError, "api_app_id"):
            build_slack_command_request(
                wrong_app, _config(), received_at=RECEIVED_AT
            )

    def test_rejects_invalid_event_contract(self) -> None:
        wrong_type = _event()
        wrong_type["event"]["type"] = "message"
        with self.assertRaisesRegex(SlackEventError, "app_mention"):
            build_slack_command_request(
                wrong_type, _config(), received_at=RECEIVED_AT
            )

        missing_mention = _event("다음 공고 찾아줘")
        with self.assertRaisesRegex(SlackEventError, "봇 호출"):
            build_slack_command_request(
                missing_mention, _config(), received_at=RECEIVED_AT
            )

        too_long = _event("<@U01234567> " + "a" * 4001)
        with self.assertRaisesRegex(SlackEventError, "4000자"):
            build_slack_command_request(
                too_long, _config(), received_at=RECEIVED_AT
            )

    def test_rejects_unsafe_allowlist_config(self) -> None:
        empty = _config()
        empty["slack_interface"]["allowed_user_ids"] = []
        with self.assertRaisesRegex(SlackEventError, "비어 있지 않은 배열"):
            build_slack_command_request(_event(), empty, received_at=RECEIVED_AT)

        duplicate = _config()
        duplicate["slack_interface"]["allowed_channel_ids"] *= 2
        with self.assertRaisesRegex(SlackEventError, "중복 ID"):
            build_slack_command_request(
                _event(), duplicate, received_at=RECEIVED_AT
            )

        secret_marker = _config()
        secret_marker["metadata"]["contains_secrets"] = True
        with self.assertRaisesRegex(SlackEventError, "비밀정보 제외"):
            build_slack_command_request(
                _event(), secret_marker, received_at=RECEIVED_AT
            )

    def test_rejects_naive_received_timestamp(self) -> None:
        with self.assertRaisesRegex(SlackEventError, "시간대"):
            build_slack_command_request(
                _event(),
                _config(),
                received_at=datetime(2026, 9, 14, 23),
            )

    def test_saves_retry_once_and_rejects_same_event_with_changed_content(self) -> None:
        request = build_slack_command_request(
            _event(), _config(), received_at=RECEIVED_AT
        )
        retry = build_slack_command_request(
            _event(), _config(), received_at=RECEIVED_AT + timedelta(seconds=5)
        )
        changed = build_slack_command_request(
            _event("<@U01234567> 다른 명령"),
            _config(),
            received_at=RECEIVED_AT + timedelta(seconds=10),
        )

        with tempfile.TemporaryDirectory() as directory:
            path, created = save_slack_command_request(request, directory)
            retry_path, retry_created = save_slack_command_request(retry, directory)
            self.assertTrue(created)
            self.assertFalse(retry_created)
            self.assertEqual(path, retry_path)
            self.assertEqual(1, len(list(Path(directory).glob("*.json"))))
            with self.assertRaisesRegex(SlackEventError, "기존 내용"):
                save_slack_command_request(changed, directory)

    def test_rejects_corrupted_existing_request(self) -> None:
        request = build_slack_command_request(
            _event(), _config(), received_at=RECEIVED_AT
        )
        request_id = request["slack_command_request"]["request_id"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{request_id}.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaisesRegex(SlackEventError, "최상위 JSON"):
                save_slack_command_request(request, directory)


if __name__ == "__main__":
    unittest.main()
