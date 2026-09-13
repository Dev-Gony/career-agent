from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import RequirementMatchError, match_job_requirements  # noqa: E402


class RequirementMatchingServiceTest(unittest.TestCase):
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

    def test_combines_matches_in_original_posting_order(self) -> None:
        result = match_job_requirements(self.profile, self.posting)

        self.assertEqual(
            ["Python", "REST API integration", "automation project"],
            [item["requirement"]["name"] for item in result["required_matches"]],
        )
        self.assertEqual(
            ["strong_match", "strong_match", "strong_match"],
            [item["assessment"]["result"] for item in result["required_matches"]],
        )
        self.assertEqual(
            ["Docker", "AWS", "LLM API"],
            [item["requirement"]["name"] for item in result["preferred_matches"]],
        )
        self.assertEqual(
            ["gap", "gap", "strong_match"],
            [item["assessment"]["result"] for item in result["preferred_matches"]],
        )
        self.assertEqual(3, result["summary"]["required"]["strong_match"])
        self.assertEqual(2, result["summary"]["preferred"]["gap"])
        self.assertEqual("sample-user-001", result["inputs"]["profile_id"])
        self.assertEqual("job-001", result["inputs"]["posting_id"])

    def test_keeps_unsupported_condition_as_unknown(self) -> None:
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
        match = result["required_matches"][-1]

        self.assertEqual("unknown", match["assessment"]["result"])
        self.assertEqual([], match["user_evidence"])
        self.assertEqual(4, result["summary"]["required"]["total"])

    def test_rejects_duplicate_source_ids_across_sections(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"][0][
            "qualification_id"
        ] = "requirement-python"

        with self.assertRaisesRegex(RequirementMatchError, "중복 공고 항목 ID"):
            match_job_requirements(self.profile, posting)


if __name__ == "__main__":
    unittest.main()
