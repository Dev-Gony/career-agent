from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    build_profile_document_import,
    build_profile_text_extraction,
    save_profile_text_extraction,
)
from scripts.build_profile_analysis_draft import main  # noqa: E402


IMPORTED_AT = datetime(2026, 9, 20, 12, tzinfo=timezone.utc)
EXTRACTED_AT = datetime(2026, 9, 20, 12, 5, tzinfo=timezone.utc)


def _response() -> dict:
    return {
        "career_evidence": [],
        "achievement_evidence": [],
        "technology_evidence": [
            {
                "technology_name": "Python",
                "usage_evidence": "Python으로 테스트 자동화 도구를 개발했습니다.",
                "proficiency_status": "unconfirmed",
                "candidate_ids": ["candidate-001"],
                "confidence": "high",
            }
        ],
        "unknowns": [],
    }


class ProfileAnalysisScriptTest(unittest.TestCase):
    def _saved_extraction(self, root: Path) -> tuple[str, Path]:
        source = root / "resume.md"
        source.write_text(
            "## 기술\n- Python으로 테스트 자동화 도구를 개발했습니다.\n",
            encoding="utf-8",
        )
        manifest, content = build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=IMPORTED_AT,
        )
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=EXTRACTED_AT,
        )
        extraction_directory = root / "extractions"
        save_profile_text_extraction(extraction, extraction_directory)
        return extraction["profile_extraction"]["extraction_id"], extraction_directory

    def test_builds_and_saves_local_draft_without_printing_candidate_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extraction_id, extraction_directory = self._saved_extraction(root)
            response_path = root / "response.json"
            response_path.write_text(
                json.dumps(_response(), ensure_ascii=False),
                encoding="utf-8",
            )
            draft_directory = root / "drafts"
            output = StringIO()
            with patch(
                "sys.argv",
                [
                    "build_profile_analysis_draft.py",
                    "--extraction-id",
                    extraction_id,
                    "--response-file",
                    str(response_path),
                    "--extraction-directory",
                    str(extraction_directory),
                    "--draft-directory",
                    str(draft_directory),
                ],
            ), redirect_stdout(output):
                result = main()

            self.assertEqual(0, result)
            self.assertIn("프로필 분석 초안 생성 완료", output.getvalue())
            self.assertNotIn("Python으로 테스트", output.getvalue())
            paths = list(draft_directory.glob("*.json"))
            self.assertEqual(1, len(paths))
            draft = json.loads(paths[0].read_text(encoding="utf-8"))
            self.assertEqual("local", draft["analysis_source"]["data_boundary"])
            self.assertFalse(draft["metadata"]["profile_updated"])

    def test_reports_grounding_failure_without_saving_draft(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            extraction_id, extraction_directory = self._saved_extraction(root)
            response = _response()
            response["technology_evidence"][0]["usage_evidence"] = "Kubernetes 운영"
            response_path = root / "response.json"
            response_path.write_text(
                json.dumps(response, ensure_ascii=False),
                encoding="utf-8",
            )
            draft_directory = root / "drafts"
            error_output = StringIO()
            with patch(
                "sys.argv",
                [
                    "build_profile_analysis_draft.py",
                    "--extraction-id",
                    extraction_id,
                    "--response-file",
                    str(response_path),
                    "--extraction-directory",
                    str(extraction_directory),
                    "--draft-directory",
                    str(draft_directory),
                ],
            ), redirect_stderr(error_output):
                result = main()

            self.assertEqual(1, result)
            self.assertIn("원문 구간", error_output.getvalue())
            self.assertFalse(draft_directory.exists())


if __name__ == "__main__":
    unittest.main()
