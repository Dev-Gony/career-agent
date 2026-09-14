from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_skill_addition_review,
    build_profile_skill_application,
    profile_content_sha256,
    save_profile_skill_application,
)


APPLIED_AT = datetime(2026, 9, 14, 22, tzinfo=timezone.utc)


def _profile() -> dict:
    return {
        "profile": {
            "basic": {"profile_id": "private-user-001"},
            "skills": [
                {
                    "skill_id": "skill-python",
                    "name": "Python",
                    "level": "project",
                    "evidence": ["합성 프로젝트"],
                    "notes": None,
                }
            ],
        },
        "metadata": {
            "schema_version": "0.1",
            "data_type": "private",
            "last_updated": "2026-09-13",
        },
    }


def _addition_proposal(profile: dict | None = None) -> dict:
    base_profile = profile or _profile()
    return {
        "profile_skill_addition": {
            "proposal_id": "profile-skill-addition-0123456789abcdef01234567",
            "created_at": "2026-09-14T20:00:00.000000+00:00",
            "status": "needs_final_review",
            "base_profile_id": base_profile["profile"]["basic"]["profile_id"],
            "base_profile_content_sha256": profile_content_sha256(base_profile),
            "source_mapping_id": "profile-skill-mapping-0123456789abcdef01234567",
            "rules_version": "0.1",
        },
        "summary": {
            "new_skill_candidate_count": 1,
            "confirmed_skill_count": 1,
            "unconfirmed_skill_count": 0,
            "duplicate_existing_count": 0,
            "needs_separation_count": 0,
        },
        "skill_additions": [
            {
                "addition_item_id": "skill-addition-item-001",
                "proposed_skill": {
                    "skill_id": "skill-import-0123456789ab",
                    "name": "FastAPI",
                    "level": "project",
                    "evidence": ["합성 프로젝트에서 API 서버 구현"],
                    "notes": None,
                },
                "source": {
                    "mapping_item_id": "skill-mapping-item-001",
                    "proposal_item_id": "proposal-item-001",
                    "candidate_id": "candidate-001",
                    "extraction_id": "profile-text-extraction-0123456789abcdef01234567",
                    "document_id": "profile-document-resume-0123456789abcdef0123",
                    "line_start": 3,
                    "line_end": 3,
                    "review_id": "profile-candidate-review-0123456789abcdef01234567",
                    "confirmation_id": "profile-skill-confirmation-0123456789abcdef01234567",
                },
                "application_status": "needs_final_review",
            }
        ],
        "analysis_notes": {"facts": [], "unknowns": []},
        "metadata": {
            "schema_version": "0.1",
            "contains_personal_data": True,
            "contains_candidate_text": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def _review(proposal: dict, decision: str, reviewed_at: datetime) -> dict:
    return build_profile_skill_addition_review(
        proposal,
        addition_item_id="skill-addition-item-001",
        decision=decision,
        reviewed_at=reviewed_at,
    )


class ProfileSkillApplicationTest(unittest.TestCase):
    def test_latest_approval_creates_new_profile_without_mutating_original(self) -> None:
        profile = _profile()
        original = deepcopy(profile)
        proposal = _addition_proposal(profile)
        reviews = [
            _review(proposal, "reject", APPLIED_AT - timedelta(hours=2)),
            _review(proposal, "approve", APPLIED_AT - timedelta(hours=1)),
        ]

        application, updated = build_profile_skill_application(
            profile,
            proposal,
            reviews,
            applied_at=APPLIED_AT,
        )

        self.assertEqual(original, profile)
        self.assertIsNotNone(updated)
        assert updated is not None
        self.assertEqual(["Python", "FastAPI"], [item["name"] for item in updated["profile"]["skills"]])
        self.assertEqual("2026-09-14", updated["metadata"]["last_updated"])
        self.assertEqual("applied_to_new_version", application["profile_skill_application"]["status"])
        self.assertEqual(1, application["summary"]["applied_count"])
        serialized = json.dumps(application, ensure_ascii=False)
        self.assertNotIn("FastAPI", serialized)
        self.assertNotIn("합성 프로젝트에서 API 서버 구현", serialized)

    def test_latest_rejection_prevents_application(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        reviews = [
            _review(proposal, "approve", APPLIED_AT - timedelta(hours=2)),
            _review(proposal, "reject", APPLIED_AT - timedelta(hours=1)),
        ]

        application, updated = build_profile_skill_application(
            profile, proposal, reviews, applied_at=APPLIED_AT
        )

        self.assertIsNone(updated)
        self.assertEqual("no_approved_skills", application["profile_skill_application"]["status"])
        self.assertEqual(1, application["summary"]["rejected_count"])

    def test_unreviewed_and_empty_proposals_create_no_profile(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        application, updated = build_profile_skill_application(
            profile, proposal, [], applied_at=APPLIED_AT
        )
        self.assertIsNone(updated)
        self.assertEqual(1, application["summary"]["unreviewed_count"])

        proposal["skill_additions"] = []
        proposal["summary"]["confirmed_skill_count"] = 0
        proposal["profile_skill_addition"]["status"] = "no_confirmed_skills"
        proposal["metadata"]["contains_candidate_text"] = False
        application, updated = build_profile_skill_application(
            profile, proposal, [], applied_at=APPLIED_AT
        )
        self.assertIsNone(updated)
        self.assertEqual(0, application["summary"]["addition_count"])

    def test_ignores_valid_review_for_another_proposal(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        other = deepcopy(proposal)
        other["profile_skill_addition"]["proposal_id"] = (
            "profile-skill-addition-aaaaaaaaaaaaaaaaaaaaaaaa"
        )
        other_review = _review(other, "approve", APPLIED_AT - timedelta(hours=1))

        application, updated = build_profile_skill_application(
            profile, proposal, [other_review], applied_at=APPLIED_AT
        )

        self.assertIsNone(updated)
        self.assertEqual(0, application["summary"]["reviewed_count"])

    def test_rejects_stale_profile_and_duplicate_skill(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        review = _review(proposal, "approve", APPLIED_AT - timedelta(hours=1))
        stale_profile = deepcopy(profile)
        stale_profile["metadata"]["last_updated"] = "2026-09-14"
        with self.assertRaisesRegex(ProfileDocumentError, "프로필 내용이 변경"):
            build_profile_skill_application(
                stale_profile, proposal, [review], applied_at=APPLIED_AT
            )

        duplicate = deepcopy(proposal)
        duplicate["skill_additions"][0]["proposed_skill"]["name"] = " python "
        duplicate_review = _review(duplicate, "approve", APPLIED_AT - timedelta(minutes=30))
        with self.assertRaisesRegex(ProfileDocumentError, "중복되는 기술명"):
            build_profile_skill_application(
                profile, duplicate, [duplicate_review], applied_at=APPLIED_AT
            )

    def test_rejects_tampered_review_id_and_source(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        review = _review(proposal, "approve", APPLIED_AT - timedelta(hours=1))
        changed_id = deepcopy(review)
        changed_id["profile_skill_addition_review"]["review_id"] = (
            "profile-skill-addition-review-000000000000000000000000"
        )
        with self.assertRaisesRegex(ProfileDocumentError, "검토 ID"):
            build_profile_skill_application(
                profile, proposal, [changed_id], applied_at=APPLIED_AT
            )

        changed_source = deepcopy(review)
        changed_source["source"]["confirmation_id"] = "changed-confirmation"
        with self.assertRaisesRegex(ProfileDocumentError, "근거가 원본"):
            build_profile_skill_application(
                profile, proposal, [changed_source], applied_at=APPLIED_AT
            )

    def test_save_reuses_identical_result_and_detects_tampering(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        review = _review(proposal, "approve", APPLIED_AT - timedelta(hours=1))
        application, updated = build_profile_skill_application(
            profile, proposal, [review], applied_at=APPLIED_AT
        )
        later_application, later_updated = build_profile_skill_application(
            profile, proposal, [review], applied_at=APPLIED_AT + timedelta(hours=1)
        )

        with tempfile.TemporaryDirectory() as directory:
            path, created = save_profile_skill_application(application, updated, directory)
            reused_path, reused = save_profile_skill_application(
                later_application, later_updated, directory
            )
            self.assertTrue(created)
            self.assertFalse(reused)
            self.assertEqual(path, reused_path)
            self.assertTrue((path.parent / "profile.json").exists())

            stored = json.loads((path.parent / "profile.json").read_text(encoding="utf-8"))
            stored["metadata"]["last_updated"] = "2099-01-01"
            (path.parent / "profile.json").write_text(
                json.dumps(stored), encoding="utf-8"
            )
            with self.assertRaisesRegex(ProfileDocumentError, "기존 새 프로필"):
                save_profile_skill_application(application, updated, directory)

    def test_noop_save_has_only_application_record(self) -> None:
        profile = _profile()
        proposal = _addition_proposal(profile)
        application, updated = build_profile_skill_application(
            profile, proposal, [], applied_at=APPLIED_AT
        )
        with tempfile.TemporaryDirectory() as directory:
            path, created = save_profile_skill_application(
                application, updated, directory
            )
            self.assertTrue(created)
            self.assertTrue(path.exists())
            self.assertFalse((path.parent / "profile.json").exists())

    def test_rejects_naive_applied_timestamp(self) -> None:
        profile = _profile()
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_skill_application(
                profile,
                _addition_proposal(profile),
                [],
                applied_at=datetime(2026, 9, 14, 22),
            )


if __name__ == "__main__":
    unittest.main()
