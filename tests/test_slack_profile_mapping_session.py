from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    build_slack_profile_mapping_session,
    load_slack_profile_mapping_session,
    save_slack_profile_mapping_session,
    select_active_slack_profile_mapping_session,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_mapping_review,
    save_profile_analysis_mapping_review,
)
from tests.test_profile_analysis_mapping_review import _proposal  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


def _session(proposal_id: str, **changes) -> dict:
    values = {
        "team_id": "T01234567",
        "channel_id": "C01234567",
        "user_id": "U76543210",
        "thread_ts": "1789372700.000900",
        "proposal_id": proposal_id,
        "change_id": "analysis-change-001",
        "mapping_status": "needs_career_selection",
        "allowed_values": ["career-001"],
        "created_at": CREATED_AT,
    }
    values.update(changes)
    return build_slack_profile_mapping_session(**values)


class SlackProfileMappingSessionTest(unittest.TestCase):
    def test_saves_and_loads_session_without_analysis_text(self) -> None:
        _, proposal = _proposal()
        session = _session(proposal["profile_analysis_update_proposal"]["proposal_id"])
        with tempfile.TemporaryDirectory() as directory:
            path = save_slack_profile_mapping_session(session, directory)
            loaded = load_slack_profile_mapping_session(path.stem, directory)

        self.assertEqual(session, loaded)
        self.assertFalse(session["metadata"]["contains_message_text"])
        self.assertFalse(session["metadata"]["contains_analysis_text"])
        self.assertEqual(["career-001"], session["target"]["allowed_values"])

    def test_selects_only_same_user_thread_and_unanswered_target(self) -> None:
        profile, proposal = _proposal()
        proposal_id = proposal["profile_analysis_update_proposal"]["proposal_id"]
        with tempfile.TemporaryDirectory() as root:
            session_directory = Path(root) / "sessions"
            review_directory = Path(root) / "reviews"
            expected = _session(proposal_id)
            save_slack_profile_mapping_session(expected, session_directory)
            save_slack_profile_mapping_session(
                _session(
                    proposal_id,
                    user_id="U99999999",
                    created_at=CREATED_AT + timedelta(seconds=1),
                ),
                session_directory,
            )
            active = select_active_slack_profile_mapping_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                review_directory=review_directory,
            )
            decision = build_profile_analysis_mapping_review(
                profile,
                proposal,
                change_id="analysis-change-001",
                selected_value="career-001",
                reviewed_at=CREATED_AT + timedelta(minutes=1),
            )
            save_profile_analysis_mapping_review(decision, review_directory)
            completed = select_active_slack_profile_mapping_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                review_directory=review_directory,
            )

        self.assertEqual(expected, active)
        self.assertIsNone(completed)


if __name__ == "__main__":
    unittest.main()
