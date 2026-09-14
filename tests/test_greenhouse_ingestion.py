from __future__ import annotations

from datetime import date
from email.message import Message
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.ingestion import (  # noqa: E402
    GreenhouseJobError,
    build_greenhouse_job_posting,
    fetch_greenhouse_job,
    fetch_greenhouse_jobs,
)


def _example_job() -> dict:
    content = """
    &lt;p&gt;&lt;strong&gt;The Role&lt;/strong&gt;&lt;/p&gt;
    &lt;p&gt;Build a small AI workflow from prototype to operation.&lt;/p&gt;
    &lt;p&gt;&lt;strong&gt;You need to have:&lt;/strong&gt;&lt;/p&gt;
    &lt;ul&gt;
      &lt;li&gt;3+ years of software engineering experience.&lt;/li&gt;
      &lt;li&gt;Python development experience.&lt;/li&gt;
      &lt;li&gt;Hands-on experience with LLM APIs.&lt;/li&gt;
    &lt;/ul&gt;
    &lt;p&gt;&lt;strong&gt;What you'll actually do:&lt;/strong&gt;&lt;/p&gt;
    &lt;ul&gt;&lt;li&gt;Build LLM tools and improve automation monitoring.&lt;/li&gt;&lt;/ul&gt;
    &lt;p&gt;&lt;strong&gt;Added Value:&lt;/strong&gt;&lt;/p&gt;
    &lt;ul&gt;&lt;li&gt;Experience with LangChain or LangGraph.&lt;/li&gt;&lt;/ul&gt;
    &lt;p&gt;Hybrid work policy applies.&lt;/p&gt;
    """
    return {
        "id": 12345,
        "title": "AI Workflow Engineer",
        "company_name": "Example Company",
        "location": {"name": "Seoul, South Korea"},
        "absolute_url": "https://job-boards.greenhouse.io/example/jobs/12345",
        "updated_at": "2026-09-13T00:00:00Z",
        "content": content,
    }


class FakeResponse:
    def __init__(
        self,
        document: dict,
        *,
        url: str = "https://boards-api.greenhouse.io/v1/boards/example/jobs/12345",
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        self.payload = json.dumps(document).encode("utf-8")
        self.url = url
        self.status = 200
        self.headers = Message()
        self.headers["Content-Type"] = content_type
        self.headers["Content-Length"] = str(len(self.payload))

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        return self.payload if size < 0 else self.payload[:size]


class GreenhouseIngestionTest(unittest.TestCase):
    def test_fetches_only_allowed_public_job_endpoint(self) -> None:
        response = FakeResponse(_example_job())

        with patch(
            "career_agent.ingestion.greenhouse.urlopen", return_value=response
        ) as mocked_open:
            actual = fetch_greenhouse_job("example", "12345")

        self.assertEqual(12345, actual["id"])
        request = mocked_open.call_args.args[0]
        self.assertEqual("GET", request.get_method())
        self.assertEqual(
            "career-agent-personal-mvp/0.1", request.get_header("User-agent")
        )

    def test_rejects_invalid_board_before_network_request(self) -> None:
        with patch("career_agent.ingestion.greenhouse.urlopen") as mocked_open:
            with self.assertRaisesRegex(GreenhouseJobError, "board_token"):
                fetch_greenhouse_job("../../other", "12345")

        mocked_open.assert_not_called()

    def test_rejects_redirect_outside_exact_api_endpoint(self) -> None:
        response = FakeResponse(
            _example_job(), url="https://example.com/v1/boards/example/jobs/12345"
        )
        with patch("career_agent.ingestion.greenhouse.urlopen", return_value=response):
            with self.assertRaisesRegex(GreenhouseJobError, "응답 URL"):
                fetch_greenhouse_job("example", "12345")

    def test_fetches_public_board_job_list_without_content_query(self) -> None:
        response = FakeResponse(
            {"jobs": [_example_job()]},
            url="https://boards-api.greenhouse.io/v1/boards/example/jobs",
        )

        with patch(
            "career_agent.ingestion.greenhouse.urlopen", return_value=response
        ) as mocked_open:
            actual = fetch_greenhouse_jobs("example")

        self.assertEqual([12345], [job["id"] for job in actual])
        request = mocked_open.call_args.args[0]
        self.assertEqual(
            "https://boards-api.greenhouse.io/v1/boards/example/jobs",
            request.full_url,
        )
        self.assertNotIn("content=true", request.full_url)

    def test_maps_explicit_sections_without_inferring_full_time(self) -> None:
        actual = build_greenhouse_job_posting(
            _example_job(), board_token="example", collected_at=date(2026, 9, 13)
        )["job_posting"]

        self.assertEqual("greenhouse-example-12345", actual["identity"]["posting_id"])
        self.assertEqual("Build a small AI workflow from prototype to operation.", actual["role"]["summary"])
        self.assertEqual(1, len(actual["responsibilities"]))
        self.assertEqual(
            ["software engineering experience", "Python", "LLM API"],
            [item["name"] for item in actual["requirements"]],
        )
        self.assertEqual(
            ["LangChain / LangGraph"],
            [item["name"] for item in actual["preferred_qualifications"]],
        )
        self.assertEqual(3, actual["experience"]["minimum_years"])
        self.assertEqual("unknown", actual["employment"]["type"])
        self.assertEqual("서울", actual["location"]["region"])
        self.assertEqual("hybrid", actual["location"]["remote"])
        self.assertNotIn("3+ years", actual["raw_text"])

    def test_marks_internship_only_when_title_is_explicit(self) -> None:
        job = _example_job()
        job["title"] = "AI Engineer Intern"

        actual = build_greenhouse_job_posting(job, board_token="example")["job_posting"]

        self.assertEqual("internship", actual["employment"]["type"])
        self.assertEqual("intern", actual["role"]["seniority"])


if __name__ == "__main__":
    unittest.main()
