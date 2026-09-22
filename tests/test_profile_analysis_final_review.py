from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_final_review,
    load_profile_analysis_final_review,
    save_profile_analysis_final_review,
    select_latest_profile_analysis_final_review,
)
from tests.test_profile_analysis_application import _final  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


class ProfileAnalysisFinalReviewTest(unittest.TestCase):
    def test_saves_content_free_explicit_decision_and_selects_latest(self) -> None:
        _, final = _final()
        first = build_profile_analysis_final_review(
            final,
            decision="reject",
            reviewed_at=CREATED_AT + timedelta(minutes=30),
        )
        latest = build_profile_analysis_final_review(
            final,
            decision="approve",
            reviewed_at=CREATED_AT + timedelta(minutes=31),
        )
        with tempfile.TemporaryDirectory() as directory:
            first_path = save_profile_analysis_final_review(first, directory)
            save_profile_analysis_final_review(latest, directory)
            loaded = load_profile_analysis_final_review(first_path.stem, directory)
            selected = select_latest_profile_analysis_final_review(
                final["profile_analysis_final_proposal"]["final_proposal_id"],
                directory,
            )

        self.assertEqual(first, loaded)
        self.assertEqual("approve", selected["profile_analysis_final_review"]["decision"])
        self.assertFalse(latest["metadata"]["contains_proposal_content"])
        self.assertFalse(latest["metadata"]["profile_updated"])


if __name__ == "__main__":
    unittest.main()
