from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import match_job_requirements  # noqa: E402


class LearningRecommendationTest(unittest.TestCase):
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

    def test_turns_first_confirmed_gap_into_existing_project_action(self) -> None:
        result = match_job_requirements(self.profile, self.posting)

        self.assertEqual(1, len(result["learning_recommendations"]))
        recommendation = result["learning_recommendations"][0]
        self.assertEqual("Docker", recommendation["topic"])
        self.assertEqual("preferred_only", recommendation["priority"])
        self.assertIn("설치만", recommendation["based_on"])
        self.assertIn("Tech News Automation", recommendation["action"])
        self.assertIn("새 환경", recommendation["completion_evidence"])

    def test_does_not_turn_unknown_requirement_into_learning_task(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"].insert(
            0,
            {
                "qualification_id": "qualification-kubernetes",
                "type": "skill",
                "name": "Kubernetes",
                "evidence_text": "Kubernetes 경험 우대",
            },
        )

        result = match_job_requirements(self.profile, posting)

        self.assertEqual(
            ["Docker"],
            [item["topic"] for item in result["learning_recommendations"]],
        )

    def test_defers_preferred_cloud_gap_until_demand_is_repeated(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"] = [
            item
            for item in posting["job_posting"]["preferred_qualifications"]
            if item["name"] == "AWS"
        ]

        result = match_job_requirements(self.profile, posting)

        self.assertEqual([], result["learning_recommendations"])

    def test_keeps_recommendation_list_small_and_prioritizes_required_gap(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"].insert(
            0,
            {
                "requirement_id": "requirement-docker",
                "type": "skill",
                "name": "Docker",
                "level": "required",
                "evidence_text": "Docker 사용 경험 필수",
            },
        )

        result = match_job_requirements(self.profile, posting)

        self.assertEqual(1, len(result["learning_recommendations"]))
        self.assertEqual("immediate", result["learning_recommendations"][0]["priority"])


if __name__ == "__main__":
    unittest.main()
