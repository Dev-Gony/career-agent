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
    build_profile_candidate_review,
    build_profile_document_import,
    build_profile_skill_mapping_proposal,
    build_profile_text_extraction,
    build_profile_update_proposal,
    load_profile_update_proposal,
    save_profile_skill_mapping_proposal,
    save_profile_update_proposal,
)


IMPORTED_AT = datetime(2026, 9, 14, 14, tzinfo=timezone.utc)
EXTRACTED_AT = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 9, 14, 16, tzinfo=timezone.utc)
PROPOSED_AT = datetime(2026, 9, 14, 17, tzinfo=timezone.utc)
MAPPED_AT = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)


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


def _extraction() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.md"
        source.write_text(
            "## 기술\n"
            "- python\n"
            "- FastAPI\n"
            "- Docker, Kubernetes\n"
            "## 희망 직무\n"
            "- AI 자동화 개발\n",
            encoding="utf-8",
        )
        manifest, content = build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=IMPORTED_AT,
        )
    return build_profile_text_extraction(
        manifest,
        content,
        extracted_at=EXTRACTED_AT,
    )


def _update_proposal(profile: dict, candidate_ids: list[str]) -> dict:
    extraction = _extraction()
    reviews = [
        build_profile_candidate_review(
            extraction,
            candidate_id=candidate_id,
            decision="approve",
            reviewed_at=REVIEWED_AT + timedelta(minutes=position),
        )
        for position, candidate_id in enumerate(candidate_ids)
    ]
    return build_profile_update_proposal(
        profile,
        extraction,
        reviews,
        created_at=PROPOSED_AT,
    )


