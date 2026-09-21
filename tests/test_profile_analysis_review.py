from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_draft,
    build_profile_analysis_review,
    build_profile_document_import,
    build_profile_text_extraction,
    save_profile_analysis_draft,
    save_profile_analysis_review,
)
from scripts.review_profile_analysis_item import main  # noqa: E402


REVIEWED_AT = datetime(2026, 9, 21, 12, tzinfo=timezone.utc)


def _draft() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.md"
        source.write_text(
            "## 경력\n- QA Engineer로 API 테스트를 수행했습니다.\n",
            encoding="utf-8",
        )
        manifest, content = build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
        )
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
        )
    return build_profile_analysis_draft(
        extraction,
        {
            "career_evidence": [
                {
                    "role_or_context": "QA Engineer",
                    "period_expression": None,
                    "responsibility_evidence": "API 테스트를 수행했습니다.",
                    "candidate_ids": ["candidate-001"],
                    "confidence": "high",
                }
            ],
            "achievement_evidence": [],
            "technology_evidence": [],
            "unknowns": [],
        },
        analyzed_at=datetime(2026, 9, 21, 11, tzinfo=timezone.utc),
        provider_name="synthetic",
        model_name="fixture-v1",
        data_boundary="local",
    )


class ProfileAnalysisReviewTest(unittest.TestCase):
    def test_builds_review_without_copying_analysis_or_candidate_text(self) -> None:
        draft = _draft()
        review = build_profile_analysis_review(
            draft,
            item_type="career_evidence",
            item_position=1,
            decision="approve",
            reviewed_at=REVIEWED_AT,
        )

        self.assertEqual(
            "approve",
            review["profile_analysis_review"]["decision"],
        )
        self.assertEqual(
            draft["profile_analysis_draft"]["draft_id"],
            review["source"]["draft_id"],
        )
        self.assertEqual("career_evidence", review["source"]["item_type"])
        self.assertEqual(1, review["source"]["item_position"])
        self.assertFalse(review["metadata"]["contains_analysis_text"])
        self.assertFalse(review["metadata"]["contains_candidate_text"])
        self.assertFalse(review["metadata"]["profile_updated"])
        serialized = json.dumps(review, ensure_ascii=False)
        self.assertNotIn("QA Engineer", serialized)
        self.assertNotIn("API 테스트", serialized)
        self.assertNotIn("candidate-001", serialized)

    def test_rejects_unknown_item_or_out_of_range_position(self) -> None:
        draft = _draft()
        with self.assertRaisesRegex(ProfileDocumentError, "item_type 허용값"):
            build_profile_analysis_review(
                draft,
                item_type="unsupported",
                item_position=1,
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )
        with self.assertRaisesRegex(ProfileDocumentError, "2번 항목이 없음"):
            build_profile_analysis_review(
                draft,
                item_type="career_evidence",
                item_position=2,
                decision="approve",
                reviewed_at=REVIEWED_AT,
            )

    def test_rejects_tampered_draft_before_building_review(self) -> None:
        draft = deepcopy(_draft())
        draft["analysis"]["career_evidence"][0]["role_or_context"] = "변조된 역할"

        with self.assertRaisesRegex(ProfileDocumentError, "ID와 내용 지문"):
            build_profile_analysis_review(
                draft,
                item_type="career_evidence",
                item_position=1,
                decision="reject",
                reviewed_at=REVIEWED_AT,
            )

    def test_saves_immutable_private_review(self) -> None:
        review = build_profile_analysis_review(
            _draft(),
            item_type="career_evidence",
            item_position=1,
            decision="reject",
            reviewed_at=REVIEWED_AT,
            notes="역할 표현 확인 필요",
        )
        with tempfile.TemporaryDirectory() as directory:
            output_path = save_profile_analysis_review(review, directory)
            saved = json.loads(output_path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(ProfileDocumentError, "이미 존재"):
                save_profile_analysis_review(review, directory)

        self.assertEqual(review, saved)

    def test_rejects_tampered_review_identity_before_saving(self) -> None:
        review = build_profile_analysis_review(
            _draft(),
            item_type="career_evidence",
            item_position=1,
            decision="approve",
            reviewed_at=REVIEWED_AT,
        )
        review["profile_analysis_review"]["notes"] = "나중에 추가한 메모"

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ProfileDocumentError, "ID와 내용 지문"):
                save_profile_analysis_review(review, directory)

    def test_cli_records_one_review_without_updating_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft = _draft()
            draft_directory = root / "drafts"
            review_directory = root / "reviews"
            save_profile_analysis_draft(draft, draft_directory)
            output = StringIO()
            with patch(
                "sys.argv",
                [
                    "review_profile_analysis_item.py",
                    "--draft-id",
                    draft["profile_analysis_draft"]["draft_id"],
                    "--item-type",
                    "career_evidence",
                    "--item-position",
                    "1",
                    "--decision",
                    "approve",
                    "--draft-directory",
                    str(draft_directory),
                    "--review-directory",
                    str(review_directory),
                ],
            ), redirect_stdout(output):
                result = main()

            saved = list(review_directory.glob("*.json"))

        self.assertEqual(0, result)
        self.assertEqual(1, len(saved))
        self.assertIn("개인 프로필은 변경하지 않았습니다", output.getvalue())


if __name__ == "__main__":
    unittest.main()
