"""Validate a Slack app mention and map it to one internal action request."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping


SLACK_COMMAND_REQUEST_SCHEMA_VERSION = "0.1"
SLACK_INTERFACE_CONFIG_SCHEMA_VERSION = "0.1"
MAX_SLACK_MESSAGE_CHARS = 4000
NEXT_JOB_COMMAND = "다음 공고 찾아줘"
NEXT_JOB_ACTION = "analyze_next_greenhouse_review"

_EVENT_ID_PATTERN = re.compile(r"^Ev[A-Za-z0-9]{6,62}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_APP_ID_PATTERN = re.compile(r"^A[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_EVENT_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_REQUEST_ID_PATTERN = re.compile(r"^slack-command-request-[0-9a-f]{24}$")


class SlackEventError(ValueError):
    """Raised when a Slack event or local interface config is unsafe."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlackEventError(f"{name} 문자열이 필요함")
    return value.strip()


def _identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    normalized = _text(value, name)
    if pattern.fullmatch(normalized) is None:
        raise SlackEventError(f"{name} 형식이 올바르지 않음")
    return normalized


def _identifier_list(
    value: Any,
    name: str,
    pattern: re.Pattern[str],
) -> frozenset[str]:
    if not isinstance(value, list) or not value:
        raise SlackEventError(f"{name} 비어 있지 않은 배열이 필요함")
    identifiers: list[str] = []
    for position, raw_identifier in enumerate(value):
        identifiers.append(
            _identifier(raw_identifier, f"{name}[{position}]", pattern)
        )
    if len(set(identifiers)) != len(identifiers):
        raise SlackEventError(f"{name}에 중복 ID가 있음")
    return frozenset(identifiers)


