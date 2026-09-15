from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import (  # noqa: E402
    build_greenhouse_discovery_records,
    run_greenhouse_discovery,
)


def _job(job_id: int, title: str) -> dict:
    return {
        "id": job_id,
        "title": title,
        "company_name": "Example Company",
        "location": {"name": "Seoul, South Korea"},
        "absolute_url": f"https://example.com/careers?gh_jid={job_id}",
        "first_published": "2026-09-14T09:00:00+09:00",
        "updated_at": "2026-09-14T10:00:00+09:00",
        "application_deadline": None,
    }


class GreenhouseDiscoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.search_plan = json.loads(
            (REPOSITORY_ROOT / "data/job_search_plan.example.json").read_text(
                encoding="utf-8"
            )
        )
        cls.execution_time = datetime.fromisoformat("2026-09-14T12:00:00+09:00")

    def test_ranks_ai_agent_and_demotes_explicit_internship(self) -> None:
        result = build_greenhouse_discovery_records(
            [
                _job(100, "Software Engineer, AI Agent"),
                _job(101, "AI Agent Engineer, Intern"),
                _job(102, "Technical Writer"),
            ],
            self.search_plan,
            board_token="example",
            discovered_at=self.execution_time,
            policy_checked_at=date(2026, 9, 14),
            is_example=True,
        )
        records = result["records"]

        self.assertEqual(["high", "medium", "review"], [
            record["profile_relevance"]["priority"] for record in records
        ])
        self.assertEqual(
            "unknown", records[0]["profile_relevance"]["employment_assessment"]
        )
        self.assertEqual(
            "mismatch", records[1]["profile_relevance"]["employment_assessment"]
        )
        self.assertEqual("available", records[0]["availability"]["detail_status"])
        self.assertFalse(records[0]["availability"]["match_ready"])
        self.assertEqual(
            "2026-09-14T10:00:00+09:00", records[0]["source"]["updated_at"]
        )
        self.assertNotIn("content", records[0])

    def test_demotes_explicit_talent_pool_title(self) -> None:
        result = build_greenhouse_discovery_records(
            [
                _job(
                    103,
                    "Expression of Interest(채용관심등록): Software Engineer - Korea",
                ),
                _job(104, "Software Engineer"),
            ],
            self.search_plan,
            board_token="example",
            discovered_at=self.execution_time,
            policy_checked_at=date(2026, 9, 14),
            is_example=True,
        )

        talent_pool, active_opening = result["records"]
        self.assertEqual("low", talent_pool["profile_relevance"]["priority"])
        self.assertEqual("high", talent_pool["profile_relevance"]["confidence"])
        self.assertIn(
            "자동 상세 분석 대상에서 제외",
            talent_pool["profile_relevance"]["reason"],
        )
        self.assertNotEqual("low", active_opening["profile_relevance"]["priority"])

    def test_keeps_valid_job_and_reports_invalid_job(self) -> None:
        result = build_greenhouse_discovery_records(
            [_job(100, "AI Agent Engineer"), {"id": 101}],
            self.search_plan,
            board_token="example",
            discovered_at=self.execution_time,
            policy_checked_at=date(2026, 9, 14),
        )

        self.assertEqual(1, len(result["records"]))
        self.assertEqual(1, len(result["errors"]))
        self.assertEqual(2, result["errors"][0]["item_number"])

    def test_service_deduplicates_board_jobs_across_runs(self) -> None:
        jobs = [_job(100, "Software Engineer, AI Agent")]
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "discoveries.json"
            with patch(
                "career_agent.discovery.service.fetch_greenhouse_jobs",
                return_value=jobs,
            ):
                first = run_greenhouse_discovery(
                    self.search_plan,
                    store_path,
                    board_token="example",
                    policy_checked_at=date(2026, 9, 14),
                    discovered_at=self.execution_time,
                )
                second = run_greenhouse_discovery(
                    self.search_plan,
                    store_path,
                    board_token="example",
                    policy_checked_at=date(2026, 9, 14),
                    discovered_at=self.execution_time,
                )

        self.assertEqual(1, first["new_records"])
        self.assertEqual("100", first["current_records"][0]["identity"]["external_id"])
        self.assertEqual({"high": 1}, first["new_record_priorities"])
        self.assertEqual(0, second["new_records"])
        self.assertEqual(1, second["duplicate_records"])


if __name__ == "__main__":
    unittest.main()
