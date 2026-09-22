from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_mapping_review,
    build_profile_analysis_update_proposal,
    load_profile_analysis_mapping_review,
    save_profile_analysis_mapping_review,
    select_latest_profile_analysis_mapping_reviews,
)
from tests.test_profile_analysis_update_proposal import (  # noqa: E402
    CREATED_AT,
    _draft,
    _profile,
    _review,
)


def _proposal() -> tuple[dict, dict]:
    profile = _profile()
    draft = _draft()
    reviews = [
        _review(draft, "career_evidence", 1, "approve", 1),
        _review(draft, "achievement_evidence", 1, "approve", 2),
        _review(draft, "technology_evidence", 1, "approve", 3),
        _review(draft, "technology_evidence", 2, "approve", 4),
        _review(draft, "unknowns", 1, "reject", 5),
    ]
    return profile, build_profile_analysis_update_proposal(
        profile,
        draft,
        reviews,
        created_at=CREATED_AT,
    )


class ProfileAnalysisMappingReviewTest(unittest.TestCase):
    def test_builds_career_and_skill_choices_without_analysis_text(self) -> None:
        profile, proposal = _proposal()

        career = build_profile_analysis_mapping_review(
            profile,
            proposal,
            change_id="analysis-change-001",
            selected_value="career-001",
            reviewed_at=CREATED_AT + timedelta(minutes=10),
        )
        skill = build_profile_analysis_mapping_review(
            profile,
            proposal,
            change_id="analysis-change-004",
            selected_value="project",
            reviewed_at=CREATED_AT + timedelta(minutes=11),
        )

        self.assertEqual("career_selection", career["profile_analysis_mapping_review"]["decision_type"])
        self.assertEqual("skill_level_confirmation", skill["profile_analysis_mapping_review"]["decision_type"])
        self.assertEqual("career-001", career["profile_analysis_mapping_review"]["selected_value"])
        self.assertFalse(career["metadata"]["contains_analysis_text"])
        self.assertFalse(career["metadata"]["profile_updated"])
        serialized = json.dumps(career, ensure_ascii=False)
        self.assertNotIn("QA Engineer", serialized)
        self.assertNotIn("API 테스트", serialized)

    def test_rejects_wrong_choice_type_unknown_career_and_stale_profile(self) -> None:
        profile, proposal = _proposal()
        with self.assertRaisesRegex(ProfileDocumentError, "경력 ID"):
            build_profile_analysis_mapping_review(
                profile,
                proposal,
                change_id="analysis-change-001",
                selected_value="career-999",
                reviewed_at=CREATED_AT,
            )
        with self.assertRaisesRegex(ProfileDocumentError, "숙련도"):
            build_profile_analysis_mapping_review(
                profile,
                proposal,
                change_id="analysis-change-004",
                selected_value="expert",
                reviewed_at=CREATED_AT,
            )
        changed_profile = deepcopy(profile)
        changed_profile["profile"]["career_goals"]["primary_goal"] = "변경됨"
        with self.assertRaisesRegex(ProfileDocumentError, "기준 프로필"):
            build_profile_analysis_mapping_review(
                changed_profile,
                proposal,
                change_id="analysis-change-001",
                selected_value="career-001",
                reviewed_at=CREATED_AT,
            )

    def test_saves_loads_and_selects_latest_choice(self) -> None:
        profile, proposal = _proposal()
        first = build_profile_analysis_mapping_review(
            profile,
            proposal,
            change_id="analysis-change-004",
            selected_value="learning",
            reviewed_at=CREATED_AT + timedelta(minutes=10),
        )
        latest = build_profile_analysis_mapping_review(
            profile,
            proposal,
            change_id="analysis-change-004",
            selected_value="project",
            reviewed_at=CREATED_AT + timedelta(minutes=11),
        )
        with tempfile.TemporaryDirectory() as directory:
            first_path = save_profile_analysis_mapping_review(first, directory)
            save_profile_analysis_mapping_review(latest, directory)
            loaded = load_profile_analysis_mapping_review(first_path.stem, directory)
            selected = select_latest_profile_analysis_mapping_reviews(
                proposal["profile_analysis_update_proposal"]["proposal_id"],
                directory,
            )
            tampered = json.loads(first_path.read_text(encoding="utf-8"))
            tampered["profile_analysis_mapping_review"]["selected_value"] = "work"
            first_path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ProfileDocumentError, "내용 지문"):
                load_profile_analysis_mapping_review(first_path.stem, directory)

        self.assertEqual(first, loaded)
        self.assertEqual(
            "project",
            selected["analysis-change-004"]["profile_analysis_mapping_review"]["selected_value"],
        )


if __name__ == "__main__":
    unittest.main()
