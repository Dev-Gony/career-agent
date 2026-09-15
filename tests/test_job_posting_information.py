from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import (  # noqa: E402
    JobPostingInformationError,
    assess_job_posting_information,
    match_job_requirements,
)


class JobPostingInformationTest(unittest.TestCase):
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

    def test_detailed_posting_is_sufficient(self) -> None:
        result = assess_job_posting_information(self.posting)

        self.assertEqual("sufficient", result["level"])
        self.assertEqual([], result["missing_fields"])
        self.assertIn("적합도 판정이 아닙니다", result["interpretation"])

    def test_missing_one_core_section_is_partial(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["responsibilities"] = []

        result = assess_job_posting_information(posting)

        self.assertEqual("partial", result["level"])
        self.assertIn("responsibilities", result["missing_fields"])

    def test_posting_without_duties_and_requirements_is_insufficient(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["responsibilities"] = []
        posting["job_posting"]["requirements"] = []
        posting["job_posting"]["experience"] = {
            "minimum_years": None,
            "maximum_years": None,
            "level_text": "경력 연수 미확인",
            "equivalent_experience_allowed": False,
        }
        posting["job_posting"]["employment"]["type"] = "unknown"

        result = assess_job_posting_information(posting)

        self.assertEqual("insufficient", result["level"])
        self.assertIn("responsibilities", result["missing_fields"])
        self.assertIn("required_qualifications", result["missing_fields"])
        self.assertIn("experience", result["missing_fields"])
        self.assertIn("employment", result["missing_fields"])

    def test_combined_match_exposes_information_level_separately(self) -> None:
        result = match_job_requirements(self.profile, self.posting)

        self.assertEqual("sufficient", result["job_posting_information"]["level"])
        self.assertEqual("적극 지원", result["application_recommendation"]["decision"])

    def test_rejects_missing_required_structure(self) -> None:
        posting = deepcopy(self.posting)
        del posting["job_posting"]["employment"]

        with self.assertRaisesRegex(JobPostingInformationError, "employment"):
            assess_job_posting_information(posting)


if __name__ == "__main__":
    unittest.main()
