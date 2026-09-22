from __future__ import annotations

from datetime import timedelta
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
    PROFILE_FINAL_APPROVE_ACTION,
    PROFILE_UPDATE_CAREER_ACTION,
    build_slack_profile_final_session,
    build_slack_profile_mapping_session,
    save_slack_profile_final_session,
    save_slack_profile_mapping_session,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_final_proposal,
    save_profile_analysis_final_proposal,
    save_profile_analysis_update_proposal,
    select_latest_profile_analysis_mapping_reviews,
)
from scripts import run_slack_socket  # noqa: E402
from tests.test_profile_analysis_mapping_review import _proposal  # noqa: E402
from tests.test_profile_analysis_final_proposal import _mapping_reviews  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


def _request(thread_ts: str = "1789372700.000900") -> dict:
    return {
        "slack_command_request": {
            "received_at": (CREATED_AT + timedelta(minutes=10)).isoformat(),
        },
        "source": {
            "team_id": "T01234567",
            "channel_id": "C01234567",
            "user_id": "U76543210",
            "thread_ts": thread_ts,
        },
        "command_arguments": {"selected_value": "career-001"},
    }


class SlackProfileMappingFlowTest(unittest.TestCase):
    def test_final_approval_creates_new_private_profile_version(self) -> None:
        profile, proposal = _proposal()
        final = build_profile_analysis_final_proposal(
            profile,
            proposal,
            _mapping_reviews(profile, proposal),
            created_at=CREATED_AT,
        )
        final_id = final["profile_analysis_final_proposal"]["final_proposal_id"]
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            profile_path = root_path / "profile.json"
            profile_path.write_text(json.dumps(profile, ensure_ascii=False), encoding="utf-8")
            final_directory = root_path / "final"
            session_directory = root_path / "sessions"
            review_directory = root_path / "reviews"
            application_directory = root_path / "applications"
            save_profile_analysis_final_proposal(final, final_directory)
            save_slack_profile_final_session(
                build_slack_profile_final_session(
                    team_id="T01234567",
                    channel_id="C01234567",
                    user_id="U76543210",
                    thread_ts="1789372700.000900",
                    final_proposal_id=final_id,
                    created_at=CREATED_AT,
                ),
                session_directory,
            )
            with (
                patch.object(run_slack_socket, "DEFAULT_PROFILE", profile_path),
                patch.object(run_slack_socket, "DEFAULT_PROFILE_ANALYSIS_FINAL_PROPOSAL_DIRECTORY", final_directory),
                patch.object(run_slack_socket, "DEFAULT_PROFILE_ANALYSIS_FINAL_REVIEW_DIRECTORY", review_directory),
                patch.object(run_slack_socket, "DEFAULT_SLACK_PROFILE_FINAL_SESSION_DIRECTORY", session_directory),
                patch.object(run_slack_socket, "DEFAULT_PROFILE_ANALYSIS_APPLICATION_DIRECTORY", application_directory),
            ):
                result = run_slack_socket._run_profile_final_decision(
                    PROFILE_FINAL_APPROVE_ACTION,
                    _request(),
                )
            saved_profiles = list(application_directory.glob("*/profile.json"))
            base_after = json.loads(profile_path.read_text(encoding="utf-8"))

        self.assertEqual("applied_to_new_version", result["status"])
        self.assertEqual(1, len(saved_profiles))
        self.assertEqual(profile, base_after)

    def test_final_review_requires_all_mappings_then_shows_summary(self) -> None:
        profile, proposal = _proposal()
        reviews = _mapping_reviews(profile, proposal)
        incomplete = dict(reviews)
        incomplete.pop("analysis-change-002")
        with tempfile.TemporaryDirectory() as root:
            final_directory = Path(root) / "final"
            with (
                patch.object(
                    run_slack_socket,
                    "_build_latest_profile_update_context",
                    return_value={
                        "profile": profile,
                        "proposal": proposal,
                        "mapping_reviews": incomplete,
                    },
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_ANALYSIS_FINAL_PROPOSAL_DIRECTORY",
                    final_directory,
                ),
            ):
                waiting = run_slack_socket._build_latest_profile_final_result(CREATED_AT)
            with (
                patch.object(
                    run_slack_socket,
                    "_build_latest_profile_update_context",
                    return_value={
                        "profile": profile,
                        "proposal": proposal,
                        "mapping_reviews": reviews,
                    },
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_ANALYSIS_FINAL_PROPOSAL_DIRECTORY",
                    final_directory,
                ),
            ):
                completed = run_slack_socket._build_latest_profile_final_result(CREATED_AT)

        self.assertIn("아직 선택하지 않은", waiting["public_message"])
        self.assertIsNone(waiting["final_target"])
        self.assertIn("프로필 최종 변경안", completed["public_message"])
        self.assertIsNotNone(completed["final_target"])

    def test_same_thread_selection_is_saved_without_updating_profile(self) -> None:
        profile, proposal = _proposal()
        proposal_id = proposal["profile_analysis_update_proposal"]["proposal_id"]
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            proposal_directory = root_path / "proposals"
            review_directory = root_path / "reviews"
            session_directory = root_path / "sessions"
            profile_path = root_path / "profile.json"
            profile_path.write_text(
                json.dumps(profile, ensure_ascii=False),
                encoding="utf-8",
            )
            save_profile_analysis_update_proposal(proposal, proposal_directory)
            session = build_slack_profile_mapping_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                proposal_id=proposal_id,
                change_id="analysis-change-001",
                mapping_status="needs_career_selection",
                allowed_values=["career-001"],
                created_at=CREATED_AT,
            )
            save_slack_profile_mapping_session(session, session_directory)
            with (
                patch.object(run_slack_socket, "DEFAULT_PROFILE", profile_path),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_ANALYSIS_UPDATE_PROPOSAL_DIRECTORY",
                    proposal_directory,
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_ANALYSIS_MAPPING_REVIEW_DIRECTORY",
                    review_directory,
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_SLACK_PROFILE_MAPPING_SESSION_DIRECTORY",
                    session_directory,
                ),
            ):
                result = run_slack_socket._run_profile_mapping_decision(
                    PROFILE_UPDATE_CAREER_ACTION,
                    _request(),
                )
            reviews = select_latest_profile_analysis_mapping_reviews(
                proposal_id,
                review_directory,
            )

        self.assertEqual("completed", result["status"])
        self.assertIn("아직 개인 프로필에는 적용하지 않았습니다", result["public_message"])
        self.assertEqual("career-001", reviews["analysis-change-001"]["profile_analysis_mapping_review"]["selected_value"])

    def test_different_thread_cannot_use_mapping_session(self) -> None:
        _, proposal = _proposal()
        proposal_id = proposal["profile_analysis_update_proposal"]["proposal_id"]
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            session_directory = root_path / "sessions"
            review_directory = root_path / "reviews"
            save_slack_profile_mapping_session(
                build_slack_profile_mapping_session(
                    team_id="T01234567",
                    channel_id="C01234567",
                    user_id="U76543210",
                    thread_ts="1789372700.000900",
                    proposal_id=proposal_id,
                    change_id="analysis-change-001",
                    mapping_status="needs_career_selection",
                    allowed_values=["career-001"],
                    created_at=CREATED_AT,
                ),
                session_directory,
            )
            with (
                patch.object(
                    run_slack_socket,
                    "DEFAULT_PROFILE_ANALYSIS_MAPPING_REVIEW_DIRECTORY",
                    review_directory,
                ),
                patch.object(
                    run_slack_socket,
                    "DEFAULT_SLACK_PROFILE_MAPPING_SESSION_DIRECTORY",
                    session_directory,
                ),
            ):
                result = run_slack_socket._run_profile_mapping_decision(
                    PROFILE_UPDATE_CAREER_ACTION,
                    _request("1789372700.999999"),
                )

        self.assertEqual("no_active_mapping_session", result["status"])


if __name__ == "__main__":
    unittest.main()
