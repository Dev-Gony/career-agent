from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import PROFILE_DRAFT_ACTION  # noqa: E402
from career_agent.profile_input import (  # noqa: E402
    build_profile_document_import,
    load_profile_analysis_draft,
    save_profile_document_import,
)
from scripts import run_slack_socket  # noqa: E402


EXTRACTED_AT = datetime(2026, 9, 22, 15, tzinfo=timezone.utc)


class SlackLocalProfileAnalysisFlowTest(unittest.TestCase):
    def test_attachment_creates_reusable_local_draft_for_existing_action(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "resume.md"
            source.write_text(
                "## 경력\n"
                "- QA Engineer로 2022년부터 API 테스트 자동화를 수행했습니다.\n"
                "## 성과\n"
                "- 회귀 테스트 시간을 40% 단축했습니다.\n"
                "## 기술\n"
                "- Python으로 테스트 데이터 검증 도구를 개발했습니다.\n",
                encoding="utf-8",
            )
            manifest, content = build_profile_document_import(
                source,
                document_kind="resume",
                imported_at=EXTRACTED_AT,
            )
            save_profile_document_import(manifest, content, root / "documents")
            document_id = manifest["profile_document"]["document_id"]
            replacements = {
                "DEFAULT_PROFILE_DOCUMENT_DIRECTORY": root / "documents",
                "DEFAULT_PROFILE_EXTRACTION_DIRECTORY": root / "extractions",
                "DEFAULT_PROFILE_EVIDENCE_DIRECTORY": root / "evidence",
                "DEFAULT_PROFILE_ANALYSIS_DRAFT_DIRECTORY": root / "drafts",
                "DEFAULT_PROFILE_ACTIVATION_DIRECTORY": root / "activations",
                "DEFAULT_PROFILE_ANALYSIS_APPLICATION_DIRECTORY": root / "applications",
                "DEFAULT_PROFILE": REPOSITORY_ROOT / "data/user_profile.example.json",
            }
            with patch.multiple(run_slack_socket, **replacements):
                first = run_slack_socket._extract_imported_profile_document(
                    {"document_id": document_id},
                    EXTRACTED_AT,
                )
                second = run_slack_socket._extract_imported_profile_document(
                    {"document_id": document_id},
                    EXTRACTED_AT,
                )
                summary_result = run_slack_socket._run_slack_action(
                    PROFILE_DRAFT_ACTION,
                    {},
                )

            draft_path = next((root / "drafts").glob("*.json"))
            draft = load_profile_analysis_draft(draft_path.stem, root / "drafts")

        self.assertEqual("extracted", first["status"])
        self.assertEqual("created", first["analysis_draft_status"])
        self.assertEqual("reused", second["status"])
        self.assertEqual("reused", second["analysis_draft_status"])
        self.assertEqual("local", draft["analysis_source"]["data_boundary"])
        self.assertFalse(draft["metadata"]["profile_updated"])
        self.assertIn("프로필 분석 초안이 준비되었습니다", summary_result["public_message"])
        self.assertNotIn("QA Engineer", summary_result["public_message"])


if __name__ == "__main__":
    unittest.main()
