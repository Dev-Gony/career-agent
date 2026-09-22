from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    LocalEvidenceProfileAnalysisProvider,
    analyze_profile_extraction,
)
from tests.test_profile_analysis_draft import _extraction  # noqa: E402


ANALYZED_AT = datetime(2026, 9, 22, 13, tzinfo=timezone.utc)


class LocalProfileAnalysisTest(unittest.TestCase):
    def test_builds_grounded_review_draft_without_external_transfer(self) -> None:
        extraction = _extraction()
        provider = LocalEvidenceProfileAnalysisProvider()
        draft = analyze_profile_extraction(
            extraction,
            provider,
            analyzed_at=ANALYZED_AT,
        )

        self.assertFalse(provider.sends_data_externally)
        self.assertEqual("local", draft["analysis_source"]["data_boundary"])
        self.assertEqual(1, draft["summary"]["career_evidence_count"])
        self.assertEqual(1, draft["summary"]["achievement_evidence_count"])
        self.assertEqual(1, draft["summary"]["technology_evidence_count"])
        achievement = draft["analysis"]["achievement_evidence"][0]
        self.assertEqual(
            "회귀 테스트 시간을 40% 단축했습니다.",
            achievement["result_evidence"],
        )
        technology = draft["analysis"]["technology_evidence"][0]
        self.assertEqual("Python", technology["technology_name"])
        self.assertEqual("unconfirmed", technology["proficiency_status"])
        self.assertIn(
            technology["usage_evidence"],
            extraction["candidates"][2]["text"],
        )

    def test_does_not_invent_achievement_without_action_and_quantity(self) -> None:
        extraction = _extraction()
        extraction["candidates"][1]["text"] = "품질 향상을 담당했습니다."
        draft = analyze_profile_extraction(
            extraction,
            LocalEvidenceProfileAnalysisProvider(),
            analyzed_at=ANALYZED_AT,
        )

        self.assertEqual(0, draft["summary"]["achievement_evidence_count"])

    def test_uses_exact_original_technology_spelling(self) -> None:
        extraction = _extraction()
        extraction["candidates"][2]["text"] = "python과 Gemini로 검증 도구를 개발했습니다."
        draft = analyze_profile_extraction(
            extraction,
            LocalEvidenceProfileAnalysisProvider(),
            analyzed_at=ANALYZED_AT,
        )

        names = [
            item["technology_name"]
            for item in draft["analysis"]["technology_evidence"]
        ]
        self.assertEqual(["python", "Gemini"], names)

    def test_keeps_negative_learning_and_scale_only_claims_unconfirmed(self) -> None:
        extraction = _extraction()
        extraction["candidates"][0]["text"] = "Docker 개발 경험 없음"
        extraction["candidates"][1]["text"] = "Python 학습 중"
        extraction["candidates"][2]["text"] = "100건 테스트를 수행했습니다."
        draft = analyze_profile_extraction(
            extraction,
            LocalEvidenceProfileAnalysisProvider(),
            analyzed_at=ANALYZED_AT,
        )

        self.assertEqual(0, draft["summary"]["career_evidence_count"])
        self.assertEqual(0, draft["summary"]["achievement_evidence_count"])
        self.assertEqual(0, draft["summary"]["technology_evidence_count"])
        self.assertEqual(3, draft["summary"]["unknown_count"])
        confidences = {
            item["confidence"]
            for category in draft["analysis"].values()
            for item in category
        }
        self.assertNotIn("high", confidences)


if __name__ == "__main__":
    unittest.main()
