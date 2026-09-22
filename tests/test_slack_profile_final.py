from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import build_slack_profile_final_proposal_result  # noqa: E402
from career_agent.profile_input import build_profile_analysis_final_proposal  # noqa: E402
from tests.test_profile_analysis_final_proposal import _mapping_reviews  # noqa: E402
from tests.test_profile_analysis_mapping_review import _proposal  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


class SlackProfileFinalTest(unittest.TestCase):
    def test_shows_complete_final_summary_without_internal_ids(self) -> None:
        profile, proposal = _proposal()
        final = build_profile_analysis_final_proposal(
            profile,
            proposal,
            _mapping_reviews(profile, proposal),
            created_at=CREATED_AT + timedelta(minutes=20),
        )

        result = build_slack_profile_final_proposal_result(profile, final)
        message = result["public_message"]

        self.assertIn("프로필 최종 변경안", message)
        self.assertIn("전체 변경: 4개", message)
        self.assertIn("`career-001`", message)
        self.assertIn("새 기술 Playwright, 숙련도 project", message)
        self.assertIn("`skill-playwright`", message)
        self.assertNotIn("profile-analysis-final-proposal-", message)
        self.assertNotIn("profile-analysis-review-", message)
        self.assertIn("final_proposal_id", result["final_target"])


if __name__ == "__main__":
    unittest.main()
