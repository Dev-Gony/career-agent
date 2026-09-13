from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import (  # noqa: E402
    match_experience_requirements,
)


class ExperienceMatchingTest(unittest.TestCase):
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

    def test_matches_example_experience_requirements(self) -> None:
        result = match_experience_requirements(self.profile, self.posting)
        matches = {
            item["requirement"]["name"]: item
            for item in result["required_matches"]
        }

        self.assertEqual(
            "strong_match", matches["REST API integration"]["assessment"]["result"]
        )
        self.assertEqual(
            "strong_match", matches["automation project"]["assessment"]["result"]
        )
        self.assertEqual(2, result["summary"]["required"]["strong_match"])
        self.assertEqual(
            {"skill", "project"},
            {
                item["source_type"]
                for item in matches["REST API integration"]["user_evidence"]
            },
        )
        self.assertEqual(
            {"project", "behavior"},
            {
                item["source_type"]
                for item in matches["automation project"]["user_evidence"]
            },
        )

    def test_unrecognized_experience_is_unknown(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"] = [
            {
                "requirement_id": "requirement-sales",
                "type": "experience",
                "name": "enterprise sales",
                "level": "required",
                "evidence_text": "엔터프라이즈 영업 경험",
            }
        ]

        result = match_experience_requirements(self.profile, posting)
        match = result["required_matches"][0]

        self.assertEqual("unknown", match["assessment"]["result"])
        self.assertEqual([], match["user_evidence"])
        self.assertEqual(["enterprise sales의 실제 수행 경험"], match["unknowns"])

    def test_matches_preferred_experience(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"].append(
            {
                "qualification_id": "qualification-automation-project",
                "type": "experience",
                "name": "automation project",
                "evidence_text": "자동화 프로젝트 경험 우대",
            }
        )

        result = match_experience_requirements(self.profile, posting)
        match = result["preferred_matches"][0]

        self.assertEqual("strong_match", match["assessment"]["result"])
        self.assertEqual(
            "preferred_qualifications", match["requirement"]["source_section"]
        )

    def test_planned_project_is_partial_without_completed_evidence(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["skills"] = []
        profile["profile"]["behavior_evidence"] = []
        tech_news = profile["profile"]["projects"][0]
        tech_news["status"] = "planning"
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"] = [
            item
            for item in posting["job_posting"]["requirements"]
            if item["requirement_id"] == "requirement-automation-project"
        ]

        result = match_experience_requirements(profile, posting)

        self.assertEqual(
            "partial", result["required_matches"][0]["assessment"]["result"]
        )
        self.assertEqual(
            "medium", result["required_matches"][0]["assessment"]["confidence"]
        )

    def test_missing_evidence_is_unknown_instead_of_gap(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["skills"] = []
        profile["profile"]["projects"] = []
        profile["profile"]["behavior_evidence"] = []

        result = match_experience_requirements(profile, self.posting)

        self.assertTrue(result["required_matches"])
        self.assertTrue(
            all(
                item["assessment"]["result"] == "unknown"
                for item in result["required_matches"]
            )
        )

    def test_uses_career_as_partial_evidence_for_compound_software_experience(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"] = [
            {
                "requirement_id": "requirement-software-engineering",
                "type": "experience",
                "name": "software engineering experience",
                "level": "required",
                "evidence_text": (
                    "3+ years of software engineering experience with direct "
                    "ownership of AI/ML or backend systems in production."
                ),
            }
        ]

        result = match_experience_requirements(self.profile, posting)
        match = result["required_matches"][0]

        self.assertEqual("partial", match["assessment"]["result"])
        self.assertEqual("related", match["assessment"]["directness"])
        self.assertEqual(
            {"career"},
            {item["source_type"] for item in match["user_evidence"]},
        )
        self.assertEqual("career-001", match["user_evidence"][0]["source_id"])
        self.assertEqual(
            [
                "총 소프트웨어 엔지니어링 경력 연수",
                "AI/ML 또는 백엔드 운영 시스템 직접 소유 범위",
            ],
            match["unknowns"],
        )

    def test_missing_career_keeps_software_experience_unknown(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["career_history"] = []
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"] = [
            {
                "requirement_id": "requirement-software-engineering",
                "type": "experience",
                "name": "software engineering experience",
                "level": "required",
                "evidence_text": "Software engineering experience required.",
            }
        ]

        result = match_experience_requirements(profile, posting)

        self.assertEqual(
            "unknown", result["required_matches"][0]["assessment"]["result"]
        )


if __name__ == "__main__":
    unittest.main()
