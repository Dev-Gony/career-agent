from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import (  # noqa: E402
    IncruitRssParseError,
    build_incruit_discovery_record,
    build_incruit_discovery_records,
)


class IncruitRssDiscoveryTest(unittest.TestCase):
    def test_builds_expected_discovery_record(self) -> None:
        xml_text = (REPOSITORY_ROOT / "data/incruit_rss_item.example.xml").read_text(
            encoding="utf-8"
        )
        search_plan = json.loads(
            (REPOSITORY_ROOT / "data/job_search_plan.example.json").read_text(
                encoding="utf-8"
            )
        )
        expected = json.loads(
            (REPOSITORY_ROOT / "data/job_discovery.example.json").read_text(
                encoding="utf-8"
            )
        )["job_discovery"]

        actual = build_incruit_discovery_record(
            xml_text,
            search_plan,
            feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
            discovered_at=datetime.fromisoformat("2026-09-13T09:00:00+09:00"),
            policy_checked_at=date.fromisoformat("2026-09-13"),
            is_example=True,
        )

        self.assertEqual(expected, actual)

    def test_rejects_rss_without_title(self) -> None:
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><item>
          <link>https://example.com/jobs/view?job=1</link>
        </item></channel></rss>
        """

        with self.assertRaisesRegex(IncruitRssParseError, "item/title"):
            build_incruit_discovery_record(
                xml_text,
                {"identity": {"profile_id": "sample-user-001"}, "role_axes": []},
                feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
                discovered_at=datetime.fromisoformat("2026-09-13T09:00:00+09:00"),
                policy_checked_at=date.fromisoformat("2026-09-13"),
            )

    def test_rejects_doctype(self) -> None:
        xml_text = """<?xml version="1.0"?>
        <!DOCTYPE rss [<!ENTITY example "unsafe">]>
        <rss version="2.0"><channel><item>
          <title>&example;</title>
          <link>https://example.com/jobs/view?job=1</link>
        </item></channel></rss>
        """

        with self.assertRaisesRegex(IncruitRssParseError, "DOCTYPE"):
            build_incruit_discovery_record(
                xml_text,
                {"identity": {"profile_id": "sample-user-001"}, "role_axes": []},
                feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
                discovered_at=datetime.fromisoformat("2026-09-13T09:00:00+09:00"),
                policy_checked_at=date.fromisoformat("2026-09-13"),
            )

    def test_batch_keeps_valid_item_and_reports_invalid_item(self) -> None:
        xml_text = (REPOSITORY_ROOT / "data/incruit_rss_item.example.xml").read_text(
            encoding="utf-8"
        )
        invalid_item = """
        <item>
          <link>https://example.com/jobs/view?job=9999999999999</link>
        </item>
        """
        xml_text = xml_text.replace("</channel>", f"{invalid_item}</channel>")
        search_plan = json.loads(
            (REPOSITORY_ROOT / "data/job_search_plan.example.json").read_text(
                encoding="utf-8"
            )
        )

        result = build_incruit_discovery_records(
            xml_text,
            search_plan,
            feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
            discovered_at=datetime.fromisoformat("2026-09-13T09:00:00+09:00"),
            policy_checked_at=date.fromisoformat("2026-09-13"),
            is_example=True,
        )

        self.assertEqual(1, len(result["records"]))
        self.assertEqual(
            [{"item_number": 2, "error": "필수 RSS 필드가 없음: item/title"}],
            result["errors"],
        )

    def test_decodes_html_entity_inside_cdata_title(self) -> None:
        xml_text = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel><item>
          <title><![CDATA[[Example &amp; Co] AI 자동화 엔지니어]]></title>
          <link>https://example.com/jobs/view?job=2</link>
          <description><![CDATA[▨ 지역 : 서울]]></description>
          <author>Example &amp; Co</author>
        </item></channel></rss>
        """
        search_plan = json.loads(
            (REPOSITORY_ROOT / "data/job_search_plan.example.json").read_text(
                encoding="utf-8"
            )
        )

        record = build_incruit_discovery_record(
            xml_text,
            search_plan,
            feed_url="https://www.incruit.com/rss/job.asp?occ1=150",
            discovered_at=datetime.fromisoformat("2026-09-13T09:00:00+09:00"),
            policy_checked_at=date.fromisoformat("2026-09-13"),
            is_example=True,
        )

        self.assertEqual("AI 자동화 엔지니어", record["summary"]["title"])
        self.assertEqual("Example & Co", record["summary"]["company"])


if __name__ == "__main__":
    unittest.main()
