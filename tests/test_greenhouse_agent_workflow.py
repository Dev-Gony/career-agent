from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.workflows import (  # noqa: E402
    profile_content_sha256,
    run_greenhouse_agent,
)


def _record(job_id: str, priority: str, published_at: str) -> dict:
    return {
        "identity": {
            "provider": "greenhouse",
            "external_id": job_id,
        },
        "source": {
            "board_token": "example",
            "source_url": f"https://example.com/jobs/{job_id}",
            "published_at": published_at,
            "updated_at": "2026-09-14T10:00:00+09:00",
        },
        "summary": {
            "title": f"Example Job {job_id}",
            "company": "Example Company",
        },
        "profile_relevance": {
            "priority": priority,
            "reason": "합성 후보 선별 근거",
        },
    }


class GreenhouseAgentWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.execution_time = datetime.fromisoformat("2026-09-14T13:00:00+09:00")
        self.discovery = {
            "current_external_ids": ["100", "101"],
            "fetched_records": 2,
            "current_records": [
                _record("100", "high", "2026-09-13T12:00:00+09:00"),
                _record("101", "high", "2026-09-14T12:00:00+09:00"),
            ],
        }

    @patch("career_agent.workflows.greenhouse_agent.analyze_greenhouse_job")
    @patch("career_agent.workflows.greenhouse_agent.run_greenhouse_discovery")
    def test_analyzes_only_newest_current_high_candidate(
        self, mocked_discovery, mocked_analyze
    ) -> None:
        mocked_discovery.return_value = self.discovery
        mocked_analyze.return_value = {"match_result": {"identity": {"analysis_id": "a"}}}

        with tempfile.TemporaryDirectory() as directory:
            result = run_greenhouse_agent(
                {"profile": {}},
                {"job_search_plan": {}},
                Path(directory) / "discoveries.json",
                board_token="example",
                policy_checked_at=date(2026, 9, 14),
                executed_at=self.execution_time,
            )

        self.assertEqual("analyzed", result["status"])
        self.assertEqual("101", result["selection"]["external_job_id"])
        mocked_analyze.assert_called_once_with(
            {"profile": {}},
            board_token="example",
            job_id="101",
            created_at=self.execution_time,
        )

    @patch("career_agent.workflows.greenhouse_agent.analyze_greenhouse_job")
    @patch("career_agent.workflows.greenhouse_agent.run_greenhouse_discovery")
    def test_stops_when_current_board_has_no_high_candidate(
        self, mocked_discovery, mocked_analyze
    ) -> None:
        mocked_discovery.return_value = {
            **self.discovery,
            "current_records": [
                _record("100", "medium", "2026-09-14T12:00:00+09:00")
            ],
        }

        with tempfile.TemporaryDirectory() as directory:
            result = run_greenhouse_agent(
                {"profile": {}},
                {"job_search_plan": {}},
                Path(directory) / "discoveries.json",
                board_token="example",
                policy_checked_at=date(2026, 9, 14),
                executed_at=self.execution_time,
            )

        self.assertEqual("no_high_candidate", result["status"])
        self.assertIsNone(result["analysis"])
        mocked_analyze.assert_not_called()

    @patch("career_agent.workflows.greenhouse_agent.analyze_greenhouse_job")
    @patch("career_agent.workflows.greenhouse_agent.run_greenhouse_discovery")
    def test_reuses_analysis_when_job_profile_and_rules_are_unchanged(
        self, mocked_discovery, mocked_analyze
    ) -> None:
        profile = {"profile": {}}
        mocked_discovery.return_value = {
            **self.discovery,
            "current_external_ids": ["101"],
            "current_records": [self.discovery["current_records"][1]],
        }
        previous_analysis = {
            "job_posting": {
                "source": {"updated_at": "2026-09-14T10:00:00+09:00"}
            },
            "match_result": {
                "identity": {"analysis_id": "analysis-existing"},
                "inputs": {
                    "profile_content_sha256": profile_content_sha256(profile)
                },
                "metadata": {
                    "matching_rules_version": "0.1",
                    "analysis_pipeline_version": "0.1",
                },
            },
        }
        previous_run = {
            "selection": {
                "board_token": "example",
                "external_job_id": "101",
            },
            "analysis": previous_analysis,
        }

        with tempfile.TemporaryDirectory() as directory:
            result = run_greenhouse_agent(
                profile,
                {"job_search_plan": {}},
                Path(directory) / "discoveries.json",
                board_token="example",
                policy_checked_at=date(2026, 9, 14),
                executed_at=self.execution_time,
                previous_runs=[previous_run],
            )

        self.assertEqual("reused", result["status"])
        self.assertEqual("analysis-existing", result["reuse"]["analysis_id"])
        self.assertEqual(previous_analysis, result["analysis"])
        mocked_analyze.assert_not_called()

    @patch("career_agent.workflows.greenhouse_agent.analyze_greenhouse_job")
    @patch("career_agent.workflows.greenhouse_agent.run_greenhouse_discovery")
    def test_changed_profile_does_not_reuse_analysis(
        self, mocked_discovery, mocked_analyze
    ) -> None:
        mocked_discovery.return_value = {
            **self.discovery,
            "current_external_ids": ["101"],
            "current_records": [self.discovery["current_records"][1]],
        }
        mocked_analyze.return_value = {
            "match_result": {"identity": {"analysis_id": "analysis-new"}}
        }
        previous_run = {
            "selection": {
                "board_token": "example",
                "external_job_id": "101",
            },
            "analysis": {
                "job_posting": {
                    "source": {"updated_at": "2026-09-14T10:00:00+09:00"}
                },
                "match_result": {
                    "identity": {"analysis_id": "analysis-existing"},
                    "inputs": {"profile_content_sha256": "different"},
                    "metadata": {
                        "matching_rules_version": "0.1",
                        "analysis_pipeline_version": "0.1",
                    },
                },
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            result = run_greenhouse_agent(
                {"profile": {"changed": True}},
                {"job_search_plan": {}},
                Path(directory) / "discoveries.json",
                board_token="example",
                policy_checked_at=date(2026, 9, 14),
                executed_at=self.execution_time,
                previous_runs=[previous_run],
            )

        self.assertEqual("analyzed", result["status"])
        mocked_analyze.assert_called_once()


if __name__ == "__main__":
    unittest.main()
