from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import (  # noqa: E402
    ResponsibilityMatchError,
    match_responsibilities,
)


class ResponsibilityMatchingTest(unittest.TestCase):
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

    def test_matches_example_responsibilities_in_source_order(self) -> None:
        result = match_responsibilities(self.profile, self.posting)

        self.assertEqual(
            [
                "strong_match",
                "strong_match",
                "strong_match",
                "match",
            ],
            [
                item["assessment"]["result"]
                for item in result["responsibility_matches"]
            ],
        )
        self.assertEqual(3, result["summary"]["strong_match"])
        self.assertEqual(1, result["summary"]["match"])

    def test_monitoring_match_keeps_missing_alerting_action(self) -> None:
        result = match_responsibilities(self.profile, self.posting)
        monitoring = result["responsibility_matches"][3]

        self.assertEqual("related", monitoring["assessment"]["directness"])
        self.assertIn("능동 실패 알림", monitoring["next_action"])

    def test_unknown_responsibility_is_not_invented(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["responsibilities"] = [
            {"responsibility_id": "responsibility-sales", "text": "해외 영업 전략 수립"}
        ]

        result = match_responsibilities(self.profile, posting)
        match = result["responsibility_matches"][0]

        self.assertEqual("unknown", match["assessment"]["result"])
        self.assertEqual([], match["user_evidence"])

    def test_planning_project_is_partial(self) -> None:
        profile = deepcopy(self.profile)
        profile["profile"]["skills"] = []
        profile["profile"]["behavior_evidence"] = []
        profile["profile"]["projects"][0]["status"] = "planning"
        posting = deepcopy(self.posting)
        posting["job_posting"]["responsibilities"] = [
            posting["job_posting"]["responsibilities"][0]
        ]

        result = match_responsibilities(profile, posting)

        self.assertEqual(
            "partial", result["responsibility_matches"][0]["assessment"]["result"]
        )

    def test_rejects_duplicate_responsibility_ids(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["responsibilities"].append(
            deepcopy(posting["job_posting"]["responsibilities"][0])
        )

        with self.assertRaisesRegex(ResponsibilityMatchError, "중복 주요 업무 ID"):
            match_responsibilities(self.profile, posting)


if __name__ == "__main__":
    unittest.main()
