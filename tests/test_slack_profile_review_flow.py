from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    PROFILE_REVIEW_APPROVE_ACTION,
    PROFILE_REVIEW_ACTION,
    SlackEventError,
    build_slack_profile_review_session,
    save_slack_profile_review_session,
    select_active_slack_profile_review_session,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_draft,
    build_profile_document_import,
    build_profile_text_extraction,
    save_profile_analysis_draft,
    save_profile_text_extraction,
)
from scripts import run_slack_socket  # noqa: E402


CREATED_AT = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


def _saved_draft(root: Path) -> dict:
    source = root / "resume.md"
    source.write_text(
        "## 경력\n- QA Engineer로 API 테스트를 수행했습니다.\n",
        encoding="utf-8",
    )
    manifest, content = build_profile_document_import(
        source,
        document_kind="resume",
        imported_at=CREATED_AT - timedelta(hours=3),
    )
    extraction = build_profile_text_extraction(
        manifest,
        content,
        extracted_at=CREATED_AT - timedelta(hours=2),
    )
    save_profile_text_extraction(extraction, root / "extractions")
    draft = build_profile_analysis_draft(
        extraction,
        {
            "career_evidence": [
                {
                    "role_or_context": "QA Engineer",
                    "period_expression": None,
                    "responsibility_evidence": "API 테스트를 수행했습니다.",
                    "candidate_ids": ["candidate-001"],
                    "confidence": "high",
                }
            ],
            "achievement_evidence": [],
            "technology_evidence": [],
            "unknowns": [],
        },
        analyzed_at=CREATED_AT - timedelta(hours=1),
        provider_name="synthetic",
        model_name="fixture-v1",
        data_boundary="local",
    )
    save_profile_analysis_draft(draft, root / "drafts")
    return draft


def _request(received_at: datetime) -> dict:
    return {
        "slack_command_request": {"received_at": received_at.isoformat()},
        "source": {
            "team_id": "T01234567",
            "channel_id": "C01234567",
            "user_id": "U76543210",
            "thread_ts": "1789372800.000100",
        },
    }


class SlackProfileReviewFlowTest(unittest.TestCase):
    def test_session_contains_only_binding_identifiers(self) -> None:
        session = build_slack_profile_review_session(
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372800.000100",
            draft_id="profile-analysis-draft-0123456789abcdef01234567",
            extraction_id="profile-text-extraction-0123456789abcdef01234567",
            item_type="career_evidence",
            item_position=1,
            created_at=CREATED_AT,
        )
        serialized = json.dumps(session, ensure_ascii=False)

        self.assertFalse(session["metadata"]["contains_message_text"])
        self.assertFalse(session["metadata"]["contains_analysis_text"])
        self.assertNotIn("QA Engineer", serialized)
        self.assertNotIn("candidate-", serialized)

        session["target"]["extraction_id"] = (
            "profile-text-extraction-ffffffffffffffffffffffff"
        )
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SlackEventError, "내용 지문"):
                save_slack_profile_review_session(session, directory)

    def test_full_slack_review_flow_records_once_and_skips_reviewed_item(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = _saved_draft(root)
            replacements = {
                "DEFAULT_PROFILE_EXTRACTION_DIRECTORY": root / "extractions",
                "DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY": root / "drafts",
                "DEFAULT_PROFILE_ANALYSIS_REVIEW_DIRECTORY": root / "reviews",
                "DEFAULT_SLACK_PROFILE_REVIEW_SESSION_DIRECTORY": root / "sessions",
            }
            with patch.multiple(run_slack_socket, **replacements):
                shown = run_slack_socket._run_slack_action(
                    PROFILE_REVIEW_ACTION,
                    _request(CREATED_AT),
                )
                active = select_active_slack_profile_review_session(
                    team_id="T01234567",
                    channel_id="C01234567",
                    user_id="U76543210",
                    thread_ts="1789372800.000100",
                    session_directory=root / "sessions",
                    review_directory=root / "reviews",
                )
                approved = run_slack_socket._run_slack_action(
                    PROFILE_REVIEW_APPROVE_ACTION,
                    _request(CREATED_AT + timedelta(minutes=1)),
                )
                active_after = select_active_slack_profile_review_session(
                    team_id="T01234567",
                    channel_id="C01234567",
                    user_id="U76543210",
                    thread_ts="1789372800.000100",
                    session_directory=root / "sessions",
                    review_directory=root / "reviews",
                )
                completed = run_slack_socket._run_slack_action(
                    PROFILE_REVIEW_ACTION,
                    _request(CREATED_AT + timedelta(minutes=2)),
                )

            review_paths = list((root / "reviews").glob("*.json"))
            review = json.loads(review_paths[0].read_text(encoding="utf-8"))

        self.assertIn("QA Engineer", shown["public_message"])
        self.assertIn("맞아", shown["public_message"])
        self.assertIsNotNone(active)
        self.assertIn("승인", approved["public_message"])
        self.assertIsNone(active_after)
        self.assertIn("모든 항목을 이미 검토", completed["public_message"])
        self.assertEqual(1, len(review_paths))
        self.assertEqual("approve", review["profile_analysis_review"]["decision"])
        self.assertEqual(
            draft["profile_analysis_draft"]["draft_id"],
            review["source"]["draft_id"],
        )
        self.assertFalse(review["metadata"]["profile_updated"])

    def test_session_cannot_be_used_from_another_user_or_thread(self) -> None:
        session = build_slack_profile_review_session(
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372800.000100",
            draft_id="profile-analysis-draft-0123456789abcdef01234567",
            extraction_id="profile-text-extraction-0123456789abcdef01234567",
            item_type="career_evidence",
            item_position=1,
            created_at=CREATED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            save_slack_profile_review_session(session, root / "sessions")
            wrong_user = select_active_slack_profile_review_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U11111111",
                thread_ts="1789372800.000100",
                session_directory=root / "sessions",
                review_directory=root / "reviews",
            )
            wrong_thread = select_active_slack_profile_review_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372800.000200",
                session_directory=root / "sessions",
                review_directory=root / "reviews",
            )

        self.assertIsNone(wrong_user)
        self.assertIsNone(wrong_thread)


if __name__ == "__main__":
    unittest.main()
