from __future__ import annotations

from contextlib import redirect_stderr
from io import BytesIO, StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import URLError


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    OpenAIResponsesProfileAnalysisProvider,
    ProfileDocumentError,
    load_openai_api_key,
    profile_analysis_response_json_schema,
)
from scripts.build_openai_profile_analysis_draft import main  # noqa: E402


API_KEY = "sk-test-key-0123456789abcdef"


def _request() -> dict:
    return {
        "contract_version": "0.1",
        "candidates": [
            {
                "candidate_id": "candidate-001",
                "profile_section": "skills",
                "text": "Python으로 API 테스트 도구를 개발했습니다.",
            }
        ],
    }


def _structured_output() -> dict:
    return {
        "career_evidence": [],
        "achievement_evidence": [],
        "technology_evidence": [
            {
                "technology_name": "Python",
                "usage_evidence": "Python으로 API 테스트 도구를 개발했습니다.",
                "proficiency_status": "unconfirmed",
                "candidate_ids": ["candidate-001"],
                "confidence": "high",
            }
        ],
        "unknowns": [],
    }


def _api_payload(output: dict | None = None) -> bytes:
    return json.dumps(
        {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {
                            "type": "output_text",
                            "text": json.dumps(
                                output or _structured_output(),
                                ensure_ascii=False,
                            ),
                        }
                    ],
                }
            ],
        },
        ensure_ascii=False,
    ).encode("utf-8")


class _Response:
    def __init__(self, body: bytes, *, status: int = 200) -> None:
        self._body = BytesIO(body)
        self.status = status
        self.headers = {"Content-Type": "application/json"}

    def read(self, size: int = -1) -> bytes:
        return self._body.read(size)

    def getcode(self) -> int:
        return self.status

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None


class OpenAIProfileAnalysisTest(unittest.TestCase):
    def test_sends_only_minimal_candidates_with_strict_stateless_format(self) -> None:
        calls = []

        def open_url(request, *, timeout):
            calls.append((request, timeout))
            return _Response(_api_payload())

        provider = OpenAIResponsesProfileAnalysisProvider(
            API_KEY,
            open_url=open_url,
        )
        result = provider.analyze(
            _request(),
            profile_analysis_response_json_schema(),
        )

        self.assertEqual(_structured_output(), result)
        self.assertEqual(1, len(calls))
        request, timeout = calls[0]
        self.assertEqual("https://api.openai.com/v1/responses", request.full_url)
        self.assertEqual(30.0, timeout)
        self.assertEqual(f"Bearer {API_KEY}", request.get_header("Authorization"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual("gpt-5.6-luna", body["model"])
        self.assertIs(False, body["store"])
        self.assertEqual({"effort": "low"}, body["reasoning"])
        self.assertNotIn("tools", body)
        self.assertEqual("json_schema", body["text"]["format"]["type"])
        self.assertIs(True, body["text"]["format"]["strict"])
        sent_candidates = json.loads(body["input"])["candidates"]
        self.assertEqual(_request()["candidates"], sent_candidates)
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(API_KEY, serialized)
        self.assertNotIn("document_id", serialized)
        self.assertNotIn("extraction_id", serialized)

    def test_rejects_extra_request_fields_before_network_call(self) -> None:
        calls = []
        provider = OpenAIResponsesProfileAnalysisProvider(
            API_KEY,
            open_url=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        request = _request()
        request["document_id"] = "private-document"

        with self.assertRaisesRegex(ProfileDocumentError, "허용되지 않은 필드"):
            provider.analyze(request, profile_analysis_response_json_schema())

        self.assertEqual([], calls)

    def test_sanitizes_network_failure_without_key_or_candidate_text(self) -> None:
        def fail_request(*_args, **_kwargs):
            raise URLError(f"{API_KEY} Python으로 API 테스트")

        provider = OpenAIResponsesProfileAnalysisProvider(
            API_KEY,
            open_url=fail_request,
        )
        with self.assertRaises(ProfileDocumentError) as raised:
            provider.analyze(_request(), profile_analysis_response_json_schema())

        message = str(raised.exception)
        self.assertIn("URLError", message)
        self.assertNotIn(API_KEY, message)
        self.assertNotIn("Python", message)

    def test_loads_key_from_environment_or_private_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "SLACK_BOT_TOKEN=xoxb-ignored\n"
                f"OPENAI_API_KEY={API_KEY}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                API_KEY,
                load_openai_api_key(env_file, environment={}),
            )
            environment_key = "sk-environment-key-0123456789"
            self.assertEqual(
                environment_key,
                load_openai_api_key(
                    env_file,
                    environment={"OPENAI_API_KEY": environment_key},
                ),
            )

    def test_cli_stops_before_key_or_network_without_explicit_approval(self) -> None:
        error_output = StringIO()
        with patch(
            "sys.argv",
            [
                "build_openai_profile_analysis_draft.py",
                "--extraction-id",
                "profile-text-extraction-0123456789abcdef01234567",
                "--env-file",
                "missing.env",
            ],
        ), redirect_stderr(error_output):
            result = main()

        self.assertEqual(2, result)
        self.assertIn("외부 전송 승인이 필요", error_output.getvalue())
        self.assertNotIn("OPENAI_API_KEY가", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()
