"""Connect Slack Socket Mode to the validated local command boundary."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .slack_events import (
    SlackEventError,
    build_slack_command_request,
    save_slack_command_request,
)


SUPPORTED_COMMAND_REPLY = (
    "요청을 확인했습니다. 현재는 Slack 연결 검증 단계이므로 "
    "공고 분석은 아직 실행하지 않았습니다."
)
ACTION_STARTED_REPLY = "요청을 확인했습니다. 다음 공고 1건 분석을 시작합니다."
UNSUPPORTED_COMMAND_REPLY = (
    "현재 지원하는 명령은 `다음 공고 찾아줘`와 첨부파일 1개를 포함한 "
    "`프로필 분석해줘`입니다."
)
PROFILE_DOCUMENT_METADATA_REPLY = (
    "첨부파일 1개의 형식과 크기를 확인했습니다. 현재는 안전한 입력 검증 단계이며 "
    "파일 내용은 아직 내려받거나 분석하지 않았습니다."
)
PROFILE_DOCUMENT_IMPORT_STARTED_REPLY = (
    "첨부파일을 확인했습니다. 비공개 문서 저장소로 가져옵니다."
)
PROFILE_DOCUMENT_IMPORT_COMPLETED_REPLY = (
    "첨부파일을 비공개 문서 저장소에 저장했습니다. "
    "아직 개인 프로필에는 반영하지 않았습니다."
)
PROFILE_DOCUMENT_IMPORT_FAILED_REPLY = (
    "첨부파일을 가져오지 못했습니다. 로컬 실행 이력을 확인해주세요."
)
PROFILE_DOCUMENT_MISSING_REPLY = (
    "`프로필 분석해줘`와 함께 이력서, 포트폴리오, 경력기술서 또는 "
    "직무분석표 파일 1개를 첨부해주세요."
)
PROFILE_DOCUMENT_COUNT_REPLY = "현재는 한 번에 첨부파일 1개만 확인할 수 있습니다."
UNEXPECTED_FILE_REPLY = (
    "첨부자료를 분석하려면 `프로필 분석해줘`라고 호출해주세요."
)


def _reply_text(request: Mapping[str, Any], *, created: bool) -> str | None:
    if not created:
        return None
    root = request.get("slack_command_request")
    if not isinstance(root, Mapping):
        raise SlackEventError("slack_command_request 객체가 필요함")
    if root.get("routing_status") == "action_identified":
        return SUPPORTED_COMMAND_REPLY
    if root.get("reason") == "profile_document_metadata_validated":
        return PROFILE_DOCUMENT_METADATA_REPLY
    if root.get("reason") == "profile_document_missing":
        return PROFILE_DOCUMENT_MISSING_REPLY
    if root.get("reason") == "profile_document_count_not_supported":
        return PROFILE_DOCUMENT_COUNT_REPLY
    if root.get("reason") == "unexpected_file_for_command":
        return UNEXPECTED_FILE_REPLY
    if root.get("reason") == "unsupported_command":
        return UNSUPPORTED_COMMAND_REPLY
    return None


def process_slack_app_mention(
    event_payload: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    received_at: datetime,
    output_directory: str | Path,
) -> dict[str, Any]:
    """Validate, store, and choose a fixed reply for one Slack mention."""

    request = build_slack_command_request(
        event_payload,
        config,
        received_at=received_at,
        network_request_verified=True,
    )
    output_path, created = save_slack_command_request(request, output_directory)
    return {
        "request": request,
        "output_path": output_path,
        "created": created,
        "reply_text": _reply_text(request, created=created),
    }


def register_slack_app_mention_listener(
    app: Any,
    config: Mapping[str, Any],
    *,
    output_directory: str | Path,
    now: Callable[[], datetime] | None = None,
    action_runner: Callable[[str], Mapping[str, str]] | None = None,
    profile_document_importer: (
        Callable[[Mapping[str, Any], datetime], Mapping[str, Any]] | None
    ) = None,
) -> Callable[..., None]:
    """Register the single supported Bolt event listener and return it for tests."""

    clock = now or (lambda: datetime.now().astimezone())

    def handle_app_mention(body: Mapping[str, Any], say: Any, logger: Any) -> None:
        received_at = clock()
        try:
            result = process_slack_app_mention(
                body,
                config,
                received_at=received_at,
                output_directory=output_directory,
            )
        except SlackEventError as error:
            logger.warning("Slack app_mention 거부: %s", error)
            return

        request = result["request"]
        root = request["slack_command_request"]
        reply_text = result["reply_text"]
        if reply_text is None:
            return
        if (
            root.get("command_name") == "submit_profile_document"
            and root.get("routing_status") == "input_validated"
            and profile_document_importer is not None
        ):
            say(
                text=PROFILE_DOCUMENT_IMPORT_STARTED_REPLY,
                thread_ts=request["source"]["event_ts"],
            )
            try:
                import_result = profile_document_importer(
                    request["profile_document"],
                    received_at,
                )
                if (
                    not isinstance(import_result, Mapping)
                    or import_result.get("status") not in {"stored", "reused"}
                ):
                    raise SlackEventError("Slack 첨부파일 저장 결과가 올바르지 않음")
                reply_text = PROFILE_DOCUMENT_IMPORT_COMPLETED_REPLY
            except SlackEventError as error:
                logger.warning("Slack 첨부파일 가져오기 실패: %s", error)
                reply_text = PROFILE_DOCUMENT_IMPORT_FAILED_REPLY
            say(
                text=reply_text,
                thread_ts=request["source"]["event_ts"],
            )
            return
        if action_runner is not None and root["action"] is not None:
            reply_text = ACTION_STARTED_REPLY
        say(
            text=reply_text,
            thread_ts=request["source"]["event_ts"],
        )
        if action_runner is None or root["action"] is None:
            return
        try:
            action_result = action_runner(root["action"])
            public_message = action_result.get("public_message")
            if not isinstance(public_message, str) or not public_message.strip():
                raise SlackEventError("Slack 동작 결과의 공개 메시지가 없음")
        except SlackEventError as error:
            logger.warning("Slack 내부 동작 실패: %s", error)
            public_message = (
                "공고 분석을 시작하지 못했습니다. 로컬 실행 이력을 확인해주세요."
            )
        say(
            text=public_message,
            thread_ts=request["source"]["event_ts"],
        )

    app.event("app_mention")(handle_app_mention)
    return handle_app_mention


def create_slack_bolt_app(bot_token: str) -> Any:
    """Create the official Slack Bolt app without exposing its token."""

    try:
        from slack_bolt import App
    except ImportError as error:
        raise SlackEventError(
            "Slack SDK가 없음: python -m pip install -r requirements.txt 실행 필요"
        ) from error
    return App(token=bot_token)


def run_slack_socket_mode(app: Any, app_token: str) -> None:
    """Start the blocking official Socket Mode handler."""

    try:
        from slack_bolt.adapter.socket_mode import SocketModeHandler
    except ImportError as error:
        raise SlackEventError(
            "Slack SDK가 없음: python -m pip install -r requirements.txt 실행 필요"
        ) from error
    SocketModeHandler(app, app_token).start()
