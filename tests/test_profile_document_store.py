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

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_document_import,
    save_profile_document_import,
)


IMPORTED_AT = datetime(2026, 9, 14, 14, tzinfo=timezone.utc)


class ProfileDocumentStoreTest(unittest.TestCase):
    def test_stores_text_document_without_content_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.txt"
            source.write_text("Python automation experience", encoding="utf-8")
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=IMPORTED_AT,
            )
            manifest_path, created = save_profile_document_import(
                manifest, content, root / "private"
            )
            actual = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertTrue(created)
            self.assertEqual(
                "stored_unparsed",
                actual["profile_document"]["processing_status"],
            )
            self.assertFalse(actual["metadata"]["contains_document_content"])
            self.assertFalse(actual["metadata"]["git_tracking_allowed"])
            self.assertNotIn(str(source.parent), manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(
                content,
                (manifest_path.parent / "original.txt").read_bytes(),
            )

    def test_reuses_identical_document_without_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "portfolio.md"
            source.write_text("# Portfolio", encoding="utf-8")
            first, content = build_profile_document_import(
                source,
                document_kind="portfolio",
                imported_at=IMPORTED_AT,
            )
            first_path, first_created = save_profile_document_import(
                first, content, root / "private"
            )
            second, second_content = build_profile_document_import(
                source,
                document_kind="portfolio",
                imported_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
            )
            second_path, second_created = save_profile_document_import(
                second, second_content, root / "private"
            )

            self.assertTrue(first_created)
            self.assertFalse(second_created)
            self.assertEqual(first_path, second_path)
            stored = json.loads(second_path.read_text(encoding="utf-8"))
            self.assertEqual(
                IMPORTED_AT.isoformat(timespec="microseconds"),
                stored["profile_document"]["imported_at"],
            )

    def test_accepts_minimal_valid_docx_container(self) -> None:
        document = BytesIO()
        with ZipFile(document, "w") as archive:
            archive.writestr("[Content_Types].xml", "<Types />")
            archive.writestr("word/document.xml", "<document />")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "career.docx"
            source.write_bytes(document.getvalue())

            manifest, _ = build_profile_document_import(
                source,
                document_kind="career_history",
                imported_at=IMPORTED_AT,
            )

        self.assertEqual("docx", manifest["profile_document"]["document_format"])

    def test_rejects_pdf_extension_without_pdf_signature(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resume.pdf"
            source.write_bytes(b"not a pdf")

            with self.assertRaisesRegex(ProfileDocumentError, "PDF 서명"):
                build_profile_document_import(
                    source,
                    document_kind="resume",
                    imported_at=IMPORTED_AT,
                )

    def test_rejects_unsupported_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resume.exe"
            source.write_bytes(b"content")

            with self.assertRaisesRegex(ProfileDocumentError, "허용 문서 확장자"):
                build_profile_document_import(
                    source,
                    document_kind="resume",
                    imported_at=IMPORTED_AT,
                )

    def test_rejects_document_larger_than_limit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resume.txt"
            source.write_bytes(b"12345")

            with self.assertRaisesRegex(ProfileDocumentError, "4바이트"):
                build_profile_document_import(
                    source,
                    document_kind="resume",
                    imported_at=IMPORTED_AT,
                    max_bytes=4,
                )

    def test_rejects_timestamp_without_timezone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "resume.txt"
            source.write_text("content", encoding="utf-8")

            with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
                build_profile_document_import(
                    source,
                    document_kind="resume",
                    imported_at=datetime(2026, 9, 14),
                )


if __name__ == "__main__":
    unittest.main()
