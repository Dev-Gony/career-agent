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

from career_agent.profile_input import MAX_DOCUMENT_BYTES


SLACK_COMMAND_REQUEST_SCHEMA_VERSION = "0.1"
SLACK_INTERFACE_CONFIG_SCHEMA_VERSION = "0.1"
MAX_SLACK_MESSAGE_CHARS = 4000
NEXT_JOB_COMMAND = "다음 공고 찾아줘"
NEXT_JOB_ACTION = "analyze_next_greenhouse_review"
PROFILE_DOCUMENT_COMMAND = "프로필 분석해줘"
PROFILE_DRAFT_COMMAND = "프로필 초안 보여줘"
PROFILE_DRAFT_ACTION = "show_latest_profile_analysis_draft"

_EVENT_ID_PATTERN = re.compile(r"^Ev[A-Za-z0-9]{6,62}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_APP_ID_PATTERN = re.compile(r"^A[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_EVENT_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_REQUEST_ID_PATTERN = re.compile(r"^slack-command-request-[0-9a-f]{24}$")
_FILE_ID_PATTERN = re.compile(r"^F[A-Za-z0-9]{6,31}$")
_PROFILE_DOCUMENT_MIME_TYPES = {
    ".docx": frozenset(
        {
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        }
    ),
    ".md": frozenset({"text/markdown", "text/plain"}),
    ".pdf": frozenset({"application/pdf"}),
    ".txt": frozenset({"text/plain"}),
}
_PROFILE_DOCUMENT_MODES = {
    ".docx": frozenset({"hosted"}),
    ".md": frozenset({"hosted", "snippet"}),
    ".pdf": frozenset({"hosted"}),
    ".txt": frozenset({"hosted", "snippet"}),
}


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


def build_slack_profile_document_reference(value: Any) -> dict[str, Any]:
    file_object = _mapping(value, "event.files[0]")
    file_id = _identifier(
        file_object.get("id"),
        "event.files[0].id",
        _FILE_ID_PATTERN,
    )
    filename = _text(file_object.get("name"), "event.files[0].name")
    if (
        len(filename) > 255
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise SlackEventError("Slack 첨부파일 이름이 안전하지 않음")
    extension = Path(filename).suffix.casefold()
    allowed_mime_types = _PROFILE_DOCUMENT_MIME_TYPES.get(extension)
    if allowed_mime_types is None:
        allowed = ", ".join(sorted(_PROFILE_DOCUMENT_MIME_TYPES))
        raise SlackEventError(f"Slack 첨부파일 허용 확장자: {allowed}")
    mimetype = _text(
        file_object.get("mimetype"),
        "event.files[0].mimetype",
    ).casefold()
    if mimetype not in allowed_mime_types:
        raise SlackEventError("Slack 첨부파일 확장자와 MIME 형식이 일치하지 않음")
    size_bytes = file_object.get("size")
    if (
        isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or not 1 <= size_bytes <= MAX_DOCUMENT_BYTES
    ):
        raise SlackEventError(
            f"Slack 첨부파일 크기는 1 이상 {MAX_DOCUMENT_BYTES}바이트 이하여야 함"
        )
    if file_object.get("mode") not in _PROFILE_DOCUMENT_MODES[extension]:
        raise SlackEventError("Slack 첨부파일 저장 형식이 지원 범위가 아님")
    if file_object.get("is_external") is not False:
        raise SlackEventError("현재는 Slack 내부에 저장된 파일만 지원함")
    if file_object.get("file_access") == "check_file_info":
        raise SlackEventError("추가 권한 확인이 필요한 Slack Connect 파일은 지원하지 않음")
    return {
        "file_id": file_id,
        "filename": filename,
        "extension": extension,
        "mimetype": mimetype,
        "size_bytes": size_bytes,
        "source_type": "slack_attachment",
        "processing_status": "metadata_validated_download_not_started",
    }


def validate_slack_profile_document_reference(value: Any) -> None:
    reference = _mapping(value, "profile_document")
    _identifier(
        reference.get("file_id"),
        "profile_document.file_id",
        _FILE_ID_PATTERN,
    )
    filename = _text(reference.get("filename"), "profile_document.filename")
    if (
        len(filename) > 255
        or Path(filename).name != filename
        or "/" in filename
        or "\\" in filename
        or "\x00" in filename
    ):
        raise SlackEventError("profile_document.filename이 안전하지 않음")
    extension = reference.get("extension")
    allowed_mime_types = _PROFILE_DOCUMENT_MIME_TYPES.get(extension)
    if allowed_mime_types is None or Path(filename).suffix.casefold() != extension:
        raise SlackEventError("profile_document 확장자가 올바르지 않음")
    if reference.get("mimetype") not in allowed_mime_types:
        raise SlackEventError("profile_document MIME 형식이 올바르지 않음")
    size_bytes = reference.get("size_bytes")
    if (
        isinstance(size_bytes, bool)
        or not isinstance(size_bytes, int)
        or not 1 <= size_bytes <= MAX_DOCUMENT_BYTES
    ):
        raise SlackEventError("profile_document 크기가 올바르지 않음")
    if reference.get("source_type") != "slack_attachment":
        raise SlackEventError("profile_document 입력 출처가 올바르지 않음")
    if (
        reference.get("processing_status")
        != "metadata_validated_download_not_started"
    ):
        raise SlackEventError("profile_document 처리 상태가 올바르지 않음")


def build_slack_command_request(
    event_payload: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    received_at: datetime,
    network_request_verified: bool = False,
) -> dict[str, Any]:
    """Build a non-executing internal request from one Slack app mention."""

    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise SlackEventError("received_at은 시간대가 포함되어야 함")
    if not isinstance(network_request_verified, bool):
        raise SlackEventError("network_request_verified는 bool이어야 함")
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
    profile_document: dict[str, Any] | None = None
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
            files = event.get("files")
            if files is not None and not isinstance(files, list):
                raise SlackEventError("event.files는 배열이어야 함")
            file_count = len(files) if isinstance(files, list) else 0
            if command == NEXT_JOB_COMMAND.casefold() and file_count == 0:
                reason = "supported_command"
                action = NEXT_JOB_ACTION
                command_name = "find_next_job"
            elif command == PROFILE_DRAFT_COMMAND.casefold() and file_count == 0:
                reason = "supported_command"
                action = PROFILE_DRAFT_ACTION
                command_name = "show_profile_analysis_draft"
            elif command in {"", PROFILE_DOCUMENT_COMMAND.casefold()}:
                action = None
                command_name = "submit_profile_document"
                if file_count == 0:
                    reason = "profile_document_missing"
                elif file_count > 1:
                    reason = "profile_document_count_not_supported"
                else:
                    profile_document = build_slack_profile_document_reference(files[0])
                    reason = "profile_document_metadata_validated"
            elif file_count > 0:
                reason = "unexpected_file_for_command"
                action = None
                command_name = None
            else:
                reason = "unsupported_command"
                action = None
                command_name = None

    if action is not None:
        routing_status = "action_identified"
    elif profile_document is not None:
        routing_status = "input_validated"
    else:
        routing_status = "ignored"
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
        **(
            {"profile_document": profile_document}
            if profile_document is not None
            else {}
        ),
        "metadata": {
            "schema_version": SLACK_COMMAND_REQUEST_SCHEMA_VERSION,
            "contains_message_text": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "network_request_verified": network_request_verified,
            "local_validation_only": not network_request_verified,
            **(
                {
                    "contains_file_content": False,
                    "contains_download_url": False,
                }
                if profile_document is not None
                else {}
            ),
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
    network_request_verified = metadata.get("network_request_verified")
    local_validation_only = metadata.get("local_validation_only")
    if not isinstance(network_request_verified, bool):
        raise SlackEventError("Slack 명령 요청의 네트워크 인증 표시가 올바르지 않음")
    if not isinstance(local_validation_only, bool):
        raise SlackEventError("Slack 명령 요청의 로컬 검증 표시가 올바르지 않음")
    if network_request_verified == local_validation_only:
        raise SlackEventError("Slack 명령 요청의 전송 경로 표시가 서로 모순됨")
    if root.get("execution_status") != "not_executed":
        raise SlackEventError("로컬 Slack 요청은 실행 상태일 수 없음")
    if root.get("routing_status") not in {
        "action_identified",
        "input_validated",
        "ignored",
    }:
        raise SlackEventError("Slack 요청 라우팅 상태가 올바르지 않음")
    profile_document = request.get("profile_document")
    if profile_document is not None:
        validate_slack_profile_document_reference(profile_document)
        if root.get("routing_status") != "input_validated":
            raise SlackEventError("Slack 첨부파일과 라우팅 상태가 일치하지 않음")
        if root.get("command_name") != "submit_profile_document":
            raise SlackEventError("Slack 첨부파일 명령이 올바르지 않음")
        if root.get("action") is not None:
            raise SlackEventError("Slack 첨부파일 검증 단계는 실행 동작일 수 없음")
        if root.get("reason") != "profile_document_metadata_validated":
            raise SlackEventError("Slack 첨부파일 검증 이유가 올바르지 않음")
        if metadata.get("contains_file_content") is not False:
            raise SlackEventError("Slack 요청에 파일 내용 제외 표시가 없음")
        if metadata.get("contains_download_url") is not False:
            raise SlackEventError("Slack 요청에 다운로드 URL 제외 표시가 없음")
    elif root.get("routing_status") == "input_validated":
        raise SlackEventError("검증된 Slack 첨부파일 요청에 파일 정보가 없음")

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
