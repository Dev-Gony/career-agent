from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from zipfile import ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_slack_profile_document_reference,
    import_slack_profile_document,
)


IMPORTED_AT = datetime(2026, 9, 15, 8, tzinfo=timezone.utc)
BOT_TOKEN = "xoxb-test-token-without-secret-value"


class _Response:
    def __init__(
        self,
        content: bytes,
        *,
        content_type: str,
        content_encoding: str = "identity",
    ) -> None:
        self.status = 200
        self.headers = {
            "Content-Type": content_type,
            "Content-Encoding": content_encoding,
        }
        self._content = BytesIO(content)

    def read(self, size: int = -1) -> bytes:
        return self._content.read(size)

    def __enter__(self) -> "_Response":
        return self

    def __exit__(self, *_args) -> None:
        return None


def _docx_content() -> bytes:
    document = BytesIO()
    with ZipFile(document, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", "<document />")
    return document.getvalue()


def _file_object(content: bytes, **changes) -> dict:
    file_object = {
        "id": "F01234567",
        "name": "resume.docx",
        "mimetype": (
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
        "size": len(content),
        "mode": "hosted",
        "is_external": False,
        "file_access": "visible",
        "url_private_download": (
            "https://files.slack.com/files-pri/example/download/resume.docx"
        ),
    }
    file_object.update(changes)
    return file_object


def _info_response(file_object: dict) -> _Response:
    payload = json.dumps({"ok": True, "file": file_object}).encode("utf-8")
    return _Response(payload, content_type="application/json; charset=utf-8")


class SlackFilesTest(unittest.TestCase):
    def test_downloads_authenticated_docx_into_private_store(self) -> None:
        content = _docx_content()
        file_object = _file_object(content)
        reference = build_slack_profile_document_reference(file_object)
        requests: list = []
        responses = [
            _info_response(file_object),
            _Response(
                content,
                content_type=file_object["mimetype"],
            ),
        ]

        def open_url(request, *, timeout):
            requests.append((request, timeout))
            return responses.pop(0)

        with tempfile.TemporaryDirectory() as directory:
            result = import_slack_profile_document(
                reference,
                bot_token=BOT_TOKEN,
                document_kind="other",
                imported_at=IMPORTED_AT,
                directory=directory,
                open_url=open_url,
            )
            manifest = json.loads(result["manifest_path"].read_text(encoding="utf-8"))
            stored_content = (
                result["manifest_path"].parent / "original.docx"
            ).read_bytes()

        self.assertEqual("stored", result["status"])
        self.assertEqual(content, stored_content)
        self.assertEqual(
            "slack_attachment",
            manifest["profile_document"]["source_type"],
        )
        self.assertEqual(
            "resume.docx",
            manifest["profile_document"]["original_filename"],
        )
        serialized = json.dumps(manifest)
        self.assertNotIn("files.slack.com", serialized)
        self.assertNotIn(BOT_TOKEN, serialized)
        self.assertEqual("POST", requests[0][0].get_method())
        self.assertEqual("GET", requests[1][0].get_method())
        self.assertTrue(
            all(
                request.get_header("Authorization") == f"Bearer {BOT_TOKEN}"
                for request, _timeout in requests
            )
        )
        self.assertTrue(all(timeout == 15.0 for _request, timeout in requests))

    def test_rejects_non_slack_download_url_before_sending_token(self) -> None:
        content = _docx_content()
        initial = _file_object(content)
        reference = build_slack_profile_document_reference(initial)
        malicious = _file_object(
            content,
            url_private_download="https://example.com/private/resume.docx",
        )
        requests: list = []

        def open_url(request, *, timeout):
            requests.append((request, timeout))
            if len(requests) > 1:
                raise AssertionError("외부 호스트에 다운로드 요청을 보내면 안 됨")
            return _info_response(malicious)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SlackEventError, "Slack이 관리"):
                import_slack_profile_document(
                    reference,
                    bot_token=BOT_TOKEN,
                    document_kind="other",
                    imported_at=IMPORTED_AT,
                    directory=directory,
                    open_url=open_url,
                )

        self.assertEqual(1, len(requests))

    def test_reports_missing_files_read_scope_without_downloading(self) -> None:
        content = _docx_content()
        reference = build_slack_profile_document_reference(_file_object(content))
        response = _Response(
            json.dumps({"ok": False, "error": "missing_scope"}).encode("utf-8"),
            content_type="application/json",
        )

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SlackEventError, "missing_scope"):
                import_slack_profile_document(
                    reference,
                    bot_token=BOT_TOKEN,
                    document_kind="other",
                    imported_at=IMPORTED_AT,
                    directory=directory,
                    open_url=lambda _request, *, timeout: response,
                )

    def test_rejects_download_whose_size_changed(self) -> None:
        content = _docx_content()
        file_object = _file_object(content)
        reference = build_slack_profile_document_reference(file_object)
        responses = [
            _info_response(file_object),
            _Response(content + b"changed", content_type=file_object["mimetype"]),
        ]

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(SlackEventError, "크기"):
                import_slack_profile_document(
                    reference,
                    bot_token=BOT_TOKEN,
                    document_kind="other",
                    imported_at=IMPORTED_AT,
                    directory=directory,
                    open_url=lambda _request, *, timeout: responses.pop(0),
                )


if __name__ == "__main__":
    unittest.main()
