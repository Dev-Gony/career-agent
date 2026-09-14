from __future__ import annotations

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
    build_profile_candidate_review,
    build_profile_document_import,
    build_profile_text_extraction,
    load_profile_text_extraction,
    save_profile_candidate_review,
    save_profile_text_extraction,
)


IMPORTED_AT = datetime(2026, 9, 14, 14, tzinfo=timezone.utc)
EXTRACTED_AT = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 9, 14, 16, tzinfo=timezone.utc)


def _extraction() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.md"
        source.write_text("## 기술\n- Python\n- REST API\n", encoding="utf-8")
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


class ProfileCandidateReviewTest(unittest.TestCase):
    def test_builds_approval_without_copying_candidate_text(self) -> None:
        review = build_profile_candidate_review(
            _extraction(),
            candidate_id="candidate-001",
            decision="approve",
            reviewed_at=REVIEWED_AT,
            notes="실제 프로젝트에서 사용",
        )
        serialized = json.dumps(review, ensure_ascii=False)

        self.assertEqual("approve", review["candidate_review"]["decision"])
        self.assertEqual("skills", review["source"]["profile_section"])
        self.assertEqual(2, review["source"]["line_start"])
        self.assertFalse(review["metadata"]["contains_candidate_text"])
        self.assertFalse(review["metadata"]["profile_updated"])
        self.assertNotIn("Python", serialized)

    def test_rejects_unknown_candidate(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "후보를 찾을 수 없음"):
            build_profile_candidate_review(
                _extraction(),
                candidate_id="candidate-999",
                decision="reject",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_invalid_decision(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "decision 허용값"):
            build_profile_candidate_review(
                _extraction(),
                candidate_id="candidate-001",
                decision="hold",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_duplicate_candidate_id(self) -> None:
        extraction = _extraction()
        extraction["candidates"].append(dict(extraction["candidates"][0]))

        with self.assertRaisesRegex(ProfileDocumentError, "중복 후보 ID"):
            build_profile_candidate_review(
                extraction,
                candidate_id="candidate-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

    def test_loads_saved_extraction_before_review(self) -> None:
        extraction = _extraction()
        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_text_extraction(extraction, directory)
            loaded = load_profile_text_extraction(
                extraction["profile_extraction"]["extraction_id"],
                directory,
            )

        self.assertEqual(path.name, f"{loaded['profile_extraction']['extraction_id']}.json")
        self.assertEqual(2, len(loaded["candidates"]))

    def test_saves_immutable_review_without_overwrite(self) -> None:
        review = build_profile_candidate_review(
            _extraction(),
            candidate_id="candidate-002",
            decision="reject",
            reviewed_at=REVIEWED_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_profile_candidate_review(review, directory)
            actual = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ProfileDocumentError, "이미 존재"):
                save_profile_candidate_review(review, directory)

        self.assertEqual("reject", actual["candidate_review"]["decision"])

    def test_rejects_notes_over_limit(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "1000자"):
            build_profile_candidate_review(
                _extraction(),
                candidate_id="candidate-001",
                decision="approve",
                reviewed_at=REVIEWED_AT,
                notes="a" * 1001,
            )


if __name__ == "__main__":
    unittest.main()
