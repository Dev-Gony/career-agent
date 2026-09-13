from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import match_job_requirements  # noqa: E402


class ApplicationRecommendationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(
            (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
                encoding="utf-8"
            )
        )
        cls.posting = json.loads(
            (REPOSITORY_ROOT / "data/job_posting.example.json").read_text(
                encoding="utf-8"
            )
        )

    def test_example_is_active_application_despite_preferred_gaps(self) -> None:
        result = match_job_requirements(self.profile, self.posting)
        recommendation = result["application_recommendation"]

        self.assertEqual("적극 지원", recommendation["decision"])
        self.assertEqual("high", recommendation["confidence"])
        self.assertTrue(
            any("Docker" in caution and "AWS" in caution for caution in recommendation["cautions"])
        )
        self.assertIn("합격 가능성 예측이 아닙니다", recommendation["interpretation"])

    def test_required_gap_recommends_improvement_before_application(self) -> None:
        profile = deepcopy(self.profile)
        python = next(
            skill for skill in profile["profile"]["skills"] if skill["skill_id"] == "skill-python"
        )
        python["level"] = "exposure"
        python["evidence"] = ["설치 및 화면 확인"]

        result = match_job_requirements(profile, self.posting)

        self.assertEqual(
            "역량 보완 후 지원", result["application_recommendation"]["decision"]
        )

    def test_unknown_required_condition_makes_recommendation_conditional(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"].append(
            {
                "requirement_id": "requirement-certificate",
                "type": "certification",
                "name": "Example Certificate",
                "level": "required",
                "evidence_text": "Example Certificate 필수",
            }
        )

        result = match_job_requirements(self.profile, posting)

        self.assertEqual("조건부 지원", result["application_recommendation"]["decision"])

    def test_conditional_eligibility_makes_recommendation_conditional(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["experience"].update(
            {"minimum_years": 3, "level_text": "경력 3년 이상"}
        )

        result = match_job_requirements(self.profile, posting)

        self.assertEqual("조건부 지원", result["application_recommendation"]["decision"])

    def test_ineligible_condition_lowers_application_priority(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["career_history"][0]["duration_years"] = 1
        posting = deepcopy(self.posting)
        posting["job_posting"]["experience"].update(
            {"minimum_years": 3, "level_text": "경력 3년 이상"}
        )

        result = match_job_requirements(profile, posting)

        self.assertEqual(
            "현재는 우선순위 낮음",
            result["application_recommendation"]["decision"],
        )

    def test_unknown_responsibility_lowers_active_to_recommended(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["responsibilities"].append(
            {"responsibility_id": "responsibility-sales", "text": "해외 영업 전략 수립"}
        )

        result = match_job_requirements(self.profile, posting)

        self.assertEqual("지원 추천", result["application_recommendation"]["decision"])


if __name__ == "__main__":
    unittest.main()
