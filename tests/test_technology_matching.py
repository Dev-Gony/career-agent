from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import (  # noqa: E402
    TechnologyMatchError,
    match_technology_requirements,
)


class TechnologyMatchingTest(unittest.TestCase):
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

    def test_matches_example_technology_requirements(self) -> None:
        result = match_technology_requirements(self.profile, self.posting)

        required = {
            item["requirement"]["name"]: item["assessment"]["result"]
            for item in result["required_matches"]
        }
        preferred = {
            item["requirement"]["name"]: item["assessment"]["result"]
            for item in result["preferred_matches"]
        }

        self.assertEqual({"Python": "strong_match"}, required)
        self.assertEqual(
            {
                "Docker": "gap",
                "AWS": "gap",
                "LLM API": "strong_match",
            },
            preferred,
        )
        self.assertEqual(1, result["summary"]["required"]["strong_match"])
        self.assertEqual(2, result["summary"]["preferred"]["gap"])
        self.assertEqual(1, result["summary"]["preferred"]["strong_match"])

    def test_missing_skill_is_unknown_instead_of_gap(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"].append(
            {
                "requirement_id": "requirement-kubernetes",
                "type": "skill",
                "name": "Kubernetes",
                "level": "required",
                "evidence_text": "Kubernetes 사용 경험",
            }
        )

        result = match_technology_requirements(self.profile, posting)
        kubernetes = result["required_matches"][-1]

        self.assertEqual("unknown", kubernetes["assessment"]["result"])
        self.assertEqual([], kubernetes["user_evidence"])
        self.assertEqual(["Kubernetes의 실제 사용 경험"], kubernetes["unknowns"])

    def test_learning_level_is_partial(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"] = [
            {
                "requirement_id": "requirement-sql",
                "type": "skill",
                "name": "SQL",
                "level": "required",
                "evidence_text": "SQL 사용 경험",
            }
        ]

        result = match_technology_requirements(self.profile, posting)

        self.assertEqual(
            "partial", result["required_matches"][0]["assessment"]["result"]
        )

    def test_rejects_duplicate_canonical_skill_names(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["skills"].append(
            {
                "skill_id": "skill-restful-api",
                "name": "RESTful API",
                "level": "project",
                "evidence": ["합성 테스트"],
            }
        )

        with self.assertRaisesRegex(TechnologyMatchError, "중복 기술 이름"):
            match_technology_requirements(profile, self.posting)


if __name__ == "__main__":
    unittest.main()