def validate_slack_interface_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a private Slack interface allowlist without reading secrets."""

    root = _mapping(config.get("slack_interface"), "slack_interface")
    metadata = _mapping(config.get("metadata"), "metadata")
    if metadata.get("schema_version") != SLACK_INTERFACE_CONFIG_SCHEMA_VERSION:
        raise SlackEventError("현재 버전의 Slack 인터페이스 설정이 아님")
    if metadata.get("contains_secrets") is not False:
        raise SlackEventError("Slack 인터페이스 설정에 비밀정보 제외 표시가 없음")
    team_id = _identifier(root.get("team_id"), "slack_interface.team_id", _TEAM_ID_PATTERN)
    api_app_id = _identifier(
        root.get("api_app_id"),
        "slack_interface.api_app_id",
        _APP_ID_PATTERN,
    )
    bot_user_id = _identifier(
        root.get("bot_user_id"),
        "slack_interface.bot_user_id",
        _USER_ID_PATTERN,
    )
    allowed_user_ids = _identifier_list(
        root.get("allowed_user_ids"),
        "slack_interface.allowed_user_ids",
        _USER_ID_PATTERN,
    )
    allowed_channel_ids = _identifier_list(
        root.get("allowed_channel_ids"),
        "slack_interface.allowed_channel_ids",
        _CHANNEL_ID_PATTERN,
    )
    if bot_user_id in allowed_user_ids:
        raise SlackEventError("bot_user_id는 허용 사용자에 포함할 수 없음")
    return {
        "team_id": team_id,
        "api_app_id": api_app_id,
        "bot_user_id": bot_user_id,
        "allowed_user_ids": allowed_user_ids,
        "allowed_channel_ids": allowed_channel_ids,
    }


def _normalized_command(text: str, bot_user_id: str) -> str:
    mention = f"<@{bot_user_id}>"
    if mention not in text:
        raise SlackEventError("app_mention 본문에 설정된 봇 호출이 없음")
    without_mention = text.replace(mention, " ")
    return " ".join(without_mention.casefold().split())


def build_slack_command_request(
    event_payload: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    received_at: datetime,
) -> dict[str, Any]:
    """Build a non-executing internal request from one Slack app mention."""

    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise SlackEventError("received_at은 시간대가 포함되어야 함")
    settings = validate_slack_interface_config(config)
    if event_payload.get("type") != "event_callback":
        raise SlackEventError("Slack event_callback만 처리할 수 있음")
    event_id = _identifier(event_payload.get("event_id"), "event_id", _EVENT_ID_PATTERN)
    team_id = _identifier(event_payload.get("team_id"), "team_id", _TEAM_ID_PATTERN)
    api_app_id = _identifier(event_payload.get("api_app_id"), "api_app_id", _APP_ID_PATTERN)
    if team_id != settings["team_id"]:
        raise SlackEventError("Slack team_id가 허용 설정과 다름")
    if api_app_id != settings["api_app_id"]:
        raise SlackEventError("Slack api_app_id가 허용 설정과 다름")
    event_time = event_payload.get("event_time")
    if isinstance(event_time, bool) or not isinstance(event_time, int) or event_time < 1:
        raise SlackEventError("event_time 양의 정수가 필요함")

    event = _mapping(event_payload.get("event"), "event")
    if event.get("type") != "app_mention":
        raise SlackEventError("Slack app_mention 이벤트만 처리할 수 있음")
    channel_id = _identifier(event.get("channel"), "event.channel", _CHANNEL_ID_PATTERN)
    event_ts = _identifier(event.get("event_ts"), "event.event_ts", _EVENT_TS_PATTERN)

    reason: str
    action: str | None
    command_name: str | None
    user_id: str | None
    if event.get("bot_id") is not None or event.get("bot_profile") is not None:
        reason = "bot_event"
        action = None
        command_name = None
        user_id = None
    else:
        user_id = _identifier(event.get("user"), "event.user", _USER_ID_PATTERN)
        if user_id == settings["bot_user_id"]:
            reason = "bot_event"
            action = None
            command_name = None
        elif user_id not in settings["allowed_user_ids"]:
            reason = "user_not_allowed"
            action = None
            command_name = None
        elif channel_id not in settings["allowed_channel_ids"]:
            reason = "channel_not_allowed"
            action = None
            command_name = None
        elif event.get("subtype") is not None:
            reason = "message_subtype_not_supported"
            action = None
            command_name = None
        else:
            raw_text = _text(event.get("text"), "event.text")
            if len(raw_text) > MAX_SLACK_MESSAGE_CHARS:
                raise SlackEventError(
                    f"event.text는 {MAX_SLACK_MESSAGE_CHARS}자 이하여야 함"
                )
            command = _normalized_command(raw_text, settings["bot_user_id"])
            if command == NEXT_JOB_COMMAND.casefold():
                reason = "supported_command"
                action = NEXT_JOB_ACTION
                command_name = "find_next_job"
            else:
                reason = "unsupported_command"
                action = None
                command_name = None

    routing_status = "action_identified" if action is not None else "ignored"
    request_key = f"{team_id}|{event_id}"
    request_id = "slack-command-request-" + sha256(
        request_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "slack_command_request": {
            "request_id": request_id,
            "received_at": received_at.isoformat(timespec="microseconds"),
            "routing_status": routing_status,
            "command_name": command_name,
            "action": action,
            "execution_status": "not_executed",
            "reason": reason,
        },
        "source": {
            "event_id": event_id,
            "event_time": event_time,
            "event_ts": event_ts,
            "team_id": team_id,
            "api_app_id": api_app_id,
            "user_id": user_id,
            "channel_id": channel_id,
        },
        "metadata": {
            "schema_version": SLACK_COMMAND_REQUEST_SCHEMA_VERSION,
            "contains_message_text": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "network_request_verified": False,
            "local_validation_only": True,
        },
    }


def save_slack_command_request(
    request: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse one Slack event routing result."""

    root = _mapping(request.get("slack_command_request"), "slack_command_request")
    metadata = _mapping(request.get("metadata"), "metadata")
    request_id = _identifier(
        root.get("request_id"),
        "slack_command_request.request_id",
        _REQUEST_ID_PATTERN,
    )
    if metadata.get("schema_version") != SLACK_COMMAND_REQUEST_SCHEMA_VERSION:
        raise SlackEventError("현재 버전의 Slack 명령 요청이 아님")
    if metadata.get("contains_message_text") is not False:
        raise SlackEventError("Slack 명령 요청에 원문 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise SlackEventError("Slack 명령 요청에 Git 제외 표시가 없음")
    if metadata.get("network_request_verified") is not False:
        raise SlackEventError("로컬 검증 요청은 네트워크 인증 상태일 수 없음")
    if metadata.get("local_validation_only") is not True:
        raise SlackEventError("로컬 검증 전용 표시가 없음")
    if root.get("execution_status") != "not_executed":
        raise SlackEventError("로컬 Slack 요청은 실행 상태일 수 없음")
    if root.get("routing_status") not in {"action_identified", "ignored"}:
        raise SlackEventError("Slack 요청 라우팅 상태가 올바르지 않음")

    output_directory = Path(directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    target_path = output_directory / f"{request_id}.json"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise SlackEventError(
                f"기존 Slack 명령 요청을 읽을 수 없음: {target_path}"
            ) from error
        if not isinstance(existing, dict):
            raise SlackEventError("기존 Slack 명령 요청 최상위 JSON은 객체여야 함")
        comparable_existing = dict(existing)
        comparable_request = dict(request)
        existing_root = dict(
            _mapping(existing.get("slack_command_request"), "slack_command_request")
        )
        current_root = dict(root)
        existing_root.pop("received_at", None)
        current_root.pop("received_at", None)
        comparable_existing["slack_command_request"] = existing_root
        comparable_request["slack_command_request"] = current_root
        if comparable_existing != comparable_request:
            raise SlackEventError("같은 Slack 요청 ID의 기존 내용이 일치하지 않음")
        return target_path, False

    serialized = json.dumps(request, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=output_directory,
            prefix=f".{request_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise SlackEventError(f"Slack 명령 요청을 저장할 수 없음: {target_path}") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True
