from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
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
    GeminiDevelopmentProfileAnalysisProvider,
    ProfileDocumentError,
    build_profile_analysis_request,
    build_profile_document_import,
    build_profile_text_extraction,
    load_gemini_api_key,
    profile_analysis_response_json_schema,
)
from scripts.build_gemini_synthetic_profile_analysis_draft import (  # noqa: E402
    PUBLIC_SYNTHETIC_DOCUMENT,
    _build_parser,
    main,
)


API_KEY = "AIza-synthetic-development-key-0123456789"


def _request() -> dict:
    now = datetime.now(timezone.utc)
    manifest, content = build_profile_document_import(
        REPOSITORY_ROOT / "data/profile_document.example.md",
        document_kind="resume",
        imported_at=now,
    )
    extraction = build_profile_text_extraction(
        manifest,
        content,
        extracted_at=now,
    )
    return build_profile_analysis_request(extraction)


def _structured_output() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / "data/profile_analysis_response.example.json").read_text(
            encoding="utf-8"
        )
    )


def _api_payload(output: dict | None = None) -> bytes:
    return json.dumps(
        {
            "candidates": [
                {
                    "content": {
                        "role": "model",
                        "parts": [
                            {
                                "text": json.dumps(
                                    output or _structured_output(),
                                    ensure_ascii=False,
                                )
                            }
                        ],
                    },
                    "finishReason": "STOP",
                }
            ]
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


class GeminiProfileAnalysisTest(unittest.TestCase):
    def test_sends_only_minimal_candidates_with_structured_output(self) -> None:
        calls = []

        def open_url(request, *, timeout):
            calls.append((request, timeout))
            return _Response(_api_payload())

        provider = GeminiDevelopmentProfileAnalysisProvider(
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
        self.assertEqual(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-3.8-flash:generateContent",
            request.full_url,
        )
        self.assertEqual(30.0, timeout)
        self.assertEqual(API_KEY, request.get_header("X-goog-api-key"))
        body = json.loads(request.data.decode("utf-8"))
        self.assertIs(False, body["store"])
        self.assertNotIn("tools", body)
        self.assertEqual("application/json", body["generationConfig"]["responseMimeType"])
        self.assertEqual(
            {"thinkingLevel": "low"},
            body["generationConfig"]["thinkingConfig"],
        )
        sent_request = json.loads(body["contents"][0]["parts"][0]["text"])
        self.assertEqual(_request(), sent_request)
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertNotIn(API_KEY, serialized)
        self.assertNotIn("document_id", serialized)
        self.assertNotIn("extraction_id", serialized)

    def test_rejects_extra_request_fields_before_network_call(self) -> None:
        calls = []
        provider = GeminiDevelopmentProfileAnalysisProvider(
            API_KEY,
            open_url=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        request = _request()
        request["document_id"] = "private-document"

        with self.assertRaisesRegex(ProfileDocumentError, "허용되지 않은 필드"):
            provider.analyze(request, profile_analysis_response_json_schema())

        self.assertEqual([], calls)

    def test_rejects_non_fixture_candidate_before_network_call(self) -> None:
        calls = []
        provider = GeminiDevelopmentProfileAnalysisProvider(
            API_KEY,
            open_url=lambda *args, **kwargs: calls.append((args, kwargs)),
        )
        request = _request()
        request["candidates"][0]["text"] = "실제 사용자 이력서 문장"

        with self.assertRaisesRegex(ProfileDocumentError, "공개 합성 예제만"):
            provider.analyze(request, profile_analysis_response_json_schema())

        self.assertEqual([], calls)

    def test_sanitizes_network_failure_without_key_or_candidate_text(self) -> None:
        def fail_request(*_args, **_kwargs):
            raise URLError(f"{API_KEY} Python으로 API 테스트")

        provider = GeminiDevelopmentProfileAnalysisProvider(
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
                f"GEMINI_API_KEY={API_KEY}\n",
                encoding="utf-8",
            )
            self.assertEqual(
                API_KEY,
                load_gemini_api_key(env_file, environment={}),
            )
            environment_key = "AIza-environment-key-01234567890123456789"
            self.assertEqual(
                environment_key,
                load_gemini_api_key(
                    env_file,
                    environment={"GEMINI_API_KEY": environment_key},
                ),
            )

    def test_cli_has_no_private_input_selection_and_stops_without_confirmation(self) -> None:
        parser_destinations = {action.dest for action in _build_parser()._actions}
        self.assertNotIn("source", parser_destinations)
        self.assertNotIn("source_path", parser_destinations)
        self.assertNotIn("extraction_id", parser_destinations)
        self.assertEqual(
            REPOSITORY_ROOT / "data/profile_document.example.md",
            PUBLIC_SYNTHETIC_DOCUMENT,
        )

        error_output = StringIO()
        with patch(
            "sys.argv",
            [
                "build_gemini_synthetic_profile_analysis_draft.py",
                "--env-file",
                "missing.env",
            ],
        ), redirect_stderr(error_output):
            result = main()

        self.assertEqual(2, result)
        self.assertIn("공개 합성 예제 전송 확인", error_output.getvalue())
        self.assertNotIn("GEMINI_API_KEY가", error_output.getvalue())

    def test_cli_builds_draft_from_only_the_fixed_public_fixture(self) -> None:
        response = json.loads(
            (REPOSITORY_ROOT / "data/profile_analysis_response.example.json").read_text(
                encoding="utf-8"
            )
        )

        class SyntheticProvider:
            provider_name = "google-gemini-development"
            model_name = "gemini-3.8-flash"
            sends_data_externally = True

            def __init__(self, api_key: str) -> None:
                self.api_key = api_key

            def analyze(self, request, response_schema):
                self.request = request
                self.response_schema = response_schema
                return response

        with tempfile.TemporaryDirectory() as directory:
            output = StringIO()
            draft_directory = Path(directory) / "drafts"
            with patch(
                "sys.argv",
                [
                    "build_gemini_synthetic_profile_analysis_draft.py",
                    "--confirm-public-synthetic-data",
                    "--draft-directory",
                    str(draft_directory),
                ],
            ), patch(
                "scripts.build_gemini_synthetic_profile_analysis_draft."
                "load_gemini_api_key",
                return_value=API_KEY,
            ), patch(
                "scripts.build_gemini_synthetic_profile_analysis_draft."
                "GeminiDevelopmentProfileAnalysisProvider",
                SyntheticProvider,
            ), redirect_stdout(output):
                result = main()

            self.assertEqual(0, result)
            self.assertIn("공개 합성 예제 결과", output.getvalue())
            saved = list(draft_directory.glob("*.json"))
            self.assertEqual(1, len(saved))
            draft = json.loads(saved[0].read_text(encoding="utf-8"))
            self.assertEqual(
                "needs_review",
                draft["profile_analysis_draft"]["status"],
            )
            self.assertFalse(draft["metadata"]["profile_updated"])


if __name__ == "__main__":
    unittest.main()
