from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.workflows import (  # noqa: E402
    ANALYSIS_PIPELINE_VERSION,
    analyze_greenhouse_job,
)


class GreenhouseAnalysisWorkflowTest(unittest.TestCase):
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

    @patch("career_agent.workflows.greenhouse_analysis.build_greenhouse_job_posting")
    @patch("career_agent.workflows.greenhouse_analysis.fetch_greenhouse_job")
    def test_packages_posting_and_persistable_match_result(
        self, mocked_fetch, mocked_build
    ) -> None:
        mocked_fetch.return_value = {"id": 12345}
        mocked_build.return_value = self.posting
        created_at = datetime(2026, 9, 13, 18, 30, tzinfo=timezone.utc)

        actual = analyze_greenhouse_job(
            self.profile,
            board_token="example",
            job_id="12345",
            created_at=created_at,
        )

        result = actual["match_result"]
        self.assertEqual("job-001", actual["job_posting"]["identity"]["posting_id"])
        self.assertEqual("completed", result["identity"]["status"])
        self.assertIn("job-001", result["identity"]["analysis_id"])
        self.assertEqual(
            "https://example.com/jobs/ai-automation-engineer",
            result["inputs"]["posting_source_url"],
        )
        self.assertEqual("not_reviewed", result["metadata"]["human_review_status"])
        self.assertEqual(
            ANALYSIS_PIPELINE_VERSION,
            result["metadata"]["analysis_pipeline_version"],
        )
        self.assertEqual(64, len(result["inputs"]["profile_content_sha256"]))
        self.assertEqual([], result["metadata"]["incomplete_sections"])
        self.assertIn("facts", result["analysis_notes"])
        self.assertNotIn("profile", actual)
        mocked_fetch.assert_called_once_with("example", "12345")


if __name__ == "__main__":
    unittest.main()
