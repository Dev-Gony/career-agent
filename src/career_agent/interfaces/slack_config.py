"""Build a private Slack allowlist config from a verified app identity."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from .slack_auth import SLACK_AUTH_SCHEMA_VERSION
from .slack_events import SlackEventError, validate_slack_interface_config


_AUTH_ID_PATTERN = re.compile(r"^slack-auth-[0-9a-f]{24}$")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlackEventError(f"{name} 문자열이 필요함")
    return value.strip()


def load_slack_authentication_result(
    auth_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load one private token-free authentication result safely."""

    normalized_id = _text(auth_id, "auth_id")
    if _AUTH_ID_PATTERN.fullmatch(normalized_id) is None:
        raise SlackEventError("auth_id 형식이 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError(f"Slack 인증 결과를 읽을 수 없음: {path}") from error
    if not isinstance(value, dict):
        raise SlackEventError("Slack 인증 결과 최상위 JSON은 객체여야 함")
    root = _mapping(value.get("slack_authentication"), "slack_authentication")
    metadata = _mapping(value.get("metadata"), "metadata")
    if root.get("auth_id") != normalized_id:
        raise SlackEventError("Slack 인증 결과 ID가 요청과 일치하지 않음")
    if root.get("bot_token_status") != "verified":
        raise SlackEventError("Bot Token 인증이 완료된 결과가 아님")
    if root.get("app_token_status") != "verified":
        raise SlackEventError("App Token 인증이 완료된 결과가 아님")
    if root.get("socket_mode_status") != "available":
        raise SlackEventError("Socket Mode 사용 가능 결과가 아님")
    if metadata.get("schema_version") != SLACK_AUTH_SCHEMA_VERSION:
        raise SlackEventError("현재 버전의 Slack 인증 결과가 아님")
    if metadata.get("contains_tokens") is not False:
        raise SlackEventError("Slack 인증 결과에 Token 제외 표시가 없음")
    if metadata.get("contains_socket_url") is not False:
        raise SlackEventError("Slack 인증 결과에 Socket URL 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise SlackEventError("Slack 인증 결과에 Git 제외 표시가 없음")
    return value


def build_slack_interface_config(
    authentication_result: Mapping[str, Any],
    *,
    api_app_id: str,
    allowed_user_id: str,
    allowed_channel_id: str,
) -> dict[str, Any]:
    """Combine verified bot identity with an explicit personal allowlist."""

    identity = _mapping(authentication_result.get("identity"), "identity")
    verified_app_id = identity.get("api_app_id")
    if verified_app_id is not None and verified_app_id != api_app_id:
        raise SlackEventError("입력한 App ID가 인증 결과와 일치하지 않음")
    config = {
        "slack_interface": {
            "team_id": _text(identity.get("team_id"), "identity.team_id"),
            "api_app_id": api_app_id,
            "bot_user_id": _text(
                identity.get("bot_user_id"),
                "identity.bot_user_id",
            ),
            "allowed_user_ids": [allowed_user_id],
            "allowed_channel_ids": [allowed_channel_id],
        },
        "metadata": {
            "schema_version": "0.1",
            "data_type": "private_local_config",
            "contains_secrets": False,
            "git_tracking_allowed": False,
        },
    }
    validate_slack_interface_config(config)
    return config


def save_slack_interface_config(
    config: Mapping[str, Any],
    path: str | Path,
) -> tuple[Path, bool]:
    """Atomically create or reuse the private Slack interface config."""

    validate_slack_interface_config(config)
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SlackEventError(
                f"기존 Slack 인터페이스 설정을 읽을 수 없음: {target_path}"
            ) from error
        if existing != config:
            raise SlackEventError("기존 Slack 인터페이스 설정이 새 설정과 일치하지 않음")
        return target_path, False

    serialized = json.dumps(config, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_path.parent,
            prefix=f".{target_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise SlackEventError(f"Slack 인터페이스 설정을 저장할 수 없음: {target_path}") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True
