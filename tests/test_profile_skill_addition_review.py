from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
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
    load_profile_skill_addition_proposal,
    save_profile_skill_addition_proposal,
    save_profile_skill_addition_review,
)


REVIEWED_AT = datetime(2026, 9, 14, 21, tzinfo=timezone.utc)


def _addition_proposal() -> dict:
    return {
        "profile_skill_addition": {
            "proposal_id": "profile-skill-addition-0123456789abcdef01234567",
            "created_at": "2026-09-14T20:00:00.000000+00:00",
            "status": "needs_final_review",
            "base_profile_id": "private-user-001",
            "base_profile_content_sha256": "a" * 64,
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
                    "extraction_id": (
                        "profile-text-extraction-0123456789abcdef01234567"
                    ),
                    "document_id": (
                        "profile-document-resume-0123456789abcdef0123"
                    ),
                    "line_start": 3,
                    "line_end": 3,
                    "review_id": (
                        "profile-candidate-review-0123456789abcdef01234567"
                    ),
                    "confirmation_id": (
                        "profile-skill-confirmation-0123456789abcdef01234567"
                    ),
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


class ProfileSkillAdditionReviewTest(unittest.TestCase):
    def test_records_approval_without_copying_proposed_skill(self) -> None:
        review = build_profile_skill_addition_review(
            _addition_proposal(),
            addition_item_id="skill-addition-item-001",
            decision="approve",
            reviewed_at=REVIEWED_AT,
            notes="합성 추가안 승인",
        )
        serialized = json.dumps(review, ensure_ascii=False)

        root = review["profile_skill_addition_review"]
        self.assertEqual("approve", root["decision"])
        self.assertEqual("explicit_user_input", root["review_source"])
        self.assertEqual(
            "skill-addition-item-001",
            review["source"]["addition_item_id"],
        )
        self.assertFalse(review["metadata"]["contains_proposed_skill"])
        self.assertFalse(review["metadata"]["profile_updated"])
        self.assertNotIn("FastAPI", serialized)
        self.assertNotIn("합성 프로젝트에서 API 서버 구현", serialized)

    def test_records_rejection(self) -> None:
        review = build_profile_skill_addition_review(
            _addition_proposal(),
            addition_item_id="skill-addition-item-001",
            decision="reject",
            reviewed_at=REVIEWED_AT,
        )

        self.assertEqual(
            "reject",
            review["profile_skill_addition_review"]["decision"],
        )

    def test_rejects_invalid_decision(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "decision 허용값"):
            build_profile_skill_addition_review(
                _addition_proposal(),
                addition_item_id="skill-addition-item-001",
                decision="hold",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_unknown_or_duplicate_addition_item(self) -> None:
        proposal = _addition_proposal()
        with self.assertRaisesRegex(ProfileDocumentError, "찾을 수 없음"):
            build_profile_skill_addition_review(
                proposal,
                addition_item_id="skill-addition-item-999",
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

        proposal["skill_additions"].append(deepcopy(proposal["skill_additions"][0]))
        proposal["summary"]["confirmed_skill_count"] = 2
        with self.assertRaisesRegex(ProfileDocumentError, "중복 기술 추가"):
            build_profile_skill_addition_review(
                proposal,
                addition_item_id="skill-addition-item-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_tampered_skill_or_source(self) -> None:
        changed_skill = _addition_proposal()
        changed_skill["skill_additions"][0]["proposed_skill"]["level"] = "expert"
        with self.assertRaisesRegex(ProfileDocumentError, "level"):
            build_profile_skill_addition_review(
                changed_skill,
                addition_item_id="skill-addition-item-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

        changed_source = _addition_proposal()
        changed_source["skill_additions"][0]["source"]["line_start"] = 0
        with self.assertRaisesRegex(ProfileDocumentError, "line_start"):
            build_profile_skill_addition_review(
                changed_source,
                addition_item_id="skill-addition-item-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_proposal_without_reviewable_skill(self) -> None:
        proposal = _addition_proposal()
        proposal["profile_skill_addition"]["status"] = "no_confirmed_skills"

        with self.assertRaisesRegex(ProfileDocumentError, "최종 검토할 기술"):
            build_profile_skill_addition_review(
                proposal,
                addition_item_id="skill-addition-item-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_naive_timestamp_and_long_notes(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_skill_addition_review(
                _addition_proposal(),
                addition_item_id="skill-addition-item-001",
                decision="approve",
                reviewed_at=datetime(2026, 9, 14, 21),
            )
        with self.assertRaisesRegex(ProfileDocumentError, "1000자"):
            build_profile_skill_addition_review(
                _addition_proposal(),
                addition_item_id="skill-addition-item-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
                notes="a" * 1001,
            )

    def test_saves_immutable_review_without_overwrite(self) -> None:
        review = build_profile_skill_addition_review(
            _addition_proposal(),
            addition_item_id="skill-addition-item-001",
            decision="approve",
            reviewed_at=REVIEWED_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_profile_skill_addition_review(review, directory)
            actual = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ProfileDocumentError, "이미 존재"):
                save_profile_skill_addition_review(review, directory)

        self.assertEqual(
            "approve",
            actual["profile_skill_addition_review"]["decision"],
        )

    def test_load_addition_rejects_path_traversal_and_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProfileDocumentError, "proposal_id 형식"):
                load_profile_skill_addition_proposal("../outside", directory)

            proposal = _addition_proposal()
            path, _ = save_profile_skill_addition_proposal(proposal, directory)
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["profile_skill_addition"]["proposal_id"] = (
                "profile-skill-addition-000000000000000000000000"
            )
            path.write_text(json.dumps(stored), encoding="utf-8")
            requested_id = proposal["profile_skill_addition"]["proposal_id"]

            with self.assertRaisesRegex(ProfileDocumentError, "요청과 일치"):
                load_profile_skill_addition_proposal(requested_id, directory)


if __name__ == "__main__":
    unittest.main()
