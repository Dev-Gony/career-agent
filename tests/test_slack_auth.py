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
    SlackAuthenticationError,
    save_slack_authentication_result,
    verify_slack_authentication,
)


VERIFIED_AT = datetime(2026, 9, 14, 23, 30, tzinfo=timezone.utc)
APP_TOKEN = "xapp-123456789012"
BOT_TOKEN = "xoxb-123456789012"


class _Response:
    def __init__(
        self,
        payload: dict | list | bytes,
        *,
        status: int = 200,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self._raw[:limit]


def _success_opener(requests: list) -> object:
    responses = iter(
        [
            _Response(
                {
                    "ok": True,
                    "team_id": "T01234567",
                    "user_id": "U01234567",
                    "bot_id": "B01234567",
                    "app_id": "A01234567",
                }
            ),
            _Response({"ok": True, "url": "wss://wss.slack.com/link/?ticket=secret"}),
        ]
    )

    def open_url(request, *, timeout: float):
        requests.append((request, timeout))
        return next(responses)

    return open_url


class SlackAuthTest(unittest.TestCase):
    def test_verifies_tokens_without_returning_tokens_or_socket_url(self) -> None:
        requests: list = []
        result = verify_slack_authentication(
            APP_TOKEN,
            BOT_TOKEN,
            verified_at=VERIFIED_AT,
            open_url=_success_opener(requests),
        )

        self.assertEqual("verified", result["slack_authentication"]["bot_token_status"])
        self.assertEqual("verified", result["slack_authentication"]["app_token_status"])
        self.assertEqual("T01234567", result["identity"]["team_id"])
        self.assertEqual("A01234567", result["identity"]["api_app_id"])
        self.assertEqual("U01234567", result["identity"]["bot_user_id"])
        serialized = json.dumps(result)
        self.assertNotIn(APP_TOKEN, serialized)
        self.assertNotIn(BOT_TOKEN, serialized)
        self.assertNotIn("ticket=secret", serialized)
        self.assertFalse(result["metadata"]["contains_tokens"])
        self.assertFalse(result["metadata"]["contains_socket_url"])
        self.assertEqual(
            ["https://slack.com/api/auth.test", "https://slack.com/api/apps.connections.open"],
            [request.full_url for request, _ in requests],
        )
        self.assertTrue(all(request.get_method() == "POST" for request, _ in requests))
        self.assertTrue(all(timeout == 10.0 for _, timeout in requests))

    def test_allows_auth_response_without_app_id(self) -> None:
        responses = iter(
            [
                _Response(
                    {
                        "ok": True,
                        "team_id": "T01234567",
                        "user_id": "U01234567",
                        "bot_id": "B01234567",
                    }
                ),
                _Response({"ok": True, "url": "wss://wss.slack.com/link/"}),
            ]
        )

        result = verify_slack_authentication(
            APP_TOKEN,
            BOT_TOKEN,
            verified_at=VERIFIED_AT,
            open_url=lambda *_args, **_kwargs: next(responses),
        )
        self.assertIsNone(result["identity"]["api_app_id"])

    def test_rejects_slack_api_error_without_echoing_token(self) -> None:
        with self.assertRaisesRegex(SlackAuthenticationError, "invalid_auth") as context:
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=lambda *_args, **_kwargs: _Response(
                    {"ok": False, "error": "invalid_auth"}
                ),
            )
        self.assertNotIn(BOT_TOKEN, str(context.exception))

    def test_rejects_invalid_response_contract(self) -> None:
        invalid_identity = iter(
            [
                _Response(
                    {
                        "ok": True,
                        "team_id": "wrong",
                        "user_id": "U01234567",
                        "bot_id": "B01234567",
                    }
                ),
                _Response({"ok": True, "url": "wss://wss.slack.com/link/"}),
            ]
        )
        with self.assertRaisesRegex(SlackAuthenticationError, "team_id"):
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=lambda *_args, **_kwargs: next(invalid_identity),
            )

        invalid_socket = iter(
            [
                _Response(
                    {
                        "ok": True,
                        "team_id": "T01234567",
                        "user_id": "U01234567",
                        "bot_id": "B01234567",
                    }
                ),
                _Response({"ok": True, "url": "https://example.invalid"}),
            ]
        )
        with self.assertRaisesRegex(SlackAuthenticationError, "Socket Mode URL"):
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=lambda *_args, **_kwargs: next(invalid_socket),
            )

    def test_rejects_non_json_and_large_response(self) -> None:
        with self.assertRaisesRegex(SlackAuthenticationError, "JSON이 아님"):
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=lambda *_args, **_kwargs: _Response(
                    b"not-json", content_type="text/plain"
                ),
            )
        with self.assertRaisesRegex(SlackAuthenticationError, "너무 큼"):
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=lambda *_args, **_kwargs: _Response(b"a" * 65537),
            )

    def test_rejects_invalid_inputs(self) -> None:
        opener = _success_opener([])
        with self.assertRaisesRegex(SlackAuthenticationError, "App Token"):
            verify_slack_authentication(
                "wrong",
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=opener,
            )
        with self.assertRaisesRegex(SlackAuthenticationError, "시간대"):
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=datetime(2026, 9, 14, 23, 30),
                open_url=opener,
            )
        with self.assertRaisesRegex(SlackAuthenticationError, "30초"):
            verify_slack_authentication(
                APP_TOKEN,
                BOT_TOKEN,
                verified_at=VERIFIED_AT,
                open_url=opener,
                timeout_seconds=31,
            )

    def test_saves_and_reuses_token_free_result(self) -> None:
        result = verify_slack_authentication(
            APP_TOKEN,
            BOT_TOKEN,
            verified_at=VERIFIED_AT,
            open_url=_success_opener([]),
        )
        later = deepcopy(result)
        later["slack_authentication"]["verified_at"] = (
            VERIFIED_AT + timedelta(minutes=1)
        ).isoformat(timespec="microseconds")
        with tempfile.TemporaryDirectory() as directory:
            path, created = save_slack_authentication_result(result, directory)
            reused_path, reused = save_slack_authentication_result(later, directory)
            self.assertTrue(created)
            self.assertFalse(reused)
            self.assertEqual(path, reused_path)
            stored = path.read_text(encoding="utf-8")
            self.assertNotIn(APP_TOKEN, stored)
            self.assertNotIn(BOT_TOKEN, stored)


if __name__ == "__main__":
    unittest.main()
