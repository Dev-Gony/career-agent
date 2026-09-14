from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import match_job_requirements  # noqa: E402


class PortfolioRecommendationTest(unittest.TestCase):
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

    def test_connects_learning_gap_to_completed_project(self) -> None:
        result = match_job_requirements(self.profile, self.posting)

        self.assertEqual(1, len(result["portfolio_recommendations"]))
        recommendation = result["portfolio_recommendations"][0]
        self.assertEqual("Tech News Automation", recommendation["target_project"])
        self.assertIn("Docker", recommendation["related_gap"])
        self.assertIn("Docker 적용", recommendation["change"])
        self.assertIn("성공 로그", recommendation["expected_evidence"])

    def test_uses_weaker_direct_project_evidence_when_no_learning_gap_exists(
        self,
    ) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"] = [
            item
            for item in posting["job_posting"]["preferred_qualifications"]
            if item["name"] == "LLM API"
        ]

        result = match_job_requirements(self.profile, posting)

        recommendation = result["portfolio_recommendations"][0]
        self.assertEqual("Tech News Automation", recommendation["target_project"])
        self.assertIn("모니터링", recommendation["related_gap"])
        self.assertIn("알림", recommendation["change"])

    def test_does_not_turn_unknown_responsibility_into_portfolio_work(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"] = []
        posting["job_posting"]["responsibilities"] = [
            {
                "responsibility_id": "responsibility-unknown",
                "text": "대규모 분산 시스템 아키텍처 총괄",
            }
        ]

        result = match_job_requirements(self.profile, posting)

        self.assertEqual([], result["portfolio_recommendations"])

    def test_does_not_recommend_unfinished_project_as_portfolio_target(self) -> None:
        profile = deepcopy(self.profile)
        for project in profile["profile"]["projects"]:
            project["status"] = "planning"

        result = match_job_requirements(profile, self.posting)

        self.assertEqual([], result["portfolio_recommendations"])


if __name__ == "__main__":
    unittest.main()
