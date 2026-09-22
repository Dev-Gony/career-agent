from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_application,
    build_profile_analysis_final_proposal,
    build_profile_analysis_final_review,
    save_profile_analysis_application,
)
from tests.test_profile_analysis_final_proposal import _mapping_reviews  # noqa: E402
from tests.test_profile_analysis_mapping_review import _proposal  # noqa: E402
from tests.test_profile_analysis_update_proposal import CREATED_AT  # noqa: E402


def _final() -> tuple[dict, dict]:
    profile, proposal = _proposal()
    final = build_profile_analysis_final_proposal(
        profile,
        proposal,
        _mapping_reviews(profile, proposal),
        created_at=CREATED_AT + timedelta(minutes=20),
    )
    return profile, final


class ProfileAnalysisApplicationTest(unittest.TestCase):
    def test_approved_final_proposal_creates_separate_profile_version(self) -> None:
        profile, final = _final()
        original = deepcopy(profile)
        review = build_profile_analysis_final_review(
            final,
            decision="approve",
            reviewed_at=CREATED_AT + timedelta(minutes=30),
        )

        application, updated = build_profile_analysis_application(
            profile,
            final,
            review,
            applied_at=CREATED_AT + timedelta(minutes=31),
        )

        self.assertEqual(original, profile)
        self.assertIsNotNone(updated)
        assert updated is not None
        career = updated["profile"]["career_history"][0]
        self.assertIn("API 테스트를 수행했습니다.", career["responsibilities"])
        self.assertEqual(2, len(career["achievements"]))
        python = next(item for item in updated["profile"]["skills"] if item["skill_id"] == "skill-python")
        self.assertIn("Python으로 테스트 데이터 검증 도구를 개발했습니다.", python["evidence"])
        playwright = next(item for item in updated["profile"]["skills"] if item["skill_id"] == "skill-playwright")
        self.assertEqual("project", playwright["level"])
        self.assertEqual("applied_to_new_version", application["profile_analysis_application"]["status"])
        self.assertEqual(4, application["summary"]["applied_count"])

    def test_rejection_creates_audit_without_profile_version(self) -> None:
        profile, final = _final()
        review = build_profile_analysis_final_review(
            final,
            decision="reject",
            reviewed_at=CREATED_AT + timedelta(minutes=30),
        )

        application, updated = build_profile_analysis_application(
            profile,
            final,
            review,
            applied_at=CREATED_AT + timedelta(minutes=31),
        )

        self.assertIsNone(updated)
        self.assertEqual("rejected", application["profile_analysis_application"]["status"])
        self.assertEqual(0, application["summary"]["applied_count"])

    def test_rejects_changed_base_profile_and_saves_immutable_result(self) -> None:
        profile, final = _final()
        review = build_profile_analysis_final_review(
            final,
            decision="approve",
            reviewed_at=CREATED_AT + timedelta(minutes=30),
        )
        changed = deepcopy(profile)
        changed["profile"]["career_goals"]["primary_goal"] = "변경됨"
        with self.assertRaisesRegex(ProfileDocumentError, "기준 프로필"):
            build_profile_analysis_application(
                changed,
                final,
                review,
                applied_at=CREATED_AT,
            )

        application, updated = build_profile_analysis_application(
            profile,
            final,
            review,
            applied_at=CREATED_AT + timedelta(minutes=31),
        )
        with tempfile.TemporaryDirectory() as directory:
            path, created = save_profile_analysis_application(application, updated, directory)
            retry_path, reused = save_profile_analysis_application(application, updated, directory)

        self.assertTrue(created)
        self.assertFalse(reused)
        self.assertEqual(path, retry_path)


if __name__ == "__main__":
    unittest.main()
