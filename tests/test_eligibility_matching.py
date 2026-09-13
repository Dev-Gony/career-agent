from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import assess_eligibility  # noqa: E402


class EligibilityMatchingTest(unittest.TestCase):
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

    def test_example_is_eligible(self) -> None:
        result = assess_eligibility(self.profile, self.posting)
        conditions = {condition["type"]: condition for condition in result["conditions"]}

        self.assertEqual("eligible", result["status"])
        self.assertEqual("met", conditions["experience"]["result"])
        self.assertEqual("not_applicable", conditions["education"]["result"])
        self.assertEqual("met", conditions["employment"]["result"])
        self.assertEqual("met", conditions["location"]["result"])

    def test_private_experience_years_need_confirmation_when_minimum_exists(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["experience"].update(
            {"minimum_years": 3, "level_text": "경력 3년 이상"}
        )

        result = assess_eligibility(self.profile, posting)

        self.assertEqual("conditional", result["status"])
        self.assertEqual("needs_confirmation", result["conditions"][0]["result"])

    def test_confirmed_short_experience_is_not_met(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["career_history"][0]["duration_years"] = 1
        posting = deepcopy(self.posting)
        posting["job_posting"]["experience"].update(
            {"minimum_years": 3, "level_text": "경력 3년 이상"}
        )

        result = assess_eligibility(profile, posting)

        self.assertEqual("ineligible", result["status"])
        self.assertEqual("not_met", result["conditions"][0]["result"])

    def test_soft_preference_mismatch_is_conditional_not_ineligible(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["location"]["region"] = "부산"
        posting["job_posting"]["employment"]["type"] = "contract"

        result = assess_eligibility(self.profile, posting)
        conditions = {condition["type"]: condition for condition in result["conditions"]}

        self.assertEqual("conditional", result["status"])
        self.assertEqual("needs_confirmation", conditions["location"]["result"])
        self.assertEqual("needs_confirmation", conditions["employment"]["result"])

    def test_required_education_without_user_data_needs_confirmation(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["education"].update(
            {"required": True, "level": "학사"}
        )

        result = assess_eligibility(self.profile, posting)
        education = result["conditions"][1]

        self.assertEqual("conditional", result["status"])
        self.assertEqual("needs_confirmation", education["result"])

    def test_known_work_mode_without_user_preference_needs_confirmation(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["location"]["remote"] = "on_site"

        result = assess_eligibility(self.profile, posting)
        location = result["conditions"][3]

        self.assertEqual("conditional", result["status"])
        self.assertEqual("needs_confirmation", location["result"])


if __name__ == "__main__":
    unittest.main()
