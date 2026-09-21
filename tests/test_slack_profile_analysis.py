from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_latest_slack_profile_analysis_review_item,
    build_latest_slack_profile_analysis_summary,
    build_slack_profile_analysis_review_item,
    build_slack_profile_analysis_summary,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_draft,
    build_profile_document_import,
    build_profile_text_extraction,
    save_profile_analysis_draft,
    save_profile_text_extraction,
)


def _draft() -> dict:
    return {
        "profile_analysis_draft": {
            "draft_id": "profile-analysis-draft-0123456789abcdef01234567",
            "status": "needs_review",
        },
        "analysis": {
            "career_evidence": [
                {
                    "role_or_context": "비공개 회사 QA Engineer",
                    "candidate_ids": ["candidate-001"],
                }
            ],
            "achievement_evidence": [
                {
                    "result_evidence": "개인 식별 가능 성과 90%",
                    "candidate_ids": ["candidate-002"],
                }
            ],
            "technology_evidence": [
                {
                    "technology_name": "Python <!channel>",
                    "candidate_ids": ["candidate-003"],
                }
            ],
            "unknowns": [
                {
                    "question": "개인 연락처를 확인해야 하나요?",
                    "candidate_ids": ["candidate-004"],
                }
            ],
        },
        "summary": {
            "career_evidence_count": 1,
            "achievement_evidence_count": 1,
            "technology_evidence_count": 1,
            "unknown_count": 1,
        },
        "metadata": {
            "schema_version": "0.1",
            "contains_personal_data": True,
            "contains_candidate_text": True,
            "git_tracking_allowed": False,
            "provider_output_validated": True,
            "profile_updated": False,
        },
    }


