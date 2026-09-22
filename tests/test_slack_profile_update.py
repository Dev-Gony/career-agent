from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    build_slack_profile_update_mapping_item_result,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_mapping_review,
    build_profile_analysis_update_proposal,
)
from tests.test_profile_analysis_update_proposal import (  # noqa: E402
    CREATED_AT,
    _draft,
    _profile,
    _review,
)


class SlackProfileUpdateTest(unittest.TestCase):
    def test_shows_first_pending_career_mapping_with_allowed_ids(self) -> None:
        profile = _profile()
        draft = _draft()
        reviews = [
            _review(draft, "career_evidence", 1, "approve", 1),
            _review(draft, "achievement_evidence", 1, "approve", 2),
            _review(draft, "technology_evidence", 1, "approve", 3),
            _review(draft, "technology_evidence", 2, "approve", 4),
            _review(draft, "unknowns", 1, "approve", 5),
        ]
        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            reviews,
            created_at=CREATED_AT,
        )

        result = build_slack_profile_update_mapping_item_result(profile, proposal)
        message = result["public_message"]

        self.assertIn("프로필 변경 매핑 1/4", message)
        self.assertIn("유형: 경력 근거", message)
        self.assertIn("QA Engineer", message)
        self.assertIn("`career-001`", message)
        self.assertIn("경력 &lt;경력ID&gt;", message)
        self.assertNotIn("profile-analysis-update-proposal-", message)
        self.assertNotIn("profile-analysis-review-", message)
        self.assertEqual(
            "needs_career_selection",
            result["mapping_target"]["mapping_status"],
        )
        self.assertEqual(
            ["career-001"],
            result["mapping_target"]["allowed_values"],
        )

    def test_requires_all_analysis_items_to_be_reviewed_first(self) -> None:
        profile = _profile()
        draft = _draft()
        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            [_review(draft, "career_evidence", 1, "approve", 1)],
            created_at=CREATED_AT,
        )

        result = build_slack_profile_update_mapping_item_result(profile, proposal)

        self.assertIn("아직 검토하지 않은", result["public_message"])
        self.assertIsNone(result["mapping_target"])

    def test_reports_mapping_complete_when_only_existing_skill_is_approved(self) -> None:
        profile = _profile()
        draft = _draft()
        reviews = [
            _review(draft, "career_evidence", 1, "reject", 1),
            _review(draft, "achievement_evidence", 1, "reject", 2),
            _review(draft, "technology_evidence", 1, "approve", 3),
            _review(draft, "technology_evidence", 2, "reject", 4),
            _review(draft, "unknowns", 1, "reject", 5),
        ]
        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            reviews,
            created_at=CREATED_AT + timedelta(minutes=10),
        )

        result = build_slack_profile_update_mapping_item_result(profile, proposal)

        self.assertIn("모든 프로필 변경 항목의 매핑", result["public_message"])
        self.assertIsNone(result["mapping_target"])

    def test_skips_saved_mapping_choice_and_shows_next_item(self) -> None:
        profile = _profile()
        draft = _draft()
        reviews = [
            _review(draft, "career_evidence", 1, "approve", 1),
            _review(draft, "achievement_evidence", 1, "approve", 2),
            _review(draft, "technology_evidence", 1, "reject", 3),
            _review(draft, "technology_evidence", 2, "reject", 4),
            _review(draft, "unknowns", 1, "reject", 5),
        ]
        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            reviews,
            created_at=CREATED_AT,
        )
        decision = build_profile_analysis_mapping_review(
            profile,
            proposal,
            change_id="analysis-change-001",
            selected_value="career-001",
            reviewed_at=CREATED_AT + timedelta(minutes=10),
        )

        result = build_slack_profile_update_mapping_item_result(
            profile,
            proposal,
            {"analysis-change-001": decision},
        )

        self.assertIn("프로필 변경 매핑 2/2", result["public_message"])
        self.assertIn("유형: 성과 근거", result["public_message"])
        self.assertEqual("analysis-change-002", result["mapping_target"]["change_id"])


if __name__ == "__main__":
    unittest.main()
