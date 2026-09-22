from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
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
    build_latest_slack_profile_analysis_review_item_result,
    build_latest_slack_profile_analysis_summary,
    build_slack_profile_review_session,
    build_slack_profile_mapping_session,
    build_slack_profile_update_mapping_item_result,
    build_slack_profile_final_proposal_result,
    build_slack_profile_final_session,
    create_slack_bolt_app,
    import_slack_profile_document,
    load_slack_interface_config,
    load_slack_tokens,
    register_slack_app_mention_listener,
    run_slack_career_action,
    run_slack_socket_mode,
    save_slack_profile_review_session,
    save_slack_profile_mapping_session,
    save_slack_profile_final_session,
    select_active_slack_profile_review_session,
    select_active_slack_profile_mapping_session,
    select_active_slack_profile_final_session,
)
from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_review,
    build_profile_analysis_mapping_review,
    build_profile_analysis_update_proposal,
    build_profile_analysis_final_proposal,
    build_profile_analysis_final_review,
    build_profile_analysis_application,
    build_profile_evidence_summary,
    build_profile_text_extraction,
    load_profile_document_import,
    load_profile_analysis_draft,
    load_profile_analysis_update_proposal,
    load_profile_analysis_final_proposal,
    save_profile_analysis_update_proposal,
    save_profile_analysis_review,
    save_profile_analysis_mapping_review,
    save_profile_analysis_final_proposal,
    save_profile_analysis_final_review,
    save_profile_analysis_application,
    save_profile_evidence_summary,
    save_profile_text_extraction,
    select_latest_profile_analysis_draft,
    select_latest_profile_analysis_reviews,
    select_latest_profile_analysis_mapping_reviews,
    select_latest_profile_text_extraction,
)


DEFAULT_CONFIG = REPOSITORY_ROOT / "private-data/slack_interface.json"
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-command-requests"
)
DEFAULT_PROFILE_DOCUMENT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-documents"
)
DEFAULT_PROFILE_EXTRACTION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-extractions"
)
DEFAULT_PROFILE_EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-evidence-summaries"
)
DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-drafts"
)
DEFAULT_PROFILE_ANALYSIS_REVIEW_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-reviews"
)
DEFAULT_SLACK_PROFILE_REVIEW_SESSION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-profile-review-sessions"
)
DEFAULT_PROFILE_ANALYSIS_UPDATE_PROPOSAL_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-update-proposals"
)
DEFAULT_PROFILE_ANALYSIS_MAPPING_REVIEW_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-mapping-reviews"
)
DEFAULT_SLACK_PROFILE_MAPPING_SESSION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-profile-mapping-sessions"
)
DEFAULT_PROFILE_ANALYSIS_FINAL_PROPOSAL_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-final-proposals"
)
DEFAULT_PROFILE_ANALYSIS_FINAL_REVIEW_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-final-reviews"
)
DEFAULT_SLACK_PROFILE_FINAL_SESSION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-profile-final-sessions"
)
DEFAULT_PROFILE_ANALYSIS_APPLICATION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-applications"
)
DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"


def _load_profile() -> dict[str, Any]:
    try:
        profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("기준 사용자 프로필을 읽을 수 없음") from error
    if not isinstance(profile, dict):
        raise SlackEventError("기준 사용자 프로필 형식이 올바르지 않음")
    return profile


