from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import MATCHING_RULES_VERSION  # noqa: E402
from career_agent.review import (  # noqa: E402
    GreenhouseReviewQueueError,
    build_greenhouse_review_analysis_run,
    save_greenhouse_review_analysis_run,
    select_next_greenhouse_review_candidate,
)
from career_agent.review.queue import REVIEW_QUEUE_SCHEMA_VERSION  # noqa: E402
from career_agent.workflows import (  # noqa: E402
    ANALYSIS_PIPELINE_VERSION,
    profile_content_sha256,
)


class GreenhouseReviewAnalysisTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {"profile": {"basic": {"profile_id": "sample"}}}
        self.candidate = {
            "position": 2,
            "candidate_key": "greenhouse:example:200",
            "board_token": "example",
            "external_job_id": "200",
            "company": "Example",
            "title": "AI Engineer",
            "priority": "review",
            "ranking_reason": "넓은 직무 신호가 있음",
            "location_assessment": "match",
            "employment_assessment": "unknown",
            "source_url": "https://boards.greenhouse.io/example/jobs/200",
            "source_updated_at": "2026-09-14T10:00:00+09:00",
            "analysis_status": "needs_analysis",
        }
        self.queue = {
            "review_queue": {
                "queue_id": "queue-001",
                "source_run_filename": "source.json",
                "limit": 10,
            },
            "items": [
                {
                    **self.candidate,
                    "position": 1,
                    "employment_assessment": "mismatch",
                },
                self.candidate,
            ],
            "metadata": {
                "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
                "matching_rules_version": MATCHING_RULES_VERSION,
                "analysis_pipeline_version": ANALYSIS_PIPELINE_VERSION,
                "profile_content_sha256": profile_content_sha256(self.profile),
            },
        }
        self.analysis = {
            "job_posting": {
                "source": {
                    "board_token": "example",
                    "external_job_id": "200",
                }
            },
            "match_result": {
                "identity": {"analysis_id": "analysis-example-200"}
            },
        }

    def test_selects_first_unanalyzed_candidate_without_known_mismatch(self) -> None:
        selected = select_next_greenhouse_review_candidate(
            self.queue,
            self.profile,
        )

        self.assertEqual("200", selected["external_job_id"])
        self.assertEqual(2, selected["position"])

    def test_rejects_queue_built_from_changed_profile(self) -> None:
        changed_profile = {"profile": {"basic": {"profile_id": "changed"}}}

        with self.assertRaisesRegex(GreenhouseReviewQueueError, "프로필"):
            select_next_greenhouse_review_candidate(
                self.queue,
                changed_profile,
            )

    def test_packages_analysis_with_queue_reference_and_no_review_claim(self) -> None:
        run = build_greenhouse_review_analysis_run(
            self.queue,
            self.candidate,
            self.analysis,
            queue_filename="queue-001.json",
        )

        self.assertEqual("greenhouse_review_queue", run["workflow"])
        self.assertEqual("queue-001", run["source_review_queue"]["queue_id"])
        self.assertEqual(
            "first_unanalyzed_non_mismatch_in_review_queue",
            run["selection"]["policy"],
        )
        self.assertEqual("not_reviewed", run["metadata"]["human_review_status"])

    def test_rejects_analysis_for_different_candidate(self) -> None:
        analysis = {
            **self.analysis,
            "job_posting": {
                "source": {
                    "board_token": "example",
                    "external_job_id": "different",
                }
            },
        }

        with self.assertRaisesRegex(GreenhouseReviewQueueError, "일치하지 않음"):
            build_greenhouse_review_analysis_run(
                self.queue,
                self.candidate,
                analysis,
                queue_filename="queue-001.json",
            )

    def test_saves_analysis_without_overwrite(self) -> None:
        run = build_greenhouse_review_analysis_run(
            self.queue,
            self.candidate,
            self.analysis,
            queue_filename="queue-001.json",
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_greenhouse_review_analysis_run(run, directory)
            actual = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(GreenhouseReviewQueueError, "이미 존재"):
                save_greenhouse_review_analysis_run(run, directory)

        self.assertEqual("analysis-example-200", actual["metadata"]["analysis_id"])
        self.assertEqual(self.analysis, actual["analysis"])


if __name__ == "__main__":
    unittest.main()
