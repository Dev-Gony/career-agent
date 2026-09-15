from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape
from zipfile import ZipFile


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_document_import,
    build_profile_text_extraction,
    load_profile_document_import,
    save_profile_document_import,
    save_profile_text_extraction,
)


IMPORTED_AT = datetime(2026, 9, 14, 14, tzinfo=timezone.utc)
EXTRACTED_AT = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)


def _text_manifest(content: str) -> tuple[dict, bytes]:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.md"
        source.write_text(content, encoding="utf-8")
        return build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=IMPORTED_AT,
        )


def _docx_manifest(
    paragraphs: list[list[str]] | None = None,
    *,
    document_xml: bytes | None = None,
) -> tuple[dict, bytes]:
    if document_xml is None:
        paragraph_xml = "".join(
            "<w:p>"
            + "".join(f"<w:r><w:t>{escape(run)}</w:t></w:r>" for run in runs)
            + "</w:p>"
            for runs in paragraphs or []
        )
        document_xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/'
            'wordprocessingml/2006/main"><w:body>'
            f"{paragraph_xml}</w:body></w:document>"
        ).encode("utf-8")
    document = BytesIO()
    with ZipFile(document, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types />")
        archive.writestr("word/document.xml", document_xml)
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.docx"
        source.write_bytes(document.getvalue())
        return build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=IMPORTED_AT,
        )


