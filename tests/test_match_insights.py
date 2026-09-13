from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import match_job_requirements  # noqa: E402


class MatchInsightsTest(unittest.TestCase):
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

    def test_example_builds_ranked_strengths_and_preferred_gaps(self) -> None:
        result = match_job_requirements(self.profile, self.posting)

        self.assertEqual(3, len(result["strengths"]))
        self.assertIn("Tech News Automation", result["strengths"][0]["title"])
        self.assertEqual(
            ["Docker", "AWS"], [gap["name"] for gap in result["gaps"]]
        )
        self.assertTrue(
            all(gap["priority"] == "preferred_only" for gap in result["gaps"])
        )
        self.assertEqual([], result["unknowns"])

    def test_unknown_required_skill_is_unknown_not_gap(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"].append(
            {
                "requirement_id": "requirement-kubernetes",
                "type": "skill",
                "name": "Kubernetes",
                "level": "required",
                "evidence_text": "Kubernetes 운영 경험",
            }
        )

        result = match_job_requirements(self.profile, posting)

        self.assertNotIn("Kubernetes", [gap["name"] for gap in result["gaps"]])
        self.assertIn(
            "Kubernetes", [unknown["subject"] for unknown in result["unknowns"]]
        )

    def test_required_gap_is_immediate(self) -> None:
        profile = deepcopy(self.profile)
        python = next(
            skill
            for skill in profile["profile"]["skills"]
            if skill["skill_id"] == "skill-python"
        )
        python["level"] = "exposure"
        python["evidence"] = ["설치 및 화면 확인"]

        result = match_job_requirements(profile, self.posting)
        python_gap = next(gap for gap in result["gaps"] if gap["name"] == "Python")

        self.assertEqual("immediate", python_gap["priority"])

    def test_ineligible_condition_is_blocking_gap(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["career_history"][0]["duration_years"] = 1
        posting = deepcopy(self.posting)
        posting["job_posting"]["experience"].update(
            {"minimum_years": 3, "level_text": "경력 3년 이상"}
        )

        result = match_job_requirements(profile, posting)
        blocking = [gap for gap in result["gaps"] if gap["priority"] == "blocking"]

        self.assertEqual(1, len(blocking))
        self.assertEqual("experience", blocking[0]["name"])

    def test_unknowns_are_ordered_by_decision_impact(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"].append(
            {
                "requirement_id": "requirement-unknown",
                "type": "other",
                "name": "Unknown required condition",
                "level": "required",
                "evidence_text": "Unknown required condition",
            }
        )
        posting["job_posting"]["preferred_qualifications"].append(
            {
                "qualification_id": "qualification-unknown",
                "type": "other",
                "name": "Unknown preferred condition",
                "evidence_text": "Unknown preferred condition",
            }
        )
        posting["job_posting"]["responsibilities"].append(
            {
                "responsibility_id": "responsibility-unknown",
                "text": "Unrecognized responsibility",
            }
        )
        posting["job_posting"]["employment"]["type"] = "unknown"

        result = match_job_requirements(self.profile, posting)

        self.assertEqual(
            ["requirements", "eligibility", "responsibilities", "preferred_qualifications"],
            [item["source"] for item in result["unknowns"]],
        )
        self.assertEqual(
            ["critical", "critical", "high", "low"],
            [item["priority"] for item in result["unknowns"]],
        )
        self.assertEqual("고용 형태", result["unknowns"][1]["subject"])

    def test_partial_requirement_unknown_is_promoted_for_review(self) -> None:
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

        result = match_job_requirements(self.profile, posting)

        self.assertEqual(
            "AI/ML 또는 백엔드 운영 시스템 직접 소유 범위",
            result["unknowns"][0]["subject"],
        )
        self.assertEqual("critical", result["unknowns"][0]["priority"])


if __name__ == "__main__":
    unittest.main()
