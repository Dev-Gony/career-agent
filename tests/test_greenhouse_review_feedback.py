from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.review import (  # noqa: E402
    GreenhouseReviewQueueError,
    build_greenhouse_human_review,
    save_greenhouse_human_review,
)
from career_agent.review.queue import REVIEW_QUEUE_SCHEMA_VERSION  # noqa: E402


def _queue(*, analysis_status: str = "analyzed_current") -> dict:
    return {
        "review_queue": {
            "queue_id": "greenhouse-review-queue-example",
            "created_at": "2026-09-14T12:00:00+09:00",
        },
        "items": [
            {
                "position": 1,
                "candidate_key": "greenhouse:example:100",
                "board_token": "example",
                "external_job_id": "100",
                "company": "Example",
                "title": "AI Engineer",
                "source_url": "https://example.com/jobs/100",
                "analysis_status": analysis_status,
                "analysis_id": (
                    "analysis-example" if analysis_status == "analyzed_current" else None
                ),
            }
        ],
        "metadata": {"schema_version": REVIEW_QUEUE_SCHEMA_VERSION},
    }


class GreenhouseReviewFeedbackTest(unittest.TestCase):
    def test_builds_explicit_metadata_only_human_review(self) -> None:
        review = build_greenhouse_human_review(
            _queue(),
            position=1,
            fit_assessment="fit",
            recommendation_useful=True,
            reviewed_at=datetime(2026, 9, 14, 13, tzinfo=timezone.utc),
            notes="사용자 경력 방향과 일치",
        )

        self.assertEqual("reviewed", review["human_review"]["status"])
        self.assertEqual("fit", review["human_review"]["fit_assessment"])
        self.assertTrue(review["human_review"]["recommendation_useful"])
        self.assertEqual("analysis-example", review["source"]["analysis_id"])
        self.assertFalse(review["metadata"]["contains_profile_content"])
        self.assertFalse(review["metadata"]["contains_job_description_content"])
        self.assertNotIn("job_posting", review)

    def test_rejects_candidate_without_current_analysis(self) -> None:
        with self.assertRaisesRegex(GreenhouseReviewQueueError, "상세 분석"):
            build_greenhouse_human_review(
                _queue(analysis_status="needs_analysis"),
                position=1,
                fit_assessment="hold",
                recommendation_useful=None,
                reviewed_at=datetime(2026, 9, 14, 13, tzinfo=timezone.utc),
            )

    def test_rejects_unknown_fit_assessment(self) -> None:
        with self.assertRaisesRegex(GreenhouseReviewQueueError, "허용값"):
            build_greenhouse_human_review(
                _queue(),
                position=1,
                fit_assessment="maybe",
                recommendation_useful=None,
                reviewed_at=datetime(2026, 9, 14, 13, tzinfo=timezone.utc),
            )

    def test_rejects_overlong_notes(self) -> None:
        with self.assertRaisesRegex(GreenhouseReviewQueueError, "1000자"):
            build_greenhouse_human_review(
                _queue(),
                position=1,
                fit_assessment="not_fit",
                recommendation_useful=False,
                reviewed_at=datetime(2026, 9, 14, 13, tzinfo=timezone.utc),
                notes="a" * 1001,
            )

    def test_saves_without_overwriting_existing_review(self) -> None:
        review = build_greenhouse_human_review(
            _queue(),
            position=1,
            fit_assessment="hold",
            recommendation_useful=None,
            reviewed_at=datetime(2026, 9, 14, 13, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_greenhouse_human_review(review, directory)
            actual = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(GreenhouseReviewQueueError, "이미 존재"):
                save_greenhouse_human_review(review, directory)

        self.assertEqual("hold", actual["human_review"]["fit_assessment"])


if __name__ == "__main__":
    unittest.main()