def _extract_imported_profile_document(
    import_result: Mapping[str, Any],
    extracted_at: datetime,
) -> dict[str, Any]:
    document_id = import_result.get("document_id")
    if not isinstance(document_id, str) or not document_id:
        raise SlackEventError("저장 결과에 문서 ID가 없음")
    try:
        manifest, content = load_profile_document_import(
            document_id,
            DEFAULT_PROFILE_DOCUMENT_DIRECTORY,
        )
        document_format = manifest["profile_document"].get("document_format")
        if document_format == "pdf":
            return {"status": "unsupported", "document_format": "pdf"}
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=extracted_at,
        )
        _, created = save_profile_text_extraction(
            extraction,
            DEFAULT_PROFILE_EXTRACTION_DIRECTORY,
        )
        evidence_summary = build_profile_evidence_summary(
            extraction,
            _load_profile(),
            analyzed_at=extracted_at,
        )
        save_profile_evidence_summary(
            evidence_summary,
            DEFAULT_PROFILE_EVIDENCE_DIRECTORY,
        )
    except ProfileDocumentError as error:
        raise SlackEventError("저장된 프로필 문서를 추출할 수 없음") from error
    return {
        "status": "extracted" if created else "reused",
        "document_format": document_format,
        "summary": extraction["summary"],
        "evidence_summary": evidence_summary["summary"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="실제 Slack app_mention을 Socket Mode로 받아 안전하게 확인합니다."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    return parser


def _request_context(request: Mapping[str, Any]) -> tuple[Mapping[str, Any], datetime]:
    root = request.get("slack_command_request")
    source = request.get("source")
    if not isinstance(root, Mapping) or not isinstance(source, Mapping):
        raise SlackEventError("Slack 동작 요청 형식이 올바르지 않음")
    received_at_text = root.get("received_at")
    if not isinstance(received_at_text, str):
        raise SlackEventError("Slack 동작 요청 시간이 없음")
    try:
        received_at = datetime.fromisoformat(received_at_text)
    except ValueError as error:
        raise SlackEventError("Slack 동작 요청 시간이 올바르지 않음") from error
    if received_at.tzinfo is None or received_at.utcoffset() is None:
        raise SlackEventError("Slack 동작 요청 시간에 시간대가 필요함")
    return source, received_at


def _run_profile_review_decision(
    action: str,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    source, reviewed_at = _request_context(request)
    try:
        session = select_active_slack_profile_review_session(
            team_id=str(source["team_id"]),
            channel_id=str(source["channel_id"]),
            user_id=str(source["user_id"]),
            thread_ts=str(source["thread_ts"]),
            session_directory=DEFAULT_SLACK_PROFILE_REVIEW_SESSION_DIRECTORY,
            review_directory=DEFAULT_PROFILE_ANALYSIS_REVIEW_DIRECTORY,
        )
        if session is None:
            return {
                "status": "no_active_review_session",
                "public_message": (
                    "이 스레드에 승인 또는 제외할 검토 항목이 없습니다. "
                    "새 메시지에서 `프로필 검토 시작`을 호출해주세요."
                ),
            }
        target = session["target"]
        draft = load_profile_analysis_draft(
            target["draft_id"],
            DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY,
        )
        decision = (
            "approve" if action == PROFILE_REVIEW_APPROVE_ACTION else "reject"
        )
        review = build_profile_analysis_review(
            draft,
            item_type=target["item_type"],
            item_position=target["item_position"],
            decision=decision,
            reviewed_at=reviewed_at,
        )
        save_profile_analysis_review(
            review,
            DEFAULT_PROFILE_ANALYSIS_REVIEW_DIRECTORY,
        )
    except (KeyError, TypeError, ProfileDocumentError) as error:
        raise SlackEventError("Slack 프로필 검토 결정을 안전하게 저장할 수 없음") from error

    outcome = "확인된 정보로 승인" if decision == "approve" else "프로필 후보에서 제외"
    return {
        "status": "completed",
        "public_message": (
            f"표시된 항목을 {outcome}했습니다. "
            "아직 개인 프로필과 공고 검색 조건에는 반영하지 않았습니다. "
            "다음 항목은 새 메시지에서 `프로필 검토 시작`을 호출해 확인할 수 있습니다."
        ),
    }


def _build_latest_profile_update_context(
    created_at: datetime,
) -> Mapping[str, Any]:
    profile = _load_profile()
    try:
        extraction = select_latest_profile_text_extraction(
            DEFAULT_PROFILE_EXTRACTION_DIRECTORY
        )
        if extraction is None:
            return {
                "unavailable_message": (
                    "아직 확인할 프로필 문서 추출 결과가 없습니다. "
                    "먼저 `프로필 분석해줘`와 함께 파일 1개를 첨부해주세요."
                )
            }
        extraction_id = extraction["profile_extraction"]["extraction_id"]
        draft = select_latest_profile_analysis_draft(
            extraction_id,
            DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY,
        )
        if draft is None:
            return {
                "unavailable_message": (
                    "가장 최근 프로필 문서의 검증된 분석 초안이 아직 없습니다. "
                    "개인 프로필은 변경되지 않았습니다."
                )
            }
        draft_id = draft["profile_analysis_draft"]["draft_id"]
        reviews = select_latest_profile_analysis_reviews(
            draft_id,
            DEFAULT_PROFILE_ANALYSIS_REVIEW_DIRECTORY,
        )
        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            reviews.values(),
            created_at=created_at,
        )
        save_profile_analysis_update_proposal(
            proposal,
            DEFAULT_PROFILE_ANALYSIS_UPDATE_PROPOSAL_DIRECTORY,
        )
        proposal_id = proposal["profile_analysis_update_proposal"]["proposal_id"]
        mapping_reviews = select_latest_profile_analysis_mapping_reviews(
            proposal_id,
            DEFAULT_PROFILE_ANALYSIS_MAPPING_REVIEW_DIRECTORY,
        )
    except (KeyError, TypeError, ProfileDocumentError) as error:
        raise SlackEventError("프로필 변경 제안을 안전하게 만들 수 없음") from error
    return {
        "profile": profile,
        "proposal": proposal,
        "mapping_reviews": mapping_reviews,
    }


def _build_latest_profile_update_mapping_result(
    created_at: datetime,
) -> Mapping[str, Any]:
    context = _build_latest_profile_update_context(created_at)
    unavailable_message = context.get("unavailable_message")
    if unavailable_message is not None:
        return {"public_message": unavailable_message, "mapping_target": None}
    return build_slack_profile_update_mapping_item_result(
        context["profile"],
        context["proposal"],
        context["mapping_reviews"],
    )


def _build_latest_profile_final_result(created_at: datetime) -> Mapping[str, Any]:
    context = _build_latest_profile_update_context(created_at)
    unavailable_message = context.get("unavailable_message")
    if unavailable_message is not None:
        return {"public_message": unavailable_message, "final_target": None}
    changes = context["proposal"].get("proposed_changes")
    if not isinstance(changes, list):
        raise SlackEventError("프로필 변경 제안 항목 배열이 없음")
    proposal_summary = context["proposal"].get("summary")
    if (
        not isinstance(proposal_summary, Mapping)
        or proposal_summary.get("unreviewed_count") != 0
        or not changes
    ):
        mapping_result = build_slack_profile_update_mapping_item_result(
            context["profile"],
            context["proposal"],
            context["mapping_reviews"],
        )
        return {
            "public_message": mapping_result["public_message"],
            "final_target": None,
        }
    required_mapping_ids = {
        str(change["change_id"])
        for change in changes
        if isinstance(change, Mapping)
        and isinstance(change.get("target"), Mapping)
        and str(change["target"].get("mapping_status")).startswith("needs_")
    }
    if required_mapping_ids - set(context["mapping_reviews"]):
        return {
            "public_message": (
                "아직 선택하지 않은 프로필 변경 항목이 있습니다. "
                "먼저 `프로필 변경 검토 시작`으로 모든 항목을 확인해주세요."
            ),
            "final_target": None,
        }
    try:
        final_proposal = build_profile_analysis_final_proposal(
            context["profile"],
            context["proposal"],
            context["mapping_reviews"],
            created_at=created_at,
        )
        save_profile_analysis_final_proposal(
            final_proposal,
            DEFAULT_PROFILE_ANALYSIS_FINAL_PROPOSAL_DIRECTORY,
        )
    except ProfileDocumentError as error:
        raise SlackEventError("최종 프로필 변경안을 안전하게 만들 수 없음") from error
    return build_slack_profile_final_proposal_result(
        context["profile"],
        final_proposal,
    )


def _run_profile_mapping_decision(
    action: str,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    source, reviewed_at = _request_context(request)
    arguments = request.get("command_arguments")
    if not isinstance(arguments, Mapping):
        raise SlackEventError("Slack 프로필 변경 선택 인자가 없음")
    selected_value = arguments.get("selected_value")
    if not isinstance(selected_value, str):
        raise SlackEventError("Slack 프로필 변경 선택값이 올바르지 않음")
    try:
        session = select_active_slack_profile_mapping_session(
            team_id=str(source["team_id"]),
            channel_id=str(source["channel_id"]),
            user_id=str(source["user_id"]),
            thread_ts=str(source["thread_ts"]),
            session_directory=DEFAULT_SLACK_PROFILE_MAPPING_SESSION_DIRECTORY,
            review_directory=DEFAULT_PROFILE_ANALYSIS_MAPPING_REVIEW_DIRECTORY,
        )
        if session is None:
            return {
                "status": "no_active_mapping_session",
                "public_message": (
                    "이 스레드에 선택할 프로필 변경 항목이 없습니다. "
                    "새 메시지에서 `프로필 변경 검토 시작`을 호출해주세요."
                ),
            }
        target = session["target"]
        expected_action = (
            PROFILE_UPDATE_CAREER_ACTION
            if target["mapping_status"] == "needs_career_selection"
            else PROFILE_UPDATE_SKILL_LEVEL_ACTION
        )
        if action != expected_action:
            return {
                "status": "selection_type_mismatch",
                "public_message": (
                    "표시된 항목에 맞는 답변 형식이 아닙니다. "
                    "스레드에 안내된 `경력 <경력ID>` 또는 `기술수준 <숙련도>` 형식을 확인해주세요."
                ),
            }
        if selected_value not in target["allowed_values"]:
            allowed = ", ".join(f"`{value}`" for value in target["allowed_values"])
            return {
                "status": "selection_not_allowed",
                "public_message": f"허용된 값 중 하나를 선택해주세요: {allowed}",
            }
        proposal = load_profile_analysis_update_proposal(
            target["proposal_id"],
            DEFAULT_PROFILE_ANALYSIS_UPDATE_PROPOSAL_DIRECTORY,
        )
        review = build_profile_analysis_mapping_review(
            _load_profile(),
            proposal,
            change_id=target["change_id"],
            selected_value=selected_value,
            reviewed_at=reviewed_at,
        )
        save_profile_analysis_mapping_review(
            review,
            DEFAULT_PROFILE_ANALYSIS_MAPPING_REVIEW_DIRECTORY,
        )
    except (KeyError, TypeError, ProfileDocumentError) as error:
        raise SlackEventError("Slack 프로필 변경 선택을 안전하게 저장할 수 없음") from error
    selection_label = (
        "경력 연결" if action == PROFILE_UPDATE_CAREER_ACTION else "기술 숙련도"
    )
    return {
        "status": "completed",
        "public_message": (
            f"{selection_label} 선택을 기록했습니다. "
            "아직 개인 프로필에는 적용하지 않았습니다. "
            "다음 항목은 새 메시지에서 `프로필 변경 검토 시작`을 호출해 확인할 수 있습니다."
        ),
    }


def _run_profile_final_decision(
    action: str,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    source, reviewed_at = _request_context(request)
    try:
        session = select_active_slack_profile_final_session(
            team_id=str(source["team_id"]),
            channel_id=str(source["channel_id"]),
            user_id=str(source["user_id"]),
            thread_ts=str(source["thread_ts"]),
            session_directory=DEFAULT_SLACK_PROFILE_FINAL_SESSION_DIRECTORY,
            review_directory=DEFAULT_PROFILE_ANALYSIS_FINAL_REVIEW_DIRECTORY,
        )
        if session is None:
            return {
                "status": "no_active_final_session",
                "public_message": (
                    "이 스레드에 결정할 최종 변경안이 없습니다. "
                    "새 메시지에서 `프로필 최종 검토`를 호출해주세요."
                ),
            }
        final_proposal = load_profile_analysis_final_proposal(
            session["target"]["final_proposal_id"],
            DEFAULT_PROFILE_ANALYSIS_FINAL_PROPOSAL_DIRECTORY,
        )
        decision = "approve" if action == PROFILE_FINAL_APPROVE_ACTION else "reject"
        review = build_profile_analysis_final_review(
            final_proposal,
            decision=decision,
            reviewed_at=reviewed_at,
        )
        save_profile_analysis_final_review(
            review,
            DEFAULT_PROFILE_ANALYSIS_FINAL_REVIEW_DIRECTORY,
        )
        application, updated_profile = build_profile_analysis_application(
            _load_profile(),
            final_proposal,
            review,
            applied_at=reviewed_at,
        )
        save_profile_analysis_application(
            application,
            updated_profile,
            DEFAULT_PROFILE_ANALYSIS_APPLICATION_DIRECTORY,
        )
    except (KeyError, TypeError, ProfileDocumentError) as error:
        raise SlackEventError("Slack 최종 프로필 결정을 안전하게 처리할 수 없음") from error
    if decision == "reject":
        return {
            "status": "rejected",
            "public_message": (
                "최종 변경안을 취소로 기록했습니다. 개인 프로필은 변경하지 않았습니다."
            ),
        }
    return {
        "status": "applied_to_new_version",
        "public_message": (
            "최종 변경안을 승인해 원본과 분리된 새 비공개 프로필 버전을 만들었습니다. "
            "기존 기준 프로필 파일은 덮어쓰지 않았습니다. "
            "새 버전을 공고 검색 조건에 연결하는 작업은 아직 실행하지 않았습니다."
        ),
    }


def _run_slack_action(
    action: str,
    request: Mapping[str, Any],
) -> Mapping[str, Any]:
    if action == PROFILE_DRAFT_ACTION:
        return {
            "status": "completed",
            "public_message": build_latest_slack_profile_analysis_summary(
                str(DEFAULT_PROFILE_EXTRACTION_DIRECTORY),
                str(DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY),
            ),
        }
    if action == PROFILE_REVIEW_ACTION:
        source, created_at = _request_context(request)
        result = build_latest_slack_profile_analysis_review_item_result(
            str(DEFAULT_PROFILE_EXTRACTION_DIRECTORY),
            str(DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY),
            str(DEFAULT_PROFILE_ANALYSIS_REVIEW_DIRECTORY),
        )
        target = result.get("review_target")
        if target is not None:
            try:
                session = build_slack_profile_review_session(
                    team_id=str(source["team_id"]),
                    channel_id=str(source["channel_id"]),
                    user_id=str(source["user_id"]),
                    thread_ts=str(source["thread_ts"]),
                    draft_id=target["draft_id"],
                    extraction_id=target["extraction_id"],
                    item_type=target["item_type"],
                    item_position=target["item_position"],
                    created_at=created_at,
                )
                save_slack_profile_review_session(
                    session,
                    DEFAULT_SLACK_PROFILE_REVIEW_SESSION_DIRECTORY,
                )
            except (KeyError, TypeError) as error:
                raise SlackEventError("Slack 프로필 검토 세션을 만들 수 없음") from error
            result["public_message"] += (
                "\n\n이 항목이 맞으면 이 스레드에서 `@career_break 맞아`, "
                "제외하려면 `@career_break 제외해줘`라고 답해주세요."
            )
        return {
            "status": "completed",
            "public_message": result["public_message"],
        }
    if action in {PROFILE_REVIEW_APPROVE_ACTION, PROFILE_REVIEW_REJECT_ACTION}:
        return _run_profile_review_decision(action, request)
    if action == PROFILE_UPDATE_MAPPING_ACTION:
        source, created_at = _request_context(request)
        result = _build_latest_profile_update_mapping_result(created_at)
        target = result.get("mapping_target")
        if target is not None:
            try:
                session = build_slack_profile_mapping_session(
                    team_id=str(source["team_id"]),
                    channel_id=str(source["channel_id"]),
                    user_id=str(source["user_id"]),
                    thread_ts=str(source["thread_ts"]),
                    proposal_id=target["proposal_id"],
                    change_id=target["change_id"],
                    mapping_status=target["mapping_status"],
                    allowed_values=target["allowed_values"],
                    created_at=created_at,
                )
                save_slack_profile_mapping_session(
                    session,
                    DEFAULT_SLACK_PROFILE_MAPPING_SESSION_DIRECTORY,
                )
            except (KeyError, TypeError) as error:
                raise SlackEventError("Slack 프로필 변경 매핑 세션을 만들 수 없음") from error
        return {
            "status": "completed",
            "public_message": result["public_message"],
        }
    if action in {PROFILE_UPDATE_CAREER_ACTION, PROFILE_UPDATE_SKILL_LEVEL_ACTION}:
        return _run_profile_mapping_decision(action, request)
    if action == PROFILE_FINAL_REVIEW_ACTION:
        source, created_at = _request_context(request)
        result = _build_latest_profile_final_result(created_at)
        target = result.get("final_target")
        if target is not None:
            try:
                session = build_slack_profile_final_session(
                    team_id=str(source["team_id"]),
                    channel_id=str(source["channel_id"]),
                    user_id=str(source["user_id"]),
                    thread_ts=str(source["thread_ts"]),
                    final_proposal_id=target["final_proposal_id"],
                    created_at=created_at,
                )
                save_slack_profile_final_session(
                    session,
                    DEFAULT_SLACK_PROFILE_FINAL_SESSION_DIRECTORY,
                )
            except (KeyError, TypeError) as error:
                raise SlackEventError("Slack 최종 프로필 검토 세션을 만들 수 없음") from error
            result["public_message"] += (
                "\n\n전체 변경을 적용하려면 이 스레드에서 `@career_break 최종 승인`, "
                "적용하지 않으려면 `@career_break 최종 취소`라고 답해주세요."
            )
        return {"status": "completed", "public_message": result["public_message"]}
    if action in {PROFILE_FINAL_APPROVE_ACTION, PROFILE_FINAL_REJECT_ACTION}:
        return _run_profile_final_decision(action, request)
    return run_slack_career_action(
        action,
        repository_root=REPOSITORY_ROOT,
    )


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        config = load_slack_interface_config(args.config)
        app_token, bot_token = load_slack_tokens(args.env_file)
        app = create_slack_bolt_app(bot_token)
        register_slack_app_mention_listener(
            app,
            config,
            output_directory=args.output_directory,
            action_runner=_run_slack_action,
            profile_document_importer=lambda reference, imported_at: (
                import_slack_profile_document(
                    reference,
                    bot_token=bot_token,
                    document_kind="other",
                    imported_at=imported_at,
                    directory=DEFAULT_PROFILE_DOCUMENT_DIRECTORY,
                )
            ),
            profile_document_extractor=_extract_imported_profile_document,
        )
        print("Slack Socket Mode 수신기를 시작합니다.")
        print("- 지원 명령: @career_break 다음 공고 찾아줘")
        print("- 지원 명령: @career_break 프로필 초안 보여줘")
        print("- 지원 명령: @career_break 프로필 검토 시작")
        print("- 지원 명령: @career_break 프로필 변경 검토 시작")
        print("- 검토 스레드 답변: @career_break 맞아 또는 @career_break 제외해줘")
        print("- 변경 스레드 답변: @career_break 경력 <경력ID>")
        print("- 변경 스레드 답변: @career_break 기술수준 <숙련도>")
        print("- 지원 명령: @career_break 프로필 최종 검토")
        print("- 최종 검토 스레드 답변: @career_break 최종 승인 또는 @career_break 최종 취소")
        print("- 지원 입력: @career_break 프로필 분석해줘 + 첨부파일 1개")
        print("- 현재 단계: 공고 1건 분석 또는 첨부파일 저장과 검토 후보 추출")
        print("- 종료: Ctrl+C")
        print("주의: 메시지 원문과 Token은 콘솔에 출력하지 않습니다.")
        run_slack_socket_mode(app, app_token)
    except SlackEventError as error:
        print(f"Slack Socket Mode 시작 실패: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Slack Socket Mode 수신기를 종료했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
