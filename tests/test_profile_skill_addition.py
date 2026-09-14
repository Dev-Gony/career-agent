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
    build_profile_skill_addition_proposal,
    build_profile_skill_confirmation,
    profile_content_sha256,
    save_profile_skill_addition_proposal,
)


CONFIRMED_AT = datetime(2026, 9, 14, 19, tzinfo=timezone.utc)
ADDITION_AT = datetime(2026, 9, 14, 20, tzinfo=timezone.utc)


def _profile() -> dict:
    return {
        "profile": {
            "basic": {
                "profile_id": "private-user-001",
                "locale": "ko-KR",
            },
            "skills": [
                {
                    "skill_id": "skill-python",
                    "name": "Python",
                    "level": "project",
                    "evidence": ["합성 프로젝트"],
                }
            ],
        },
        "metadata": {"schema_version": "0.1"},
    }


def _source(candidate_number: int, line: int) -> dict:
    return {
        "proposal_item_id": f"proposal-item-{candidate_number:03d}",
        "candidate_id": f"candidate-{candidate_number:03d}",
        "extraction_id": "profile-text-extraction-0123456789abcdef01234567",
        "document_id": "profile-document-resume-0123456789abcdef0123",
        "line_start": line,
        "line_end": line,
        "review_id": (
            f"profile-candidate-review-{candidate_number:024x}"
        ),
    }


