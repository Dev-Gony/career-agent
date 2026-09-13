from __future__ import annotations

from email.message import Message
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import IncruitFeedError, fetch_incruit_rss  # noqa: E402


class FakeResponse:
    def __init__(
        self,
        payload: bytes,
        *,
        url: str = "https://www.incruit.com/rss/job.asp?occ1=150",
        content_type: str = "text/xml; charset=utf-8",
        status: int = 200,
    ) -> None:
        self.payload = payload
        self.url = url
        self.status = status
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(payload))

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


class IncruitFeedTest(unittest.TestCase):
    def test_fetches_allowed_xml_response(self) -> None:
        payload = (REPOSITORY_ROOT / "data/incruit_rss_item.example.xml").read_bytes()
        response = FakeResponse(payload)

        with patch(
            "career_agent.discovery.incruit_feed.urlopen", return_value=response
        ) as mocked_open:
            actual = fetch_incruit_rss(
                "https://www.incruit.com/rss/job.asp?occ1=150"
            )

        self.assertIn("비식별 예시 AI 자동화 엔지니어", actual)
        request = mocked_open.call_args.args[0]
        self.assertEqual(
            "career-agent-personal-mvp/0.1", request.get_header("User-agent")
        )

    def test_rejects_unapproved_host_without_request(self) -> None:
        with patch("career_agent.discovery.incruit_feed.urlopen") as mocked_open:
            with self.assertRaisesRegex(IncruitFeedError, "허용되지 않은"):
                fetch_incruit_rss("https://example.com/rss.xml")

        mocked_open.assert_not_called()

    def test_rejects_oversized_response(self) -> None:
        response = FakeResponse(b"x" * 20)

        with patch(
            "career_agent.discovery.incruit_feed.urlopen", return_value=response
        ):
            with self.assertRaisesRegex(IncruitFeedError, "허용 크기"):
                fetch_incruit_rss(
                    "https://www.incruit.com/rss/job.asp?occ1=150",
                    max_bytes=10,
                )


if __name__ == "__main__":
    unittest.main()
