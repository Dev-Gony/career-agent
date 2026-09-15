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
    build_profile_evidence_summary,
    save_profile_evidence_summary,
)


ANALYZED_AT = datetime(2026, 9, 15, 10, tzinfo=timezone.utc)


def _profile() -> dict:
    return {
        "profile": {
            "basic": {"profile_id": "test-profile"},
            "skills": [],
        }
    }


def _extraction() -> dict:
    document_id = "profile-document-resume-0123456789abcdef0123"
    texts = [
        "2023.01-2025.08 Python 자동화 업무를 수행했습니다.",
        "반복 작업 90%를 개선했습니다.",
        "Kubernetes 환경을 확인했습니다.",
    ]
    return {
        "profile_extraction": {
            "extraction_id": "profile-text-extraction-0123456789abcdef01234567",
            "status": "needs_review",
        },
        "source_document": {"document_id": document_id},
        "candidates": [
            {
                "candidate_id": f"candidate-{position:03d}",
                "profile_section": "career_history",
                "text": text,
                "status": "needs_review",
                "source_evidence": {
                    "document_id": document_id,
                    "line_start": position,
                    "line_end": position,
                },
            }
            for position, text in enumerate(texts, start=1)
        ],
        "metadata": {
            "schema_version": "0.1",
            "profile_updated": False,
        },
    }


class ProfileEvidenceSummaryTest(unittest.TestCase):
    def test_builds_non_final_signals_without_copying_candidate_text(self) -> None:
        result = build_profile_evidence_summary(
            _extraction(),
            _profile(),
            analyzed_at=ANALYZED_AT,
        )

        self.assertEqual(
            {
                "candidate_count": 3,
                "duration_expression_count": 1,
                "quantified_expression_count": 1,
                "action_expression_count": 2,
                "technology_mention_candidate_count": 1,
                "technology_names": ["Python"],
            },
            result["summary"],
        )
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("반복 작업 90%", serialized)
        self.assertNotIn("Kubernetes", serialized)
        self.assertFalse(result["metadata"]["contains_candidate_text"])
        self.assertFalse(result["metadata"]["profile_updated"])

    def test_rejects_profile_updated_extraction(self) -> None:
        extraction = _extraction()
        extraction["metadata"]["profile_updated"] = True

        with self.assertRaisesRegex(ProfileDocumentError, "프로필 적용 전"):
            build_profile_evidence_summary(
                extraction,
                _profile(),
                analyzed_at=ANALYZED_AT,
            )

    def test_rejects_naive_timestamp(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_evidence_summary(
                _extraction(),
                _profile(),
                analyzed_at=datetime(2026, 9, 15, 10),
            )

    def test_saves_and_reuses_same_signals_with_later_timestamp(self) -> None:
        first = build_profile_evidence_summary(
            _extraction(),
            _profile(),
            analyzed_at=ANALYZED_AT,
        )
        later = build_profile_evidence_summary(
            _extraction(),
            _profile(),
            analyzed_at=ANALYZED_AT + timedelta(minutes=5),
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path, first_created = save_profile_evidence_summary(
                first,
                directory,
            )
            later_path, later_created = save_profile_evidence_summary(
                later,
                directory,
            )

        self.assertTrue(first_created)
        self.assertFalse(later_created)
        self.assertEqual(first_path, later_path)

    def test_rejects_tampered_existing_summary(self) -> None:
        result = build_profile_evidence_summary(
            _extraction(),
            _profile(),
            analyzed_at=ANALYZED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_evidence_summary(result, directory)
            changed = deepcopy(result)
            changed["summary"]["candidate_count"] = 99
            with self.assertRaisesRegex(ProfileDocumentError, "내용이 일치하지 않음"):
                save_profile_evidence_summary(changed, directory)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
