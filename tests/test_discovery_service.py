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

from career_agent.discovery import run_incruit_discovery  # noqa: E402


class DiscoveryServiceTest(unittest.TestCase):
    def test_runs_discovery_and_deduplicates_next_run(self) -> None:
        xml_text = (REPOSITORY_ROOT / "data/incruit_rss_item.example.xml").read_text(
            encoding="utf-8"
        )
        search_plan = json.loads(
            (REPOSITORY_ROOT / "data/job_search_plan.example.json").read_text(
                encoding="utf-8"
            )
        )
        execution_time = datetime.fromisoformat("2026-09-13T09:00:00+09:00")

        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "discoveries.json"
            with patch(
                "career_agent.discovery.service.fetch_incruit_rss",
                return_value=xml_text,
            ):
                first = run_incruit_discovery(
                    search_plan,
                    store_path,
                    feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
                    policy_checked_at=date.fromisoformat("2026-09-13"),
                    discovered_at=execution_time,
                )
                second = run_incruit_discovery(
                    search_plan,
                    store_path,
                    feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
                    policy_checked_at=date.fromisoformat("2026-09-13"),
                    discovered_at=execution_time,
                )

        self.assertEqual(1, first["new_records"])
        self.assertEqual(0, first["duplicate_records"])
        self.assertEqual({"high": 1}, first["new_record_priorities"])
        self.assertEqual(0, second["new_records"])
        self.assertEqual(1, second["duplicate_records"])
        self.assertEqual({}, second["new_record_priorities"])


if __name__ == "__main__":
    unittest.main()
