from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_slack_profile_analysis_summary,
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


if __name__ == "__main__":
    unittest.main()
