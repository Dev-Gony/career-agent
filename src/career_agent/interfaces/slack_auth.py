"""Verify Slack Bot and App Tokens without exposing credential values."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


SLACK_AUTH_SCHEMA_VERSION = "0.1"
SLACK_API_BASE_URL = "https://slack.com/api"
MAX_SLACK_AUTH_RESPONSE_BYTES = 64 * 1024

_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_APP_ID_PATTERN = re.compile(r"^A[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_BOT_ID_PATTERN = re.compile(r"^B[A-Za-z0-9]{6,31}$")
_AUTH_ID_PATTERN = re.compile(r"^slack-auth-[0-9a-f]{24}$")


class SlackAuthenticationError(ValueError):
    """Raised when Slack credential verification cannot be completed safely."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


def _text(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SlackAuthenticationError(f"Slack 인증 응답의 {name} 형식이 올바르지 않음")
    return value


def _post_json(
    method: str,
    token: str,
    *,
    open_url: Callable[..., Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    if method not in {"auth.test", "apps.connections.open"}:
        raise SlackAuthenticationError("허용되지 않은 Slack 인증 API 메서드")
    request = Request(
        f"{SLACK_API_BASE_URL}/{method}",
        data=b"",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "career-agent-personal-mvp/0.1",
        },
        method="POST",
    )
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None)
            if status is None:
                status = response.getcode()
            if status != 200:
                raise SlackAuthenticationError(
                    f"Slack 인증 API HTTP 상태가 올바르지 않음: {status}"
                )
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type.casefold():
                raise SlackAuthenticationError("Slack 인증 API 응답이 JSON이 아님")
            raw = response.read(MAX_SLACK_AUTH_RESPONSE_BYTES + 1)
    except SlackAuthenticationError:
        raise
    except (HTTPError, URLError, OSError) as error:
        raise SlackAuthenticationError(
            f"Slack 인증 API 요청 실패: {type(error).__name__}"
        ) from error
    if len(raw) > MAX_SLACK_AUTH_RESPONSE_BYTES:
        raise SlackAuthenticationError("Slack 인증 API 응답이 너무 큼")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SlackAuthenticationError("Slack 인증 API JSON을 해석할 수 없음") from error
    if not isinstance(payload, Mapping):
        raise SlackAuthenticationError("Slack 인증 API 최상위 응답이 객체가 아님")
    if payload.get("ok") is not True:
        error_code = payload.get("error")
        safe_error = error_code if isinstance(error_code, str) else "unknown_error"
        raise SlackAuthenticationError(f"Slack 인증 거부: {safe_error}")
    return payload


def verify_slack_authentication(
    app_token: str,
    bot_token: str,
    *,
    verified_at: datetime,
    open_url: Callable[..., Any] = _open_without_redirect,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    """Verify two tokens and return only non-secret Slack identity fields."""

    if verified_at.tzinfo is None or verified_at.utcoffset() is None:
        raise SlackAuthenticationError("verified_at은 시간대가 포함되어야 함")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 30:
        raise SlackAuthenticationError("timeout_seconds는 0초 초과 30초 이하여야 함")
    if not isinstance(bot_token, str) or not bot_token.startswith("xoxb-"):
        raise SlackAuthenticationError("Bot Token 형식이 올바르지 않음")
    if not isinstance(app_token, str) or not app_token.startswith("xapp-"):
        raise SlackAuthenticationError("App Token 형식이 올바르지 않음")

    bot_identity = _post_json(
        "auth.test",
        bot_token,
        open_url=open_url,
        timeout_seconds=float(timeout_seconds),
    )
    socket_identity = _post_json(
        "apps.connections.open",
        app_token,
        open_url=open_url,
        timeout_seconds=float(timeout_seconds),
    )
    team_id = _text(bot_identity.get("team_id"), "team_id", _TEAM_ID_PATTERN)
    bot_user_id = _text(bot_identity.get("user_id"), "user_id", _USER_ID_PATTERN)
    bot_id = _text(bot_identity.get("bot_id"), "bot_id", _BOT_ID_PATTERN)
    raw_app_id = bot_identity.get("app_id")
    api_app_id = (
        _text(raw_app_id, "app_id", _APP_ID_PATTERN)
        if raw_app_id is not None
        else None
    )
    socket_url = socket_identity.get("url")
    if not isinstance(socket_url, str):
        raise SlackAuthenticationError("Socket Mode URL이 인증 응답에 없음")
    parsed_socket_url = urlparse(socket_url)
    if parsed_socket_url.scheme != "wss" or not parsed_socket_url.hostname:
        raise SlackAuthenticationError("Socket Mode URL 형식이 올바르지 않음")

    identity_key = f"{team_id}|{api_app_id or 'unknown'}|{bot_user_id}|{bot_id}"
    auth_id = "slack-auth-" + sha256(identity_key.encode("utf-8")).hexdigest()[:24]
    return {
        "slack_authentication": {
            "auth_id": auth_id,
            "verified_at": verified_at.isoformat(timespec="microseconds"),
            "bot_token_status": "verified",
            "app_token_status": "verified",
            "socket_mode_status": "available",
        },
        "identity": {
            "team_id": team_id,
            "api_app_id": api_app_id,
            "bot_user_id": bot_user_id,
            "bot_id": bot_id,
        },
        "metadata": {
            "schema_version": SLACK_AUTH_SCHEMA_VERSION,
            "contains_tokens": False,
            "contains_socket_url": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
        },
    }


def save_slack_authentication_result(
    result: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse a token-free Slack authentication result."""

    root = result.get("slack_authentication")
    metadata = result.get("metadata")
    if not isinstance(root, Mapping) or not isinstance(metadata, Mapping):
        raise SlackAuthenticationError("Slack 인증 결과 객체가 올바르지 않음")
    auth_id = root.get("auth_id")
    if not isinstance(auth_id, str) or _AUTH_ID_PATTERN.fullmatch(auth_id) is None:
        raise SlackAuthenticationError("Slack 인증 결과 ID가 올바르지 않음")
    if metadata.get("schema_version") != SLACK_AUTH_SCHEMA_VERSION:
        raise SlackAuthenticationError("현재 버전의 Slack 인증 결과가 아님")
    if metadata.get("contains_tokens") is not False:
        raise SlackAuthenticationError("Slack 인증 결과에 Token 제외 표시가 없음")
    if metadata.get("contains_socket_url") is not False:
        raise SlackAuthenticationError("Slack 인증 결과에 Socket URL 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise SlackAuthenticationError("Slack 인증 결과에 Git 제외 표시가 없음")

    output_directory = Path(directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    target_path = output_directory / f"{auth_id}.json"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SlackAuthenticationError(
                f"기존 Slack 인증 결과를 읽을 수 없음: {target_path}"
            ) from error
        if not isinstance(existing, dict):
            raise SlackAuthenticationError("기존 Slack 인증 결과 최상위 JSON이 객체가 아님")
        existing_root = existing.get("slack_authentication")
        if not isinstance(existing_root, Mapping):
            raise SlackAuthenticationError("기존 Slack 인증 결과 객체가 올바르지 않음")
        comparable_existing = dict(existing)
        comparable_result = dict(result)
        existing_root_without_time = dict(existing_root)
        current_root_without_time = dict(root)
        existing_root_without_time.pop("verified_at", None)
        current_root_without_time.pop("verified_at", None)
        comparable_existing["slack_authentication"] = existing_root_without_time
        comparable_result["slack_authentication"] = current_root_without_time
        if comparable_existing != comparable_result:
            raise SlackAuthenticationError("같은 Slack 인증 ID의 기존 내용이 일치하지 않음")
        return target_path, False

    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_directory,
            prefix=f".{auth_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise SlackAuthenticationError(
            f"Slack 인증 결과를 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True