def _mapping_proposal(profile: dict | None = None) -> dict:
    profile = profile or _profile()
    return {
        "profile_skill_mapping": {
            "mapping_id": "profile-skill-mapping-0123456789abcdef01234567",
            "created_at": "2026-09-14T18:00:00.000000+00:00",
            "status": "needs_confirmation",
            "base_profile_id": profile["profile"]["basic"]["profile_id"],
            "base_profile_content_sha256": profile_content_sha256(profile),
            "source_update_proposal_id": (
                "profile-update-proposal-0123456789abcdef01234567"
            ),
            "rules_version": "0.1",
        },
        "summary": {
            "approved_candidate_count": 3,
            "skill_candidate_count": 3,
            "duplicate_existing_count": 1,
            "needs_details_count": 1,
            "needs_separation_count": 1,
            "skipped_non_skill_count": 0,
        },
        "skill_mappings": [
            {
                "mapping_item_id": "skill-mapping-item-001",
                "source": _source(1, 2),
                "candidate_text": "FastAPI",
                "candidate_name": "FastAPI",
                "mapping_status": "needs_details",
                "existing_skill": None,
                "missing_fields": ["level", "evidence"],
                "profile_change_ready": False,
            },
            {
                "mapping_item_id": "skill-mapping-item-002",
                "source": _source(2, 3),
                "candidate_text": "python",
                "candidate_name": "python",
                "mapping_status": "duplicate_existing",
                "existing_skill": {"skill_id": "skill-python", "name": "Python"},
                "missing_fields": [],
                "profile_change_ready": False,
            },
            {
                "mapping_item_id": "skill-mapping-item-003",
                "source": _source(3, 4),
                "candidate_text": "Docker, Kubernetes",
                "candidate_name": None,
                "mapping_status": "needs_separation",
                "existing_skill": None,
                "missing_fields": ["individual_skill_names", "level", "evidence"],
                "profile_change_ready": False,
            },
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


def _confirmation(
    mapping: dict,
    *,
    level: str = "project",
    evidence: list[str] | None = None,
    confirmed_at: datetime = CONFIRMED_AT,
) -> dict:
    return build_profile_skill_confirmation(
        mapping,
        mapping_item_id="skill-mapping-item-001",
        level=level,
        evidence=evidence or ["합성 프로젝트에서 API 서버 구현"],
        confirmed_at=confirmed_at,
    )


class ProfileSkillAdditionTest(unittest.TestCase):
    def test_builds_complete_skill_from_latest_confirmation_without_applying(self) -> None:
        profile = _profile()
        original_profile = deepcopy(profile)
        mapping = _mapping_proposal(profile)
        confirmations = [
            _confirmation(
                mapping,
                level="learning",
                evidence=["합성 학습 과정"],
                confirmed_at=CONFIRMED_AT,
            ),
            _confirmation(
                mapping,
                level="project",
                evidence=["합성 프로젝트에서 API 서버 구현"],
                confirmed_at=CONFIRMED_AT + timedelta(minutes=1),
            ),
        ]

        proposal = build_profile_skill_addition_proposal(
            profile,
            mapping,
            confirmations,
            created_at=ADDITION_AT,
        )

        self.assertEqual(profile, original_profile)
        self.assertEqual("needs_final_review", proposal["profile_skill_addition"]["status"])
        self.assertEqual(
            {
                "new_skill_candidate_count": 1,
                "confirmed_skill_count": 1,
                "unconfirmed_skill_count": 0,
                "duplicate_existing_count": 1,
                "needs_separation_count": 1,
            },
            proposal["summary"],
        )
        self.assertEqual(1, len(proposal["skill_additions"]))
        addition = proposal["skill_additions"][0]
        skill = addition["proposed_skill"]
        self.assertTrue(skill["skill_id"].startswith("skill-import-"))
        self.assertEqual("FastAPI", skill["name"])
        self.assertEqual("project", skill["level"])
        self.assertEqual(["합성 프로젝트에서 API 서버 구현"], skill["evidence"])
        self.assertEqual("needs_final_review", addition["application_status"])
        self.assertFalse(proposal["metadata"]["profile_updated"])

    def test_keeps_unconfirmed_candidate_out_of_additions(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)

        proposal = build_profile_skill_addition_proposal(
            profile,
            mapping,
            [],
            created_at=ADDITION_AT,
        )

        self.assertEqual("no_confirmed_skills", proposal["profile_skill_addition"]["status"])
        self.assertEqual([], proposal["skill_additions"])
        self.assertEqual(1, proposal["summary"]["unconfirmed_skill_count"])

    def test_ignores_valid_confirmation_for_another_mapping(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        other_mapping = deepcopy(mapping)
        other_mapping["profile_skill_mapping"]["mapping_id"] = (
            "profile-skill-mapping-aaaaaaaaaaaaaaaaaaaaaaaa"
        )
        confirmation = _confirmation(other_mapping)

        proposal = build_profile_skill_addition_proposal(
            profile,
            mapping,
            [confirmation],
            created_at=ADDITION_AT,
        )

        self.assertEqual(0, proposal["summary"]["confirmed_skill_count"])

    def test_rejects_changed_confirmation_identity_or_source(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        changed_id = _confirmation(mapping)
        changed_id["profile_skill_confirmation"]["confirmation_id"] = "changed"
        with self.assertRaisesRegex(ProfileDocumentError, "확인 ID"):
            build_profile_skill_addition_proposal(
                profile,
                mapping,
                [changed_id],
                created_at=ADDITION_AT,
            )

        changed_source = _confirmation(mapping)
        changed_source["source"]["line_start"] = 999
        with self.assertRaisesRegex(ProfileDocumentError, "원문 참조"):
            build_profile_skill_addition_proposal(
                profile,
                mapping,
                [changed_source],
                created_at=ADDITION_AT,
            )

    def test_rejects_profile_changed_after_mapping(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        changed_profile = deepcopy(profile)
        changed_profile["profile"]["basic"]["locale"] = "en-US"

        with self.assertRaisesRegex(ProfileDocumentError, "프로필 내용이 변경"):
            build_profile_skill_addition_proposal(
                changed_profile,
                mapping,
                [_confirmation(mapping)],
                created_at=ADDITION_AT,
            )

    def test_rejects_confirmed_skill_now_duplicated_in_profile(self) -> None:
        profile = _profile()
        profile["profile"]["skills"].append(
            {
                "skill_id": "skill-fastapi",
                "name": "fastapi",
                "level": "learning",
                "evidence": ["합성 학습"],
            }
        )
        mapping = _mapping_proposal(profile)

        with self.assertRaisesRegex(ProfileDocumentError, "기존 기술과 중복"):
            build_profile_skill_addition_proposal(
                profile,
                mapping,
                [_confirmation(mapping)],
                created_at=ADDITION_AT,
            )

    def test_rejects_tampered_confirmation_details(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        confirmation = _confirmation(mapping)
        confirmation["profile_skill_confirmation"]["evidence"] = [" 앞 공백"]

        with self.assertRaisesRegex(ProfileDocumentError, "정규화되지 않음"):
            build_profile_skill_addition_proposal(
                profile,
                mapping,
                [confirmation],
                created_at=ADDITION_AT,
            )

    def test_rejects_mapping_status_inconsistent_with_items(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        mapping["profile_skill_mapping"]["status"] = "duplicate_only"

        with self.assertRaisesRegex(ProfileDocumentError, "항목 구성"):
            build_profile_skill_addition_proposal(
                profile,
                mapping,
                [],
                created_at=ADDITION_AT,
            )

    def test_saves_and_reuses_identical_addition_proposal(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        confirmation = _confirmation(mapping)
        first = build_profile_skill_addition_proposal(
            profile,
            mapping,
            [confirmation],
            created_at=ADDITION_AT,
        )
        second = build_profile_skill_addition_proposal(
            profile,
            mapping,
            [confirmation],
            created_at=ADDITION_AT + timedelta(days=1),
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path, first_created = save_profile_skill_addition_proposal(
                first, directory
            )
            second_path, second_created = save_profile_skill_addition_proposal(
                second, directory
            )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_path, second_path)

    def test_rejects_tampered_existing_addition_proposal(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)
        proposal = build_profile_skill_addition_proposal(
            profile,
            mapping,
            [_confirmation(mapping)],
            created_at=ADDITION_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_skill_addition_proposal(proposal, directory)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["skill_additions"][0]["proposed_skill"]["level"] = "work"
            path.write_text(json.dumps(tampered), encoding="utf-8")

            with self.assertRaisesRegex(ProfileDocumentError, "skill_additions"):
                save_profile_skill_addition_proposal(proposal, directory)

    def test_rejects_naive_created_at(self) -> None:
        profile = _profile()
        mapping = _mapping_proposal(profile)

        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_skill_addition_proposal(
                profile,
                mapping,
                [],
                created_at=datetime(2026, 9, 14, 20),
            )


if __name__ == "__main__":
    unittest.main()
