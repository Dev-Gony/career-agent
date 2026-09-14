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
    SKILL_LEVELS,
    ProfileDocumentError,
    build_profile_skill_confirmation,
    load_profile_skill_mapping_proposal,
    save_profile_skill_confirmation,
    save_profile_skill_mapping_proposal,
)


CONFIRMED_AT = datetime(2026, 9, 14, 19, tzinfo=timezone.utc)


def _mapping_proposal() -> dict:
    return {
        "profile_skill_mapping": {
            "mapping_id": "profile-skill-mapping-0123456789abcdef01234567",
            "created_at": "2026-09-14T18:00:00.000000+00:00",
            "status": "needs_confirmation",
            "base_profile_id": "private-user-001",
            "base_profile_content_sha256": "a" * 64,
            "source_update_proposal_id": (
                "profile-update-proposal-0123456789abcdef01234567"
            ),
            "rules_version": "0.1",
        },
        "summary": {
            "approved_candidate_count": 1,
            "skill_candidate_count": 1,
            "duplicate_existing_count": 0,
            "needs_details_count": 1,
            "needs_separation_count": 0,
            "skipped_non_skill_count": 0,
        },
        "skill_mappings": [
            {
                "mapping_item_id": "skill-mapping-item-001",
                "source": {
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
                },
                "candidate_text": "FastAPI",
                "candidate_name": "FastAPI",
                "mapping_status": "needs_details",
                "existing_skill": None,
                "missing_fields": ["level", "evidence"],
                "profile_change_ready": False,
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


class ProfileSkillConfirmationTest(unittest.TestCase):
    def test_records_level_and_evidence_without_copying_candidate_name(self) -> None:
        confirmation = build_profile_skill_confirmation(
            _mapping_proposal(),
            mapping_item_id="skill-mapping-item-001",
            level="project",
            evidence=["합성 프로젝트에서 API 서버 구현"],
            confirmed_at=CONFIRMED_AT,
            notes="공개 테스트용 합성 기록",
        )
        serialized = json.dumps(confirmation, ensure_ascii=False)

        root = confirmation["profile_skill_confirmation"]
        self.assertEqual("explicit_user_input", root["confirmation_source"])
        self.assertEqual("project", root["level"])
        self.assertEqual(["합성 프로젝트에서 API 서버 구현"], root["evidence"])
        self.assertEqual("skill-mapping-item-001", confirmation["source"]["mapping_item_id"])
        self.assertFalse(confirmation["metadata"]["contains_candidate_text"])
        self.assertFalse(confirmation["metadata"]["profile_updated"])
        self.assertNotIn("FastAPI", serialized)

    def test_accepts_only_documented_skill_levels(self) -> None:
        for position, level in enumerate(sorted(SKILL_LEVELS)):
            with self.subTest(level=level):
                confirmation = build_profile_skill_confirmation(
                    _mapping_proposal(),
                    mapping_item_id="skill-mapping-item-001",
                    level=level,
                    evidence=["합성 확인 근거"],
                    confirmed_at=CONFIRMED_AT + timedelta(minutes=position),
                )
                self.assertEqual(
                    level,
                    confirmation["profile_skill_confirmation"]["level"],
                )

        with self.assertRaisesRegex(ProfileDocumentError, "level 허용값"):
            build_profile_skill_confirmation(
                _mapping_proposal(),
                mapping_item_id="skill-mapping-item-001",
                level="expert",
                evidence=["합성 확인 근거"],
                confirmed_at=CONFIRMED_AT,
            )

    def test_rejects_invalid_evidence(self) -> None:
        invalid_cases = [
            ([], "최소 1개"),
            ("문자열 하나", "문자열 배열"),
            ([""], "문자열이 필요"),
            (["같은 근거", "같은 근거"], "중복 evidence"),
            (["a" * 301], "300자"),
            ([f"근거 {index}" for index in range(11)], "최대 10개"),
        ]
        for evidence, message in invalid_cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(ProfileDocumentError, message):
                    build_profile_skill_confirmation(
                        _mapping_proposal(),
                        mapping_item_id="skill-mapping-item-001",
                        level="project",
                        evidence=evidence,
                        confirmed_at=CONFIRMED_AT,
                    )

    def test_rejects_mapping_item_that_does_not_need_details(self) -> None:
        for status in ("duplicate_existing", "needs_separation"):
            with self.subTest(status=status):
                mapping = _mapping_proposal()
                mapping["skill_mappings"][0]["mapping_status"] = status
                with self.assertRaisesRegex(ProfileDocumentError, "needs_details"):
                    build_profile_skill_confirmation(
                        mapping,
                        mapping_item_id="skill-mapping-item-001",
                        level="project",
                        evidence=["합성 확인 근거"],
                        confirmed_at=CONFIRMED_AT,
                    )

    def test_rejects_unknown_or_duplicate_mapping_item_id(self) -> None:
        mapping = _mapping_proposal()
        with self.assertRaisesRegex(ProfileDocumentError, "찾을 수 없음"):
            build_profile_skill_confirmation(
                mapping,
                mapping_item_id="skill-mapping-item-999",
                level="project",
                evidence=["합성 확인 근거"],
                confirmed_at=CONFIRMED_AT,
            )

        mapping["skill_mappings"].append(deepcopy(mapping["skill_mappings"][0]))
        with self.assertRaisesRegex(ProfileDocumentError, "중복 기술 매핑"):
            build_profile_skill_confirmation(
                mapping,
                mapping_item_id="skill-mapping-item-001",
                level="project",
                evidence=["합성 확인 근거"],
                confirmed_at=CONFIRMED_AT,
            )

    def test_rejects_invalid_source_line_range(self) -> None:
        mapping = _mapping_proposal()
        mapping["skill_mappings"][0]["source"]["line_start"] = 0

        with self.assertRaisesRegex(ProfileDocumentError, "line_start"):
            build_profile_skill_confirmation(
                mapping,
                mapping_item_id="skill-mapping-item-001",
                level="project",
                evidence=["합성 확인 근거"],
                confirmed_at=CONFIRMED_AT,
            )

    def test_rejects_naive_timestamp_and_long_notes(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_skill_confirmation(
                _mapping_proposal(),
                mapping_item_id="skill-mapping-item-001",
                level="project",
                evidence=["합성 확인 근거"],
                confirmed_at=datetime(2026, 9, 14, 19),
            )
        with self.assertRaisesRegex(ProfileDocumentError, "1000자"):
            build_profile_skill_confirmation(
                _mapping_proposal(),
                mapping_item_id="skill-mapping-item-001",
                level="project",
                evidence=["합성 확인 근거"],
                confirmed_at=CONFIRMED_AT,
                notes="a" * 1001,
            )

    def test_saves_immutable_confirmation_without_overwrite(self) -> None:
        confirmation = build_profile_skill_confirmation(
            _mapping_proposal(),
            mapping_item_id="skill-mapping-item-001",
            level="project",
            evidence=["합성 확인 근거"],
            confirmed_at=CONFIRMED_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_profile_skill_confirmation(confirmation, directory)
            actual = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ProfileDocumentError, "이미 존재"):
                save_profile_skill_confirmation(confirmation, directory)

        self.assertEqual("project", actual["profile_skill_confirmation"]["level"])

    def test_load_mapping_rejects_path_traversal_and_id_mismatch(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProfileDocumentError, "mapping_id 형식"):
                load_profile_skill_mapping_proposal("../outside", directory)

            mapping = _mapping_proposal()
            path, _ = save_profile_skill_mapping_proposal(mapping, directory)
            stored = json.loads(path.read_text(encoding="utf-8"))
            stored["profile_skill_mapping"]["mapping_id"] = (
                "profile-skill-mapping-000000000000000000000000"
            )
            path.write_text(json.dumps(stored), encoding="utf-8")
            requested_id = mapping["profile_skill_mapping"]["mapping_id"]

            with self.assertRaisesRegex(ProfileDocumentError, "요청과 일치"):
                load_profile_skill_mapping_proposal(requested_id, directory)


if __name__ == "__main__":
    unittest.main()
