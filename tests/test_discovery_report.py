from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import format_discovery_records  # noqa: E402


class DiscoveryReportTest(unittest.TestCase):
    def test_formats_candidate_with_non_final_warning(self) -> None:
        record = json.loads(
            (REPOSITORY_ROOT / "data/job_discovery.example.json").read_text(
                encoding="utf-8"
            )
        )["job_discovery"]

        report = format_discovery_records([record])

        self.assertIn("[HIGH] 비식별 예시 AI 자동화 엔지니어", report)
        self.assertIn("회사: 비식별 예시 기업", report)
        self.assertIn("최종 적합도나 지원 추천이 아닙니다", report)
        self.assertIn("https://example.com/jobs/view?job=0000000000000", report)

    def test_filters_by_priority(self) -> None:
        record = json.loads(
            (REPOSITORY_ROOT / "data/job_discovery.example.json").read_text(
                encoding="utf-8"
            )
        )["job_discovery"]

        report = format_discovery_records([record], priority="review")

        self.assertIn("표시할 후보가 없습니다", report)

    def test_cleans_rss_location_delimiters(self) -> None:
        record = json.loads(
            (REPOSITORY_ROOT / "data/job_discovery.example.json").read_text(
                encoding="utf-8"
            )
        )["job_discovery"]
        record["summary"]["location_text"] = "|경기>성남시 분당구"

        report = format_discovery_records([record])

        self.assertIn("지역: 경기 > 성남시 분당구", report)


if __name__ == "__main__":
    unittest.main()