class ProfileSkillMappingTest(unittest.TestCase):
    def test_classifies_duplicate_new_composite_and_non_skill_candidates(self) -> None:
        profile = _profile()
        original_profile = deepcopy(profile)
        proposal = _update_proposal(
            profile,
            ["candidate-001", "candidate-002", "candidate-003", "candidate-004"],
        )

        mapping = build_profile_skill_mapping_proposal(
            profile,
            proposal,
            created_at=MAPPED_AT,
        )

        self.assertEqual(profile, original_profile)
        self.assertEqual("needs_confirmation", mapping["profile_skill_mapping"]["status"])
        self.assertEqual(
            {
                "approved_candidate_count": 4,
                "skill_candidate_count": 3,
                "duplicate_existing_count": 1,
                "needs_details_count": 1,
                "needs_separation_count": 1,
                "skipped_non_skill_count": 1,
            },
            mapping["summary"],
        )
        statuses = [item["mapping_status"] for item in mapping["skill_mappings"]]
        self.assertEqual(
            ["duplicate_existing", "needs_details", "needs_separation"],
            statuses,
        )
        duplicate = mapping["skill_mappings"][0]
        self.assertEqual("skill-python", duplicate["existing_skill"]["skill_id"])
        self.assertFalse(duplicate["profile_change_ready"])
        new_skill = mapping["skill_mappings"][1]
        self.assertEqual("FastAPI", new_skill["candidate_name"])
        self.assertEqual(["level", "evidence"], new_skill["missing_fields"])
        self.assertNotIn("level", new_skill)
        composite = mapping["skill_mappings"][2]
        self.assertIsNone(composite["candidate_name"])
        self.assertIn("individual_skill_names", composite["missing_fields"])
        self.assertTrue(mapping["metadata"]["contains_candidate_text"])
        self.assertFalse(mapping["metadata"]["profile_updated"])

    def test_returns_duplicate_only_for_normalized_existing_name(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, ["candidate-001"])

        mapping = build_profile_skill_mapping_proposal(
            profile,
            proposal,
            created_at=MAPPED_AT,
        )

        self.assertEqual("duplicate_only", mapping["profile_skill_mapping"]["status"])
        self.assertEqual(1, mapping["summary"]["duplicate_existing_count"])
        self.assertEqual(0, mapping["summary"]["needs_details_count"])

    def test_returns_no_skill_candidates_for_empty_approval_set(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, [])

        mapping = build_profile_skill_mapping_proposal(
            profile,
            proposal,
            created_at=MAPPED_AT,
        )

        self.assertEqual(
            "no_skill_candidates",
            mapping["profile_skill_mapping"]["status"],
        )
        self.assertEqual([], mapping["skill_mappings"])
        self.assertFalse(mapping["metadata"]["contains_candidate_text"])

    def test_rejects_profile_changed_after_update_proposal(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, ["candidate-002"])
        changed_profile = deepcopy(profile)
        changed_profile["profile"]["basic"]["locale"] = "en-US"

        with self.assertRaisesRegex(ProfileDocumentError, "프로필 내용이 변경"):
            build_profile_skill_mapping_proposal(
                changed_profile,
                proposal,
                created_at=MAPPED_AT,
            )

    def test_rejects_duplicate_existing_skill_names(self) -> None:
        profile = _profile()
        profile["profile"]["skills"].append(
            {
                "skill_id": "skill-python-duplicate",
                "name": " python ",
                "level": "learning",
                "evidence": [],
            }
        )
        proposal = _update_proposal(profile, ["candidate-001"])

        with self.assertRaisesRegex(ProfileDocumentError, "중복 기술명"):
            build_profile_skill_mapping_proposal(
                profile,
                proposal,
                created_at=MAPPED_AT,
            )

    def test_rejects_non_approval_inside_update_proposal(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, ["candidate-002"])
        proposal["proposed_additions"][0]["approval"]["decision"] = "reject"

        with self.assertRaisesRegex(ProfileDocumentError, "승인 결정"):
            build_profile_skill_mapping_proposal(
                profile,
                proposal,
                created_at=MAPPED_AT,
            )

    def test_saves_and_reuses_identical_mapping(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, ["candidate-002"])
        first = build_profile_skill_mapping_proposal(
            profile,
            proposal,
            created_at=MAPPED_AT,
        )
        second = build_profile_skill_mapping_proposal(
            profile,
            proposal,
            created_at=MAPPED_AT + timedelta(days=1),
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path, first_created = save_profile_skill_mapping_proposal(
                first, directory
            )
            second_path, second_created = save_profile_skill_mapping_proposal(
                second, directory
            )

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_path, second_path)

    def test_rejects_tampered_existing_mapping(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, ["candidate-002"])
        mapping = build_profile_skill_mapping_proposal(
            profile,
            proposal,
            created_at=MAPPED_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_skill_mapping_proposal(mapping, directory)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["skill_mappings"][0]["candidate_name"] = "Changed"
            path.write_text(json.dumps(tampered), encoding="utf-8")

            with self.assertRaisesRegex(ProfileDocumentError, "skill_mappings"):
                save_profile_skill_mapping_proposal(mapping, directory)

    def test_load_update_proposal_rejects_path_traversal_and_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProfileDocumentError, "proposal_id 형식"):
                load_profile_update_proposal("../outside", directory)

            profile = _profile()
            proposal = _update_proposal(profile, ["candidate-001"])
            path, _ = save_profile_update_proposal(proposal, directory)
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["profile_update_proposal"]["proposal_id"] = (
                "profile-update-proposal-000000000000000000000000"
            )
            path.write_text(json.dumps(stored), encoding="utf-8")
            requested_id = proposal["profile_update_proposal"]["proposal_id"]

            with self.assertRaisesRegex(ProfileDocumentError, "요청과 일치"):
                load_profile_update_proposal(requested_id, directory)

    def test_rejects_naive_created_at(self) -> None:
        profile = _profile()
        proposal = _update_proposal(profile, ["candidate-001"])

        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_skill_mapping_proposal(
                profile,
                proposal,
                created_at=datetime(2026, 9, 14, 18),
            )


if __name__ == "__main__":
    unittest.main()
