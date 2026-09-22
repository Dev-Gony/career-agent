from __future__ import annotations

from copy import deepcopy
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
    HUMAN_REVIEW_SCHEMA_VERSION,
    GreenhouseReviewQueueError,
    build_greenhouse_review_queue,
    save_greenhouse_review_queue,
)
from career_agent.review.queue import (  # noqa: E402
    validate_greenhouse_review_queue_search_plan,
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


def _human_review(
    *,
    reviewed_at: str,
    review_id: str,
    fit_assessment: str,
    analysis_id: str = "analysis-current",
) -> dict:
    return {
        "human_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_at,
            "status": "reviewed",
            "fit_assessment": fit_assessment,
            "recommendation_useful": True,
            "notes": "사용자 판단",
        },
        "candidate": {
            "candidate_key": "greenhouse:example:100",
            "board_token": "example",
            "external_job_id": "100",
        },
        "source": {"analysis_id": analysis_id},
        "metadata": {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "contains_profile_content": False,
            "contains_job_description_content": False,
        },
    }


class GreenhouseReviewQueueTest(unittest.TestCase):
    def setUp(self) -> None:
        self.profile = {"profile": {"basic": {"profile_id": "sample"}}}
        self.search_plan = {
            "job_search_plan": {
                "identity": {"plan_id": "search-plan-review-queue-test"},
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
        self.review = _record(
            "300",
            "review",
            "2026-09-15T10:00:00+09:00",
            title="Automation Platform Engineer",
        )
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
            source_run_filename="source.json",
        )

        self.assertEqual(
            ["100", "200", "300"],
            [item["external_job_id"] for item in queue["items"]],
        )
        self.assertEqual("analyzed_current", queue["items"][0]["analysis_status"])
        self.assertEqual("needs_analysis", queue["items"][1]["analysis_status"])
        self.assertEqual("not_reviewed", queue["items"][0]["human_review"]["status"])
        self.assertEqual(3, queue["summary"]["eligible_current_candidates"])

    def test_records_and_validates_exact_search_plan_identity(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )

        self.assertEqual(
            "search-plan-review-queue-test",
            queue["review_queue"]["search_plan_id"],
        )
        self.assertEqual(
            "greenhouse-review-queue-20260914T120000000000+0000",
            queue["review_queue"]["queue_id"],
        )
        self.assertRegex(
            queue["metadata"]["search_plan_content_sha256"],
            r"^[0-9a-f]{64}$",
        )
        validate_greenhouse_review_queue_search_plan(queue, self.search_plan)
        validate_greenhouse_review_queue_search_plan(
            queue,
            self.search_plan["job_search_plan"],
        )

    def test_rejects_queue_when_search_plan_content_changes_under_same_id(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )
        changed_plan = deepcopy(self.search_plan)
        changed_plan["job_search_plan"]["role_axes"][0]["discovery_terms"].append(
            "Workflow Automation"
        )

        with self.assertRaisesRegex(GreenhouseReviewQueueError, "검색 계획 내용"):
            validate_greenhouse_review_queue_search_plan(queue, changed_plan)

    def test_accepts_semantically_same_generated_plan_with_later_timestamp(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )
        regenerated_plan = deepcopy(self.search_plan)
        regenerated_plan["job_search_plan"]["identity"]["generated_at"] = (
            "2026-09-15T12:00:00+00:00"
        )

        validate_greenhouse_review_queue_search_plan(queue, regenerated_plan)

    def test_rejects_queue_when_search_plan_id_changes(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )
        changed_plan = deepcopy(self.search_plan)
        changed_plan["job_search_plan"]["identity"]["plan_id"] = (
            "search-plan-review-queue-other"
        )

        with self.assertRaisesRegex(GreenhouseReviewQueueError, "검색 계획 ID"):
            validate_greenhouse_review_queue_search_plan(queue, changed_plan)

    def test_rejects_legacy_queue_without_search_plan_identity(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )
        del queue["review_queue"]["search_plan_id"]
        del queue["metadata"]["search_plan_content_sha256"]

        with self.assertRaisesRegex(GreenhouseReviewQueueError, "재사용할 수 없음"):
            validate_greenhouse_review_queue_search_plan(queue, self.search_plan)

    def test_excludes_legacy_talent_pool_record_from_queue(self) -> None:
        talent_pool = _record(
            "500",
            "review",
            "2026-09-17T10:00:00+09:00",
            title="Expression of Interest: Software Engineer - Korea",
        )
        active_opening = _record(
            "600",
            "review",
            "2026-09-16T10:00:00+09:00",
            title="Automation Platform Engineer - Korea",
        )
        self.discovery["board_results"][0]["current_records"] = [
            talent_pool,
            active_opening,
        ]

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )

        self.assertEqual(1, queue["summary"]["eligible_current_candidates"])
        self.assertEqual("600", queue["items"][0]["external_job_id"])

    def test_deduplicates_candidate_and_applies_limit(self) -> None:
        duplicate = _record(
            "300",
            "review",
            "2026-09-16T10:00:00+09:00",
            title="Automation Platform Engineer",
        )
        self.discovery["board_results"][0]["current_records"].append(duplicate)

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
            limit=2,
        )

        self.assertEqual(3, queue["summary"]["eligible_current_candidates"])
        self.assertEqual(2, queue["summary"]["selected_candidates"])
        self.assertEqual([1, 2], [item["position"] for item in queue["items"]])

    def test_keeps_distinctive_profile_signal_and_excludes_generic_role_word(self) -> None:
        local_technical = _record(
            "500",
            "review",
            "2026-09-10T10:00:00+09:00",
            title="Automation Platform Engineer",
        )
        local_technical["profile_relevance"]["location_assessment"] = "match"
        local_technical["profile_relevance"]["employment_assessment"] = "unknown"
        remote_newer = _record(
            "600",
            "review",
            "2026-09-16T10:00:00+09:00",
            title="Security Engineer",
        )
        remote_newer["profile_relevance"]["location_assessment"] = "mismatch"
        remote_newer["profile_relevance"]["employment_assessment"] = "unknown"
        translated_generic = _record(
            "700",
            "review",
            "2026-09-17T10:00:00+09:00",
            title="Software Engineer (소프트웨어 엔지니어)",
        )
        translated_generic["profile_relevance"]["location_assessment"] = "match"
        translated_generic["profile_relevance"]["employment_assessment"] = "unknown"
        self.discovery["board_results"][0]["current_records"] = [
            remote_newer,
            translated_generic,
            local_technical,
        ]

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )

        self.assertEqual("500", queue["items"][0]["external_job_id"])
        self.assertEqual(
            ["automation", "engineer"],
            queue["items"][0]["broad_role_signals"],
        )
        self.assertEqual(1, queue["summary"]["eligible_current_candidates"])

    def test_keeps_unique_single_term_from_profile_role_axis(self) -> None:
        self.search_plan["job_search_plan"]["role_axes"][0][
            "discovery_terms"
        ].append("ITSM")
        itsm = _record(
            "900",
            "review",
            "2026-09-17T10:00:00+09:00",
            title="ITSM Administrator",
        )
        self.discovery["board_results"][0]["current_records"] = [itsm]

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )

        self.assertEqual(["itsm"], queue["items"][0]["broad_role_signals"])

    def test_moves_explicit_preference_mismatch_after_review_candidate(self) -> None:
        medium_mismatch = _record(
            "700",
            "medium",
            "2026-09-16T10:00:00+09:00",
            title="AI Agent Engineer, Intern",
        )
        medium_mismatch["profile_relevance"]["location_assessment"] = "match"
        medium_mismatch["profile_relevance"]["employment_assessment"] = "mismatch"
        review_match = _record(
            "800",
            "review",
            "2026-09-10T10:00:00+09:00",
            title="Automation Platform Engineer",
        )
        review_match["profile_relevance"]["location_assessment"] = "match"
        review_match["profile_relevance"]["employment_assessment"] = "unknown"
        self.discovery["board_results"][0]["current_records"] = [
            medium_mismatch,
            review_match,
        ]

        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
        )

        self.assertEqual("800", queue["items"][0]["external_job_id"])

    def test_changed_profile_marks_previous_analysis_as_needing_analysis(self) -> None:
        changed_profile = {"profile": {"basic": {"profile_id": "changed"}}}

        queue = build_greenhouse_review_queue(
            self.discovery,
            [self._previous_run()],
            changed_profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
            limit=1,
        )

        self.assertEqual("needs_analysis", queue["items"][0]["analysis_status"])
        self.assertIsNone(queue["items"][0]["analysis_id"])

    def test_merges_latest_review_for_current_analysis(self) -> None:
        older = _human_review(
            reviewed_at="2026-09-14T12:00:00+09:00",
            review_id="review-older",
            fit_assessment="hold",
        )
        newer = _human_review(
            reviewed_at="2026-09-14T13:00:00+09:00",
            review_id="review-newer",
            fit_assessment="fit",
        )

        queue = build_greenhouse_review_queue(
            self.discovery,
            [self._previous_run()],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
            limit=1,
            human_reviews=[newer, older],
        )

        self.assertEqual("reviewed", queue["items"][0]["human_review"]["status"])
        self.assertEqual("fit", queue["items"][0]["human_review"]["fit_assessment"])
        self.assertEqual("review-newer", queue["items"][0]["human_review"]["review_id"])
        self.assertEqual(1, queue["summary"]["human_review_statuses"]["reviewed"])

    def test_does_not_merge_review_for_stale_analysis(self) -> None:
        stale = _human_review(
            reviewed_at="2026-09-14T13:00:00+09:00",
            review_id="review-stale",
            fit_assessment="not_fit",
            analysis_id="analysis-stale",
        )

        queue = build_greenhouse_review_queue(
            self.discovery,
            [self._previous_run()],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
            limit=1,
            human_reviews=[stale],
        )

        self.assertEqual(
            "not_reviewed", queue["items"][0]["human_review"]["status"]
        )
        self.assertIsNone(queue["items"][0]["human_review"]["review_id"])

    def test_rejects_review_with_inconsistent_candidate_key(self) -> None:
        invalid = _human_review(
            reviewed_at="2026-09-14T13:00:00+09:00",
            review_id="review-invalid",
            fit_assessment="fit",
        )
        invalid["candidate"]["candidate_key"] = "greenhouse:other:100"

        with self.assertRaisesRegex(GreenhouseReviewQueueError, "식별자"):
            build_greenhouse_review_queue(
                self.discovery,
                [self._previous_run()],
                self.profile,
                self.search_plan,
                created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
                source_run_filename="source.json",
                human_reviews=[invalid],
            )

    def test_saves_immutable_metadata_only_snapshot(self) -> None:
        queue = build_greenhouse_review_queue(
            self.discovery,
            [],
            self.profile,
            self.search_plan,
            created_at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
            source_run_filename="source.json",
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
                source_run_filename="source.json",
            )


if __name__ == "__main__":
    unittest.main()