class ProfileTextExtractionTest(unittest.TestCase):
    def test_extracts_heading_sections_with_line_evidence(self) -> None:
        manifest, content = _text_manifest(
            "홍길동\n"
            "## 경력\n"
            "- 웹 서비스 유지보수\n"
            "## 기술: Python, GitHub Actions\n"
            "## 프로젝트\n"
            "1. 기술 뉴스 자동화\n"
        )

        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )

        self.assertEqual(3, extraction["summary"]["candidate_count"])
        self.assertEqual(
            ["career_history", "skills", "projects"],
            [item["profile_section"] for item in extraction["candidates"]],
        )
        self.assertEqual("웹 서비스 유지보수", extraction["candidates"][0]["text"])
        self.assertEqual(3, extraction["candidates"][0]["source_evidence"]["line_start"])
        self.assertEqual("needs_review", extraction["candidates"][0]["status"])
        self.assertEqual(1, extraction["summary"]["unclassified_nonempty_line_count"])
        self.assertFalse(extraction["metadata"]["profile_updated"])

    def test_omits_contact_lines_without_storing_values(self) -> None:
        manifest, content = _text_manifest(
            "## 경력\n"
            "- API 개발\n"
            "이메일: private@example.com\n"
            "전화: 010-1234-5678\n"
            "주민번호: 900101-1234567\n"
        )

        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )
        serialized = json.dumps(extraction, ensure_ascii=False)

        self.assertEqual(1, extraction["summary"]["candidate_count"])
        self.assertEqual(3, extraction["summary"]["omitted_sensitive_line_count"])
        self.assertNotIn("private@example.com", serialized)
        self.assertNotIn("010-1234-5678", serialized)
        self.assertNotIn("900101-1234567", serialized)

    def test_sensitive_heading_stops_previous_section(self) -> None:
        manifest, content = _text_manifest(
            "## 기술\n"
            "- Python\n"
            "## 연락처\n"
            "서울시 비공개 주소\n"
        )

        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )

        self.assertEqual(["Python"], [item["text"] for item in extraction["candidates"]])
        self.assertNotIn(
            "서울시 비공개 주소",
            json.dumps(extraction, ensure_ascii=False),
        )

    def test_unrecognized_text_is_not_inferred_as_profile_fact(self) -> None:
        manifest, content = _text_manifest("Python을 사용했습니다.\n자동화를 좋아합니다.\n")

        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )

        self.assertEqual([], extraction["candidates"])
        self.assertEqual(2, extraction["summary"]["unclassified_nonempty_line_count"])

    def test_extracts_docx_paragraphs_and_combines_text_runs(self) -> None:
        manifest, content = _docx_manifest(
            [
                ["홍길동"],
                ["경력"],
                ["API ", "자동화 운영"],
                ["연락처"],
                ["private@example.com"],
                ["기술"],
                ["Python"],
            ]
        )

        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )

        self.assertEqual("heading_based_docx", extraction["profile_extraction"]["method"])
        self.assertEqual(
            ["API 자동화 운영", "Python"],
            [item["text"] for item in extraction["candidates"]],
        )
        self.assertEqual(
            [3, 7],
            [
                item["source_evidence"]["line_start"]
                for item in extraction["candidates"]
            ],
        )
        self.assertEqual(1, extraction["summary"]["omitted_sensitive_line_count"])

    def test_recognizes_career_summary_heading_from_resume(self) -> None:
        manifest, content = _docx_manifest(
            [
                ["경력 요약"],
                ["운영 업무를 자동화했습니다."],
                ["경력"],
                ["품질 개선 업무를 수행했습니다."],
            ]
        )

        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )

        self.assertEqual(2, extraction["summary"]["candidate_count"])
        self.assertEqual(
            {"career_history": 2},
            extraction["summary"]["section_counts"],
        )
        self.assertEqual(
            "0.3",
            extraction["profile_extraction"]["rules_version"],
        )

    def test_rejects_docx_document_xml_with_dtd(self) -> None:
        manifest, content = _docx_manifest(
            document_xml=(
                b'<?xml version="1.0"?>'
                b'<!DOCTYPE document [<!ENTITY private "value">]>'
                b'<w:document xmlns:w="http://schemas.openxmlformats.org/'
                b'wordprocessingml/2006/main"><w:body /></w:document>'
            )
        )

        with self.assertRaisesRegex(ProfileDocumentError, "DTD 또는 ENTITY"):
            build_profile_text_extraction(
                manifest,
                content,
                extracted_at=EXTRACTED_AT,
            )

    def test_rejects_malformed_docx_document_xml(self) -> None:
        manifest, content = _docx_manifest(document_xml=b"<not-closed>")

        with self.assertRaisesRegex(ProfileDocumentError, "해석할 수 없음"):
            build_profile_text_extraction(
                manifest,
                content,
                extracted_at=EXTRACTED_AT,
            )

    def test_rejects_binary_document_until_extractor_is_added(self) -> None:
        manifest = {
            "profile_document": {
                "document_id": "profile-document-resume-0123456789abcdef0123",
                "document_kind": "resume",
                "document_format": "pdf",
                "content_sha256": "unused",
            },
            "metadata": {"schema_version": "0.1"},
        }

        with self.assertRaisesRegex(ProfileDocumentError, "TXT, Markdown와 DOCX"):
            build_profile_text_extraction(
                manifest,
                b"%PDF-1.7",
                extracted_at=EXTRACTED_AT,
            )

    def test_load_rejects_changed_stored_original(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.txt"
            source.write_text("## 기술\nPython", encoding="utf-8")
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=IMPORTED_AT,
            )
            manifest_path, _ = save_profile_document_import(
                manifest, content, root / "documents"
            )
            (manifest_path.parent / "original.txt").write_text(
                "changed", encoding="utf-8"
            )

            with self.assertRaisesRegex(ProfileDocumentError, "크기가 manifest와 다름"):
                load_profile_document_import(
                    manifest["profile_document"]["document_id"],
                    root / "documents",
                )

    def test_saves_and_reuses_same_document_and_rules(self) -> None:
        manifest, content = _text_manifest("## 기술\n- Python\n")
        first = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )
        second = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=datetime(2026, 9, 15, tzinfo=timezone.utc),
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path, first_created = save_profile_text_extraction(first, directory)
            second_path, second_created = save_profile_text_extraction(second, directory)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_path, second_path)

    def test_rejects_tampered_existing_extraction(self) -> None:
        manifest, content = _text_manifest("## 기술\n- Python\n")
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_text_extraction(extraction, directory)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["candidates"][0]["text"] = "변조된 값"
            path.write_text(
                json.dumps(tampered, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProfileDocumentError, "candidates"):
                save_profile_text_extraction(extraction, directory)


if __name__ == "__main__":
    unittest.main()