class SlackProfileAnalysisTest(unittest.TestCase):
    def test_builds_count_only_review_summary(self) -> None:
        message = build_slack_profile_analysis_summary(_draft())

        self.assertIn("프로필 분석 초안이 준비되었습니다.", message)
        self.assertIn("- 경력 근거: 1개", message)
        self.assertIn("- 성과 근거: 1개", message)
        self.assertIn("- 기술 사용 근거: 1개", message)
        self.assertIn("- 추가 확인 질문: 1개", message)
        self.assertIn("검토 상태: 사용자 확인 필요", message)
        self.assertIn("아직 개인 프로필", message)

    def test_does_not_expose_any_analysis_text_or_slack_control_string(self) -> None:
        message = build_slack_profile_analysis_summary(_draft())

        self.assertNotIn("비공개 회사", message)
        self.assertNotIn("개인 식별 가능", message)
        self.assertNotIn("Python", message)
        self.assertNotIn("<!channel>", message)
        self.assertNotIn("개인 연락처", message)
        self.assertNotIn("candidate-", message)

    def test_rejects_summary_count_that_does_not_match_analysis(self) -> None:
        draft = _draft()
        draft["summary"]["technology_evidence_count"] = 2

        with self.assertRaisesRegex(SlackEventError, "합계가 일치하지 않음"):
            build_slack_profile_analysis_summary(draft)

    def test_rejects_unvalidated_or_already_applied_draft(self) -> None:
        for field, value, message in (
            ("provider_output_validated", False, "검증이 완료되지 않은"),
            ("profile_updated", True, "이미 프로필에 반영된"),
        ):
            with self.subTest(field=field):
                draft = deepcopy(_draft())
                draft["metadata"][field] = value
                with self.assertRaisesRegex(SlackEventError, message):
                    build_slack_profile_analysis_summary(draft)

    def test_latest_summary_distinguishes_missing_extraction_and_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extraction_directory = root / "extractions"
            draft_directory = root / "drafts"
            no_extraction = build_latest_slack_profile_analysis_summary(
                str(extraction_directory),
                str(draft_directory),
            )

            source = root / "resume.md"
            source.write_text("## 기술\n- Python\n", encoding="utf-8")
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=datetime(2026, 9, 21, 8, tzinfo=timezone.utc),
            )
            extraction = build_profile_text_extraction(
                manifest,
                content,
                extracted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
            )
            save_profile_text_extraction(extraction, extraction_directory)
            no_draft = build_latest_slack_profile_analysis_summary(
                str(extraction_directory),
                str(draft_directory),
            )

        self.assertIn("추출 결과가 없습니다", no_extraction)
        self.assertIn("분석 초안이 아직 없습니다", no_draft)

    def test_latest_summary_uses_verified_draft_without_exposing_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.md"
            source.write_text(
                "## 경력\n- QA Engineer로 API 테스트를 수행했습니다.\n",
                encoding="utf-8",
            )
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=datetime(2026, 9, 21, 8, tzinfo=timezone.utc),
            )
            extraction = build_profile_text_extraction(
                manifest,
                content,
                extracted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
            )
            extraction_directory = root / "extractions"
            draft_directory = root / "drafts"
            save_profile_text_extraction(extraction, extraction_directory)
            draft = build_profile_analysis_draft(
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
                analyzed_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
                provider_name="synthetic",
                model_name="fixture-v1",
                data_boundary="local",
            )
            save_profile_analysis_draft(draft, draft_directory)
            message = build_latest_slack_profile_analysis_summary(
                str(extraction_directory),
                str(draft_directory),
            )

        self.assertIn("경력 근거: 1개", message)
        self.assertNotIn("QA Engineer", message)
        self.assertNotIn("API 테스트", message)

    def test_review_item_shows_one_item_and_escapes_slack_control_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resume.md"
            source.write_text(
                "## 경력\n- QA Engineer <!channel>로 API 테스트를 수행했습니다.\n",
                encoding="utf-8",
            )
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=datetime(2026, 9, 21, 8, tzinfo=timezone.utc),
            )
            extraction = build_profile_text_extraction(
                manifest,
                content,
                extracted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
            )
            draft = build_profile_analysis_draft(
                extraction,
                {
                    "career_evidence": [
                        {
                            "role_or_context": "QA Engineer <!channel>",
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
                analyzed_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
                provider_name="synthetic",
                model_name="fixture-v1",
                data_boundary="local",
            )
            message = build_slack_profile_analysis_review_item(draft)

        self.assertIn("프로필 분석 항목 1/1", message)
        self.assertIn("유형: 경력 근거", message)
        self.assertIn("QA Engineer &lt;!channel&gt;", message)
        self.assertIn("API 테스트를 수행했습니다.", message)
        self.assertIn("검토 항목: 경력 근거 1번", message)
        self.assertIn("승인 또는 거부는 기록하지 않았습니다", message)
        self.assertNotIn("<!channel>", message)
        self.assertNotIn("candidate-", message)
        self.assertNotIn("profile-analysis-draft-", message)
        self.assertNotIn("synthetic", message)

    def test_latest_review_item_loads_verified_current_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.md"
            source.write_text(
                "## 기술\n- Python으로 데이터 검증 도구를 개발했습니다.\n",
                encoding="utf-8",
            )
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=datetime(2026, 9, 21, 8, tzinfo=timezone.utc),
            )
            extraction = build_profile_text_extraction(
                manifest,
                content,
                extracted_at=datetime(2026, 9, 21, 9, tzinfo=timezone.utc),
            )
            extraction_directory = root / "extractions"
            draft_directory = root / "drafts"
            save_profile_text_extraction(extraction, extraction_directory)
            draft = build_profile_analysis_draft(
                extraction,
                {
                    "career_evidence": [],
                    "achievement_evidence": [],
                    "technology_evidence": [
                        {
                            "technology_name": "Python",
                            "usage_evidence": "Python으로 데이터 검증 도구를 개발했습니다.",
                            "proficiency_status": "unconfirmed",
                            "candidate_ids": ["candidate-001"],
                            "confidence": "high",
                        }
                    ],
                    "unknowns": [],
                },
                analyzed_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
                provider_name="synthetic",
                model_name="fixture-v1",
                data_boundary="local",
            )
            save_profile_analysis_draft(draft, draft_directory)
            message = build_latest_slack_profile_analysis_review_item(
                str(extraction_directory),
                str(draft_directory),
            )

        self.assertIn("유형: 기술 사용 근거", message)
        self.assertIn("Python", message)
        self.assertIn("숙련도: 사용자 확인 전 미확정", message)
        self.assertNotIn("candidate-001", message)


if __name__ == "__main__":
    unittest.main()
