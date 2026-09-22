from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    build_slack_profile_final_session,
    load_slack_profile_final_session,
    save_slack_profile_final_session,
    select_active_slack_profile_final_session,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_final_review,
    save_profile_analysis_final_review,
)
from tests.test_profile_analysis_application import _final  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


class SlackProfileFinalSessionTest(unittest.TestCase):
    def test_session_is_thread_bound_and_closes_after_decision(self) -> None:
        _, final = _final()
        final_id = final["profile_analysis_final_proposal"]["final_proposal_id"]
        session = build_slack_profile_final_session(
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372700.000900",
            final_proposal_id=final_id,
            created_at=CREATED_AT,
        )
        with tempfile.TemporaryDirectory() as root:
            session_directory = Path(root) / "sessions"
            review_directory = Path(root) / "reviews"
            path = save_slack_profile_final_session(session, session_directory)
            loaded = load_slack_profile_final_session(path.stem, session_directory)
            active = select_active_slack_profile_final_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                review_directory=review_directory,
            )
            wrong_thread = select_active_slack_profile_final_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.999999",
                session_directory=session_directory,
                review_directory=review_directory,
            )
            save_profile_analysis_final_review(
                build_profile_analysis_final_review(
                    final,
                    decision="approve",
                    reviewed_at=CREATED_AT + timedelta(minutes=1),
                ),
                review_directory,
            )
            completed = select_active_slack_profile_final_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                review_directory=review_directory,
            )

        self.assertEqual(session, loaded)
        self.assertEqual(session, active)
        self.assertIsNone(wrong_thread)
        self.assertIsNone(completed)
        self.assertFalse(session["metadata"]["contains_proposal_content"])


if __name__ == "__main__":
    unittest.main()
