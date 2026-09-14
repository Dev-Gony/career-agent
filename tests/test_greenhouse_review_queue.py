from __future__ import annotations

from datetime import datetime, timezone
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
    build_greenhouse_review_queue,
    save_greenhouse_review_queue,
)
from career_agent.workflows import (  # noqa: E402
    ANALYSIS_PIPELINE_VERSION,
    profile_content_sha256,
)


def _record(
    job_id: str,
    priority: str,
    updated_at: str,
    *,
    title: str | None = None,
) -> dict:
    return {
        "identity": {"provider": "greenhouse", "external_id": job_id},
        "source": {
            "board_token": "example",
            "source_url": f"https://boards.greenhouse.io/example/jobs/{job_id}",
            "published_at": updated_at,
            "updated_at": updated_at,
        },
        "summary": {
            "company": "Example",
            "title": title or f"Job {job_id}",
            "location_text": "Seoul",
        },
        "profile_relevance": {
            "priority": priority,
            "reason": f"{priority} 테스트 근거",
        },
    }


class GreenhouseReviewQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {"profile": {"basic": {"profile_id": "sample"}}}
        self.search_plan = {
            "job_search_plan": {
                "role_axes": [
                    {
                        "priority": 1,
                        "canonical_role": "AI Automation Engineer",
                        "discovery_terms": ["AI Agent"],
                    }
                ]
            }
        }
        self.high = _record("100", "high", "2026-09-10T10:00:00+09:00")
        self.medium = _record("200", "medium", "2026-09-14T10:00:00+09:00")
        self.review = _record("300", "review", "2026-09-15T10:00:00+09:00")
        self.low = _record("400", "low", "2026-09-16T10:00:00+09:00")
        self.discovery = {
            "executed_at": "2026-09-14T11:00:00+09:00",
            "board_results": [
                {
                    "board_token": "example",
                    "current_records": [
                        self.review,
                        self.medium,
                        self.low,
                        self.high,
                    ],
                }
            ],
        }

    def _previous_run(self) -> dict:
        return {
            "selection": {
                "board_token": "example",
                "external_job_id": "100",
            },
            "analysis": {
                "job_posting": {
                    "source": {"updated_at": self.high["source"]["updated_at"]}
                },
                "match_result": {
                    "identity": {"analysis_id": "analysis-current"},
                    "inputs": {
                        "profile_content_sha256": profile_content_sha256(self.profile)
                    },
                    "metadata": {
                        "matching_rules_version": MATCHING_RULES_VERSION,
                        "analysis_pipeline_version": ANALYSIS_PIPELINE_VERSION,
                        "human_review_status": "not_reviewed",
                    },
                },
            },
        }

    def test_orders_priority_before_recency_and_excludes_low(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [self._previous_run()],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        )

        self.assertEqual(
            ["100", "200", "300"],
            [item["external_job_id"] for item in queue["items"]],
        )
        self.assertEqual("analyzed_current", queue["items"][0]["analysis_status"])
        self.assertEqual("needs_analysis", queue["items"][1]["analysis_status"])
        self.assertEqual("not_reviewed", queue["items"][0]["human_review"]["status"])
        self.assertEqual(3, queue["summary"]["eligible_current_candidates"])

    def test_deduplicates_candidate_and_applies_limit(self) -> None:
        duplicate = _record("300", "review", "2026-09-16T10:00:00+09:00")
        self.discovery["board_results"][0]["current_records"].append(duplicate)

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            limit=2,
        )

        self.assertEqual(3, queue["summary"]["eligible_current_candidates"])
        self.assertEqual(2, queue["summary"]["selected_candidates"])
        self.assertEqual([1, 2], [item["position"] for item in queue["items"]])

    def test_prefers_matching_location_and_broad_role_signal_within_review(self) -> None:
        local_technical = _record(
            "500",
            "review",
            "2026-09-10T10:00:00+09:00",
            title="Software Engineer",
        )
        local_technical["profile_relevance"]["location_assessment"] = "match"
        local_technical["profile_relevance"]["employment_assessment"] = "unknown"
        remote_newer = _record(
            "600",
            "review",
            "2026-09-16T10:00:00+09:00",
            title="Growth Director",
        )
        remote_newer["profile_relevance"]["location_assessment"] = "mismatch"
        remote_newer["profile_relevance"]["employment_assessment"] = "unknown"
        self.discovery["board_results"][0]["current_records"] = [
            remote_newer,
            local_technical,
        ]

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        )

        self.assertEqual("500", queue["items"][0]["external_job_id"])
        self.assertEqual(["engineer"], queue["items"][0]["broad_role_signals"])

    def test_changed_profile_marks_previous_analysis_as_needing_analysis(self) -> None:
        changed_profile = {"profile": {"basic": {"profile_id": "changed"}}}

        queue = build_greenhouse_review_queue(
            self.discovery,
            [self._previous_run()],
            changed_profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            limit=1,
        )

        self.assertEqual("needs_analysis", queue["items"][0]["analysis_status"])
        self.assertIsNone(queue["items"][0]["analysis_id"])

    def test_saves_immutable_metadata_only_snapshot(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            limit=1,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = save_greenhouse_review_queue(queue, directory)
            actual = json.loads(path.read_text(encoding="utf-8"))
            with self.assertRaisesRegex(
                GreenhouseReviewQueueError, "이미 존재"
            ):
                save_greenhouse_review_queue(queue, directory)

        self.assertFalse(actual["metadata"]["contains_profile_content"])
        self.assertFalse(actual["metadata"]["contains_job_description_content"])
        self.assertNotIn("job_posting", actual)

    def test_requires_timezone_aware_creation_time(self) -> None:
        with self.assertRaisesRegex(GreenhouseReviewQueueError, "시간대"):
            build_greenhouse_review_queue(
                self.discovery,
                [],
                self.profile,
                self.search_plan,
                created_at=datetime(2026, 9, 14, 12),
            )


if __name__ == "__main__":
    unittest.main()
