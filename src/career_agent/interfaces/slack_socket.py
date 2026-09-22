"""Connect Slack Socket Mode to the validated local command boundary."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Mapping

from .slack_events import (
    PROFILE_EXTERNAL_ANALYSIS_APPROVE_ACTION,
    PROFILE_EXTERNAL_ANALYSIS_REJECT_ACTION,
    PROFILE_DRAFT_ACTION,
    PROFILE_REVIEW_APPROVE_ACTION,
    PROFILE_REVIEW_ACTION,
    PROFILE_REVIEW_REJECT_ACTION,
    PROFILE_UPDATE_MAPPING_ACTION,
    PROFILE_UPDATE_CAREER_ACTION,
    PROFILE_UPDATE_SKILL_LEVEL_ACTION,
    PROFILE_FINAL_REVIEW_ACTION,
    PROFILE_FINAL_APPROVE_ACTION,
    PROFILE_FINAL_REJECT_ACTION,
    SlackEventError,
    build_slack_command_request,
    save_slack_command_request,
)


SUPPORTED_COMMAND_REPLY = (
    "요청을 확인했습니다. 현재는 Slack 연결 검증 단계이므로 "
    "공고 분석은 아직 실행하지 않았습니다."
)
ACTION_STARTED_REPLY = "요청을 확인했습니다. 다음 공고 1건 분석을 시작합니다."
PROFILE_DRAFT_STARTED_REPLY = "요청을 확인했습니다. 최신 프로필 분석 초안을 확인합니다."
PROFILE_REVIEW_STARTED_REPLY = "요청을 확인했습니다. 검토할 프로필 분석 항목을 확인합니다."
PROFILE_REVIEW_APPROVE_STARTED_REPLY = "요청을 확인했습니다. 표시된 항목의 승인을 기록합니다."
PROFILE_REVIEW_REJECT_STARTED_REPLY = "요청을 확인했습니다. 표시된 항목의 제외를 기록합니다."
PROFILE_REVIEW_THREAD_REQUIRED_REPLY = (
    "승인 또는 제외 답변은 `프로필 검토 시작`으로 생성된 스레드 안에서 보내주세요."
)
PROFILE_UPDATE_MAPPING_STARTED_REPLY = (
    "요청을 확인했습니다. 프로필 변경 제안의 매핑 항목을 확인합니다."
)
PROFILE_UPDATE_SELECTION_STARTED_REPLY = (
    "요청을 확인했습니다. 표시된 프로필 변경 항목의 선택을 기록합니다."
)
PROFILE_FINAL_REVIEW_STARTED_REPLY = (
    "요청을 확인했습니다. 적용 전 최종 프로필 변경안을 확인합니다."
)
PROFILE_FINAL_DECISION_STARTED_REPLY = (
    "요청을 확인했습니다. 최종 변경안에 대한 명시적 결정을 기록합니다."
)
PROFILE_FINAL_THREAD_REQUIRED_REPLY = (
    "최종 승인 또는 취소는 `프로필 최종 검토`로 생성된 스레드 안에서 보내주세요."
)
PROFILE_EXTERNAL_ANALYSIS_DECISION_STARTED_REPLY = (
    "요청을 확인했습니다. 외부 AI 분석 전송 결정을 기록합니다."
)
PROFILE_EXTERNAL_ANALYSIS_THREAD_REQUIRED_REPLY = (
    "외부 AI 분석 동의 또는 거부는 파일 분석 결과가 표시된 스레드 안에서 보내주세요."
)
PROFILE_EXTERNAL_ANALYSIS_CONSENT_PROMPT = (
    "외부 AI 분석은 자동으로 실행하지 않습니다. 후보 문장에는 경력, 회사와 "
    "프로젝트 정보가 포함될 수 있습니다. 무료 Gemini의 입력과 응답은 Google의 "
    "제품·모델 개선과 사람 검토에 사용될 수 있습니다. 동의하면 연락처 형태, 파일명, "
    "문서 ID와 로컬 경로를 제외한 최소 후보 텍스트를 Gemini로 전송해 검토 초안을 "
    "만듭니다. 동의하려면 이 스레드에서 "
    "`@career_break 외부 AI 분석 동의`, 전송하지 않으려면 "
    "`@career_break 외부 AI 분석 거부`라고 답해주세요. 동의 전에는 외부 전송이 없습니다."
)
PROFILE_EXTERNAL_ANALYSIS_CONSENT_PREPARATION_FAILED_REPLY = (
    "외부 AI 분석 동의 단계를 준비하지 못했습니다. 문서와 추출 결과는 비공개 저장소에 "
    "남아 있으며 외부 전송은 실행되지 않았습니다."
)
PROFILE_MAPPING_THREAD_REQUIRED_REPLY = (
    "경력 또는 기술수준 답변은 `프로필 변경 검토 시작`으로 생성된 "
    "스레드 안에서 보내주세요."
)
UNSUPPORTED_COMMAND_REPLY = (
    "현재 지원하는 명령은 `다음 공고 찾아줘`, `프로필 초안 보여줘`, "
    "`프로필 검토 시작`과 첨부파일 1개를 포함한 `프로필 분석해줘`입니다."
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
PROFILE_DOCUMENT_EXTRACTION_EMPTY_REPLY = (
    "첨부파일 본문을 확인했지만 프로필 검토 후보를 찾지 못했습니다. "
    "개인 프로필은 변경하지 않았습니다."
)
PROFILE_DOCUMENT_EXTRACTION_UNSUPPORTED_REPLY = (
    "첨부파일은 비공개 문서 저장소에 저장했습니다. "
    "현재 PDF 본문 추출은 아직 지원하지 않습니다. "
    "개인 프로필은 변경하지 않았습니다."
)
PROFILE_DOCUMENT_EXTRACTION_FAILED_REPLY = (
    "첨부파일은 저장했지만 본문에서 프로필 검토 후보를 만들지 못했습니다. "
    "로컬 실행 이력을 확인해주세요. 개인 프로필은 변경하지 않았습니다."
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

_PROFILE_SECTION_LABELS = {
    "career_history": "경력",
    "projects": "프로젝트",
    "skills": "기술",
    "education": "교육",
    "target_roles": "관심 직무",
    "work_preferences": "근무 조건",
}


def _profile_extraction_reply(result: Mapping[str, Any]) -> str:
    status = result.get("status")
    if status == "unsupported" and result.get("document_format") == "pdf":
        return PROFILE_DOCUMENT_EXTRACTION_UNSUPPORTED_REPLY
    if status not in {"extracted", "reused"}:
        raise SlackEventError("프로필 문서 추출 결과 상태가 올바르지 않음")
    summary = result.get("summary")
    if not isinstance(summary, Mapping):
        raise SlackEventError("프로필 문서 추출 요약이 없음")
    candidate_count = summary.get("candidate_count")
    section_counts = summary.get("section_counts")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count < 0
        or not isinstance(section_counts, Mapping)
    ):
        raise SlackEventError("프로필 문서 추출 요약 형식이 올바르지 않음")
    normalized_counts: list[tuple[str, int]] = []
    for section, count in section_counts.items():
        if (
            section not in _PROFILE_SECTION_LABELS
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
        ):
            raise SlackEventError("프로필 문서 섹션 요약 형식이 올바르지 않음")
        if count:
            normalized_counts.append((section, count))
    if sum(count for _, count in normalized_counts) != candidate_count:
        raise SlackEventError("프로필 문서 후보 합계가 일치하지 않음")
    if candidate_count == 0:
        return PROFILE_DOCUMENT_EXTRACTION_EMPTY_REPLY
    unclassified_count = summary.get("unclassified_nonempty_line_count", 0)
    sensitive_count = summary.get("omitted_sensitive_line_count", 0)
    for name, value in (
        ("미분류 문단 수", unclassified_count),
        ("개인정보 제외 문단 수", sensitive_count),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SlackEventError(f"프로필 문서 {name}가 올바르지 않음")
    details = "\n".join(
        f"- {_PROFILE_SECTION_LABELS[section]}: {count}개"
        for section, count in normalized_counts
    )
    quality_note = (
        "한 영역만 인식해 추가 구조화가 필요합니다."
        if len(normalized_counts) == 1
        else "각 후보는 사용자 검토가 필요합니다."
    )
    evidence_summary = result.get("evidence_summary")
    evidence_lines: list[str] = []
    if evidence_summary is not None:
        if not isinstance(evidence_summary, Mapping):
            raise SlackEventError("프로필 근거 신호 요약 형식이 올바르지 않음")
        evidence_fields = (
            ("기간 표현", "duration_expression_count"),
            ("수치 표현", "quantified_expression_count"),
            ("실행·개선 표현", "action_expression_count"),
            ("기술명 언급", "technology_mention_candidate_count"),
        )
        detected_lines = []
        for label, field in evidence_fields:
            value = evidence_summary.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not 0 <= value <= candidate_count
            ):
                raise SlackEventError(f"프로필 근거 신호 {field}가 올바르지 않음")
            detected_lines.append(f"- {label}: {value}개 문장")
        evidence_lines = [
            "",
            "자동 탐지 근거 신호(미확정)",
            *detected_lines,
        ]
    analysis_draft_summary = result.get("analysis_draft_summary")
    draft_lines: list[str] = []
    if analysis_draft_summary is not None:
        if not isinstance(analysis_draft_summary, Mapping):
            raise SlackEventError("로컬 프로필 분석 초안 요약 형식이 올바르지 않음")
        draft_fields = (
            ("경력·프로젝트 수행 근거", "career_evidence_count"),
            ("성과 후보", "achievement_evidence_count"),
            ("기술 사용 후보", "technology_evidence_count"),
            ("추가 확인 질문", "unknown_count"),
        )
        draft_counts: list[str] = []
        for label, field in draft_fields:
            value = analysis_draft_summary.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise SlackEventError(f"로컬 프로필 분석 초안 {field}가 올바르지 않음")
            draft_counts.append(f"- {label}: {value}개")
        draft_lines = [
            "",
            "로컬 검증 초안",
            *draft_counts,
            "이 초안은 외부 전송 없이 만들어졌으며 각 항목은 사용자 확인 전까지 미확정입니다.",
            "`@career_break 프로필 초안 보여줘`로 요약을 보고, "
            "`@career_break 프로필 검토 시작`으로 항목을 한 건씩 확인할 수 있습니다.",
        ]
    reply_lines = [
        "첨부파일 1차 문단 분류를 완료했습니다.",
        f"- 프로필 검토 후보: {candidate_count}개",
        *details.splitlines(),
        f"- 미분류 문단: {unclassified_count}개",
        f"- 개인정보 형태 제외: {sensitive_count}개",
        *evidence_lines,
        *draft_lines,
        "",
        f"분류 품질: 확인 필요. {quality_note}",
        "이 결과는 이력서의 최종 분석 결과가 아니며, "
        "아직 개인 프로필에는 반영하지 않았습니다.",
    ]
    return "\n".join(reply_lines)


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
    if root.get("reason") == "profile_review_thread_required":
        return PROFILE_REVIEW_THREAD_REQUIRED_REPLY
    if root.get("reason") == "profile_mapping_thread_required":
        return PROFILE_MAPPING_THREAD_REQUIRED_REPLY
    if root.get("reason") == "profile_final_thread_required":
        return PROFILE_FINAL_THREAD_REQUIRED_REPLY
    if root.get("reason") == "profile_external_analysis_consent_thread_required":
        return PROFILE_EXTERNAL_ANALYSIS_THREAD_REQUIRED_REPLY
    return None


def _action_started_reply(action: str) -> str:
    if action == PROFILE_DRAFT_ACTION:
        return PROFILE_DRAFT_STARTED_REPLY
    if action == PROFILE_REVIEW_ACTION:
        return PROFILE_REVIEW_STARTED_REPLY
    if action == PROFILE_REVIEW_APPROVE_ACTION:
        return PROFILE_REVIEW_APPROVE_STARTED_REPLY
    if action == PROFILE_REVIEW_REJECT_ACTION:
        return PROFILE_REVIEW_REJECT_STARTED_REPLY
    if action == PROFILE_UPDATE_MAPPING_ACTION:
        return PROFILE_UPDATE_MAPPING_STARTED_REPLY
    if action in {PROFILE_UPDATE_CAREER_ACTION, PROFILE_UPDATE_SKILL_LEVEL_ACTION}:
        return PROFILE_UPDATE_SELECTION_STARTED_REPLY
    if action == PROFILE_FINAL_REVIEW_ACTION:
        return PROFILE_FINAL_REVIEW_STARTED_REPLY
    if action in {PROFILE_FINAL_APPROVE_ACTION, PROFILE_FINAL_REJECT_ACTION}:
        return PROFILE_FINAL_DECISION_STARTED_REPLY
    if action in {
        PROFILE_EXTERNAL_ANALYSIS_APPROVE_ACTION,
        PROFILE_EXTERNAL_ANALYSIS_REJECT_ACTION,
    }:
        return PROFILE_EXTERNAL_ANALYSIS_DECISION_STARTED_REPLY
    return ACTION_STARTED_REPLY


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
    action_runner: Callable[[str, Mapping[str, Any]], Mapping[str, Any]] | None = None,
    profile_document_importer: (
        Callable[[Mapping[str, Any], datetime], Mapping[str, Any]] | None
    ) = None,
    profile_document_extractor: (
        Callable[[Mapping[str, Any], datetime], Mapping[str, Any]] | None
    ) = None,
    profile_analysis_consent_session_creator: (
        Callable[[Mapping[str, Any], Mapping[str, Any], datetime], None] | None
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
                thread_ts=request["source"]["thread_ts"],
            )
            document_stored = False
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
                document_stored = True
                if profile_document_extractor is None:
                    reply_text = PROFILE_DOCUMENT_IMPORT_COMPLETED_REPLY
                else:
                    extraction_result = profile_document_extractor(
                        import_result,
                        received_at,
                    )
                    if not isinstance(extraction_result, Mapping):
                        raise SlackEventError("프로필 문서 추출 결과가 올바르지 않음")
                    reply_text = _profile_extraction_reply(extraction_result)
                    summary = extraction_result.get("summary")
                    candidate_count = (
                        summary.get("candidate_count")
                        if isinstance(summary, Mapping)
                        else 0
                    )
                    if (
                        candidate_count
                        and profile_analysis_consent_session_creator is not None
                    ):
                        try:
                            profile_analysis_consent_session_creator(
                                request,
                                extraction_result,
                                received_at,
                            )
                        except SlackEventError as error:
                            logger.warning("Slack 외부 분석 동의 준비 실패: %s", error)
                            reply_text += (
                                "\n\n"
                                + PROFILE_EXTERNAL_ANALYSIS_CONSENT_PREPARATION_FAILED_REPLY
                            )
                        else:
                            reply_text += "\n\n" + PROFILE_EXTERNAL_ANALYSIS_CONSENT_PROMPT
            except SlackEventError as error:
                logger.warning("Slack 첨부파일 처리 실패: %s", error)
                reply_text = (
                    PROFILE_DOCUMENT_EXTRACTION_FAILED_REPLY
                    if document_stored
                    else PROFILE_DOCUMENT_IMPORT_FAILED_REPLY
                )
            say(
                text=reply_text,
                thread_ts=request["source"]["thread_ts"],
            )
            return
        if action_runner is not None and root["action"] is not None:
            reply_text = _action_started_reply(root["action"])
        say(
            text=reply_text,
            thread_ts=request["source"]["thread_ts"],
        )
        if action_runner is None or root["action"] is None:
            return
        try:
            action_result = action_runner(root["action"], request)
            public_message = action_result.get("public_message")
            if not isinstance(public_message, str) or not public_message.strip():
                raise SlackEventError("Slack 동작 결과의 공개 메시지가 없음")
        except SlackEventError as error:
            logger.warning("Slack 내부 동작 실패: %s", error)
            public_message = (
                "프로필 분석 초안을 확인하지 못했습니다. 로컬 실행 이력을 확인해주세요."
                if root["action"]
                in {
                    PROFILE_DRAFT_ACTION,
                    PROFILE_REVIEW_ACTION,
                    PROFILE_REVIEW_APPROVE_ACTION,
                    PROFILE_REVIEW_REJECT_ACTION,
                    PROFILE_UPDATE_MAPPING_ACTION,
                    PROFILE_UPDATE_CAREER_ACTION,
                    PROFILE_UPDATE_SKILL_LEVEL_ACTION,
                    PROFILE_FINAL_REVIEW_ACTION,
                    PROFILE_FINAL_APPROVE_ACTION,
                    PROFILE_FINAL_REJECT_ACTION,
                    PROFILE_EXTERNAL_ANALYSIS_APPROVE_ACTION,
                    PROFILE_EXTERNAL_ANALYSIS_REJECT_ACTION,
                }
                else "공고 분석을 시작하지 못했습니다. 로컬 실행 이력을 확인해주세요."
            )
        say(
            text=public_message,
            thread_ts=request["source"]["thread_ts"],
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
