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
    build_profile_analysis_final_proposal,
    build_profile_analysis_mapping_review,
    load_profile_analysis_final_proposal,
    save_profile_analysis_final_proposal,
)
from tests.test_profile_analysis_mapping_review import _proposal  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


def _mapping_reviews(profile: dict, proposal: dict) -> dict[str, dict]:
    values = (
        ("analysis-change-001", "career-001"),
        ("analysis-change-002", "career-001"),
        ("analysis-change-004", "project"),
    )
    return {
        change_id: build_profile_analysis_mapping_review(
            profile,
            proposal,
            change_id=change_id,
            selected_value=selected_value,
            reviewed_at=CREATED_AT + timedelta(minutes=10 + position),
        )
        for position, (change_id, selected_value) in enumerate(values)
    }


class ProfileAnalysisFinalProposalTest(unittest.TestCase):
    def test_resolves_every_change_without_mutating_profile(self) -> None:
        profile, proposal = _proposal()
        original = deepcopy(profile)

        final = build_profile_analysis_final_proposal(
            profile,
            proposal,
            _mapping_reviews(profile, proposal),
            created_at=CREATED_AT + timedelta(minutes=20),
        )

        self.assertEqual(original, profile)
        self.assertEqual("ready_for_final_review", final["profile_analysis_final_proposal"]["status"])
        self.assertEqual(4, final["summary"]["change_count"])
        self.assertEqual(1, final["summary"]["career_evidence_count"])
        self.assertEqual(1, final["summary"]["achievement_evidence_count"])
        self.assertEqual(1, final["summary"]["existing_skill_evidence_count"])
        self.assertEqual(1, final["summary"]["new_skill_count"])
        self.assertEqual("career-001", final["resolved_changes"][0]["target"]["record_id"])
        self.assertEqual("skill-python", final["resolved_changes"][2]["target"]["record_id"])
        self.assertIsNone(final["resolved_changes"][2]["proposed_value"]["proposed_level"])
        self.assertEqual("skill-playwright", final["resolved_changes"][3]["target"]["record_id"])
        self.assertEqual("project", final["resolved_changes"][3]["proposed_value"]["proposed_level"])
        self.assertFalse(final["metadata"]["profile_updated"])

    def test_requires_all_mapping_choices_and_current_profile(self) -> None:
        profile, proposal = _proposal()
        reviews = _mapping_reviews(profile, proposal)
        reviews.pop("analysis-change-002")
        with self.assertRaisesRegex(ProfileDocumentError, "모든 경력 매핑"):
            build_profile_analysis_final_proposal(
                profile,
                proposal,
                reviews,
                created_at=CREATED_AT,
            )
        changed = deepcopy(profile)
        changed["profile"]["basic"]["career_status"] = "employed"
        with self.assertRaisesRegex(ProfileDocumentError, "기준 프로필"):
            build_profile_analysis_final_proposal(
                changed,
                proposal,
                _mapping_reviews(profile, proposal),
                created_at=CREATED_AT,
            )

    def test_saves_reuses_and_rejects_tampered_final_proposal(self) -> None:
        profile, proposal = _proposal()
        final = build_profile_analysis_final_proposal(
            profile,
            proposal,
            _mapping_reviews(profile, proposal),
            created_at=CREATED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            path, created = save_profile_analysis_final_proposal(final, directory)
            loaded = load_profile_analysis_final_proposal(path.stem, directory)
            _, reused = save_profile_analysis_final_proposal(final, directory)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["resolved_changes"][0]["proposed_value"]["role_or_context"] = "변조"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ProfileDocumentError, "내용 지문"):
                load_profile_analysis_final_proposal(path.stem, directory)

        self.assertTrue(created)
        self.assertFalse(reused)
        self.assertEqual(final, loaded)


if __name__ == "__main__":
    unittest.main()
