from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    process_slack_app_mention,
    register_slack_app_mention_listener,
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


def _profile_event() -> dict:
    event = _event("<@U01234567> 프로필 분석해줘")
    event["event"]["files"] = [
        {
            "id": "F01234567",
            "name": "resume.pdf",
            "mimetype": "application/pdf",
            "size": 1024,
            "mode": "hosted",
            "is_external": False,
        }
    ]
    return event


class _FakeApp:
    def __init__(self) -> None:
        self.event_name: str | None = None
        self.listener = None

    def event(self, event_name: str):
        self.event_name = event_name

        def decorator(listener):
            self.listener = listener
            return listener

        return decorator


class _FakeLogger:
    def __init__(self) -> None:
        self.messages: list[tuple] = []

    def warning(self, *args) -> None:
        self.messages.append(args)


class SlackSocketTest(unittest.TestCase):
    def test_supported_mention_is_stored_and_gets_fixed_reply_once(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            first = process_slack_app_mention(
                _event(),
                _config(),
                received_at=RECEIVED_AT,
                output_directory=directory,
            )
            duplicate = process_slack_app_mention(
                _event(),
                _config(),
                received_at=RECEIVED_AT,
                output_directory=directory,
            )

        self.assertTrue(first["created"])
        self.assertIn("연결 검증 단계", first["reply_text"])
        self.assertFalse(duplicate["created"])
        self.assertIsNone(duplicate["reply_text"])
        self.assertEqual(
            "not_executed",
            first["request"]["slack_command_request"]["execution_status"],
        )
        self.assertTrue(first["request"]["metadata"]["network_request_verified"])
        self.assertFalse(first["request"]["metadata"]["local_validation_only"])

    def test_allowed_unsupported_command_gets_help_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = process_slack_app_mention(
                _event("<@U01234567> 이력서 분석해줘"),
                _config(),
                received_at=RECEIVED_AT,
                output_directory=directory,
            )

        self.assertIn("다음 공고 찾아줘", result["reply_text"])
        self.assertIsNone(result["request"]["slack_command_request"]["action"])

    def test_profile_document_metadata_gets_non_execution_reply(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            result = process_slack_app_mention(
                _profile_event(),
                _config(),
                received_at=RECEIVED_AT,
                output_directory=directory,
            )

        self.assertIn("형식과 크기", result["reply_text"])
        self.assertIn("아직", result["reply_text"])
        self.assertIsNone(result["request"]["slack_command_request"]["action"])

    def test_registered_listener_imports_profile_document_once(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        imports: list[tuple] = []
        logger = _FakeLogger()

        def import_document(reference, imported_at):
            imports.append((reference, imported_at))
            return {"status": "stored"}

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=import_document,
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(1, len(imports))
        self.assertEqual("F01234567", imports[0][0]["file_id"])
        self.assertEqual(RECEIVED_AT, imports[0][1])
        self.assertEqual(2, len(replies))
        self.assertIn("비공개 문서 저장소", replies[0]["text"])
        self.assertIn("프로필에는 반영하지 않았습니다", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_reports_safe_profile_import_failure(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        def fail_import(_reference, _imported_at):
            raise SlackEventError("private download details")

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=fail_import,
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(2, len(replies))
        self.assertIn("가져오지 못했습니다", replies[1]["text"])
        self.assertNotIn("private download details", replies[1]["text"])
        self.assertEqual(1, len(logger.messages))

    def test_registered_listener_reports_profile_candidate_counts(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        def import_document(_reference, _imported_at):
            return {"status": "stored", "document_id": "safe-document-id"}

        def extract_document(import_result, extracted_at):
            self.assertEqual("safe-document-id", import_result["document_id"])
            self.assertEqual(RECEIVED_AT, extracted_at)
            return {
                "status": "extracted",
                "document_format": "docx",
                "summary": {
                    "candidate_count": 3,
                    "section_counts": {"career_history": 2, "skills": 1},
                },
                "evidence_summary": {
                    "duration_expression_count": 1,
                    "quantified_expression_count": 1,
                    "action_expression_count": 2,
                    "technology_mention_candidate_count": 1,
                },
                "analysis_draft_summary": {
                    "career_evidence_count": 1,
                    "achievement_evidence_count": 1,
                    "technology_evidence_count": 1,
                    "unknown_count": 2,
                },
            }

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=import_document,
                profile_document_extractor=extract_document,
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(2, len(replies))
        self.assertIn("1차 문단 분류", replies[1]["text"])
        self.assertIn("검토 후보: 3개", replies[1]["text"])
        self.assertIn("경력: 2개", replies[1]["text"])
        self.assertIn("기술: 1개", replies[1]["text"])
        self.assertIn("자동 탐지 근거 신호", replies[1]["text"])
        self.assertIn("기간 표현: 1개 문장", replies[1]["text"])
        self.assertIn("실행·개선 표현: 2개 문장", replies[1]["text"])
        self.assertIn("로컬 검증 초안", replies[1]["text"])
        self.assertIn("경력·프로젝트 수행 근거: 1개", replies[1]["text"])
        self.assertIn("추가 확인 질문: 2개", replies[1]["text"])
        self.assertIn("프로필 검토 시작", replies[1]["text"])
        self.assertIn("외부 전송 없이", replies[1]["text"])
        self.assertNotIn("\n\n\n", replies[1]["text"])
        self.assertIn("최종 분석 결과가 아니며", replies[1]["text"])
        self.assertNotIn("safe-document-id", replies[1]["text"])
        self.assertIn("아직 개인 프로필에는 반영하지 않았습니다", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_prepares_external_analysis_consent_in_same_thread(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        prepared: list[tuple] = []
        logger = _FakeLogger()

        def prepare_consent(request, extraction_result, created_at):
            prepared.append((request, extraction_result, created_at))

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=lambda _reference, _at: {
                    "status": "stored",
                    "document_id": "safe-document-id",
                },
                profile_document_extractor=lambda _result, _at: {
                    "status": "extracted",
                    "document_format": "docx",
                    "extraction_id": "profile-text-extraction-0123456789abcdef01234567",
                    "summary": {
                        "candidate_count": 2,
                        "section_counts": {"career_history": 2},
                    },
                },
                profile_analysis_consent_session_creator=prepare_consent,
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(1, len(prepared))
        self.assertEqual(
            "1789372800.000100",
            prepared[0][0]["source"]["thread_ts"],
        )
        self.assertEqual(RECEIVED_AT, prepared[0][2])
        self.assertIn("무료 Gemini의 입력과 응답", replies[1]["text"])
        self.assertIn("최소 후보 텍스트를 Gemini로 전송", replies[1]["text"])
        self.assertIn("외부 AI 분석 동의", replies[1]["text"])
        self.assertIn("동의 전에는 외부 전송이 없습니다", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_warns_when_only_one_section_is_found(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=lambda _reference, _at: {
                    "status": "stored",
                    "document_id": "safe-document-id",
                },
                profile_document_extractor=lambda _result, _at: {
                    "status": "extracted",
                    "document_format": "docx",
                    "summary": {
                        "candidate_count": 13,
                        "section_counts": {"career_history": 13},
                        "unclassified_nonempty_line_count": 6,
                        "omitted_sensitive_line_count": 1,
                    },
                },
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertIn("한 영역만 인식", replies[1]["text"])
        self.assertIn("미분류 문단: 6개", replies[1]["text"])
        self.assertIn("개인정보 형태 제외: 1개", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_reports_empty_profile_extraction(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=lambda _reference, _at: {
                    "status": "stored",
                    "document_id": "safe-document-id",
                },
                profile_document_extractor=lambda _result, _at: {
                    "status": "extracted",
                    "document_format": "docx",
                    "summary": {"candidate_count": 0, "section_counts": {}},
                },
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertIn("후보를 찾지 못했습니다", replies[1]["text"])
        self.assertIn("프로필은 변경하지 않았습니다", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_keeps_unsupported_pdf_stored(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=lambda _reference, _at: {
                    "status": "stored",
                    "document_id": "safe-document-id",
                },
                profile_document_extractor=lambda _result, _at: {
                    "status": "unsupported",
                    "document_format": "pdf",
                },
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertIn("저장했습니다", replies[1]["text"])
        self.assertIn("PDF 본문 추출", replies[1]["text"])
        self.assertNotIn("가져오지 못했습니다", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_reports_safe_profile_extraction_failure(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        def fail_extraction(_result, _at):
            raise SlackEventError("private extraction details")

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                profile_document_importer=lambda _reference, _at: {
                    "status": "stored",
                    "document_id": "safe-document-id",
                },
                profile_document_extractor=fail_extraction,
            )
            listener(
                _profile_event(),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertIn("첨부파일은 저장했지만", replies[1]["text"])
        self.assertNotIn("private extraction details", replies[1]["text"])
        self.assertEqual(1, len(logger.messages))

    def test_disallowed_user_is_recorded_without_reply(self) -> None:
        event = _event()
        event["event"]["user"] = "U11111111"
        with tempfile.TemporaryDirectory() as directory:
            result = process_slack_app_mention(
                event,
                _config(),
                received_at=RECEIVED_AT,
                output_directory=directory,
            )

        self.assertIsNone(result["reply_text"])
        self.assertEqual(
            "user_not_allowed",
            result["request"]["slack_command_request"]["reason"],
        )

    def test_registered_listener_replies_in_original_message_thread(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()
        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
            )
            listener(_event(), lambda **values: replies.append(values), logger)

        self.assertEqual("app_mention", app.event_name)
        self.assertIs(listener, app.listener)
        self.assertEqual("1789372800.000100", replies[0]["thread_ts"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_rejects_invalid_event_without_reply(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()
        invalid = _event()
        invalid["team_id"] = "T11111111"
        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
            )
            listener(invalid, lambda **values: replies.append(values), logger)

        self.assertEqual([], replies)
        self.assertEqual(1, len(logger.messages))

    def test_registered_listener_runs_identified_action_once(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        actions: list[str] = []
        logger = _FakeLogger()

        def run_action(action: str, _request: dict) -> dict[str, str]:
            actions.append(action)
            return {
                "status": "completed",
                "public_message": "공고 분석 완료",
            }

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                action_runner=run_action,
            )
            listener(_event(), lambda **values: replies.append(values), logger)
            listener(_event(), lambda **values: replies.append(values), logger)

        self.assertEqual(["analyze_next_greenhouse_review"], actions)
        self.assertEqual(2, len(replies))
        self.assertIn("분석을 시작", replies[0]["text"])
        self.assertEqual("공고 분석 완료", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_shows_profile_draft_in_original_thread(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        actions: list[str] = []
        logger = _FakeLogger()

        def run_action(action: str, _request: dict) -> dict[str, str]:
            actions.append(action)
            return {
                "status": "completed",
                "public_message": "프로필 분석 초안이 준비되었습니다.\n- 경력 근거: 1개",
            }

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                action_runner=run_action,
            )
            listener(
                _event("<@U01234567> 프로필 초안 보여줘"),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(["show_latest_profile_analysis_draft"], actions)
        self.assertEqual(2, len(replies))
        self.assertIn("최신 프로필 분석 초안", replies[0]["text"])
        self.assertIn("경력 근거: 1개", replies[1]["text"])
        self.assertEqual("1789372800.000100", replies[1]["thread_ts"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_starts_profile_review_in_original_thread(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        actions: list[str] = []
        logger = _FakeLogger()

        def run_action(action: str, _request: dict) -> dict[str, str]:
            actions.append(action)
            return {
                "status": "completed",
                "public_message": "프로필 분석 항목 1/2\n유형: 경력 근거",
            }

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                action_runner=run_action,
            )
            listener(
                _event("<@U01234567> 프로필 검토 시작"),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(["show_next_profile_analysis_review_item"], actions)
        self.assertEqual(2, len(replies))
        self.assertIn("검토할 프로필 분석 항목", replies[0]["text"])
        self.assertIn("유형: 경력 근거", replies[1]["text"])
        self.assertEqual("1789372800.000100", replies[1]["thread_ts"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_routes_review_answer_to_existing_thread(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        requests: list[dict] = []
        logger = _FakeLogger()
        event = _event("<@U01234567> 맞아")
        event["event"]["thread_ts"] = "1789372700.000900"

        def run_action(action: str, request: dict) -> dict[str, str]:
            self.assertEqual(
                "approve_active_profile_analysis_review_item",
                action,
            )
            requests.append(request)
            return {
                "status": "completed",
                "public_message": "표시된 항목을 승인했습니다.",
            }

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                action_runner=run_action,
            )
            listener(event, lambda **values: replies.append(values), logger)

        self.assertEqual(1, len(requests))
        self.assertEqual("1789372700.000900", requests[0]["source"]["thread_ts"])
        self.assertEqual(2, len(replies))
        self.assertEqual("1789372700.000900", replies[0]["thread_ts"])
        self.assertEqual("1789372700.000900", replies[1]["thread_ts"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_starts_profile_update_mapping(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        actions: list[str] = []
        logger = _FakeLogger()

        def run_action(action: str, _request: dict) -> dict[str, str]:
            actions.append(action)
            return {
                "status": "completed",
                "public_message": "프로필 변경 매핑 1/2\n유형: 경력 근거",
            }

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                action_runner=run_action,
            )
            listener(
                _event("<@U01234567> 프로필 변경 검토 시작"),
                lambda **values: replies.append(values),
                logger,
            )

        self.assertEqual(["show_next_profile_update_mapping_item"], actions)
        self.assertEqual(2, len(replies))
        self.assertIn("프로필 변경 제안", replies[0]["text"])
        self.assertIn("유형: 경력 근거", replies[1]["text"])
        self.assertEqual([], logger.messages)

    def test_registered_listener_reports_safe_action_failure(self) -> None:
        app = _FakeApp()
        replies: list[dict] = []
        logger = _FakeLogger()

        def fail_action(_action: str, _request: dict) -> dict[str, str]:
            raise SlackEventError("private failure details")

        with tempfile.TemporaryDirectory() as directory:
            listener = register_slack_app_mention_listener(
                app,
                _config(),
                output_directory=directory,
                now=lambda: RECEIVED_AT,
                action_runner=fail_action,
            )
            listener(_event(), lambda **values: replies.append(values), logger)

        self.assertEqual(2, len(replies))
        self.assertIn("시작하지 못했습니다", replies[1]["text"])
        self.assertNotIn("private failure details", replies[1]["text"])
        self.assertEqual(1, len(logger.messages))


if __name__ == "__main__":
    unittest.main()
