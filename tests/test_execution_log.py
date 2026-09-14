from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.execution import (  # noqa: E402
    ExecutionLogError,
    build_greenhouse_execution_record,
    save_execution_record,
)


class ExecutionLogTest(unittest.TestCase):
    def setUp(self) -> None:
        self.executed_at = datetime.fromisoformat("2026-09-14T16:00:00.123456+09:00")
        self.discovery = {
            "boards_requested": 2,
            "boards_succeeded": 1,
            "boards_failed": 1,
            "fetched_records": 3,
            "board_attempts": [
                {
                    "board_token": "one",
                    "status": "failed",
                    "error": "합성 실패",
                },
                {
                    "board_token": "two",
                    "status": "succeeded",
                    "fetched_records": 3,
                },
            ],
            "board_results": [
                {"current_records": [{"content": "저장하면 안 되는 공고 내용"}]}
            ],
        }

    def test_builds_minimal_reused_execution_without_source_documents(self) -> None:
        actual = build_greenhouse_execution_record(
            executed_at=self.executed_at,
            status="reused",
            discovery=self.discovery,
            selection={"board_token": "two", "external_job_id": "200"},
            analysis_id="analysis-existing",
            analysis_filename="analysis-existing.json",
        )

        self.assertEqual("reused", actual["execution"]["status"])
        self.assertEqual(2, len(actual["discovery"]["board_attempts"]))
        self.assertNotIn("board_results", actual["discovery"])
        self.assertTrue(actual["analysis_reference"]["reused"])
        self.assertFalse(actual["metadata"]["contains_profile_content"])
        self.assertNotIn("저장하면 안 되는 공고 내용", json.dumps(actual))

    def test_saves_execution_record_without_overwrite(self) -> None:
        record = build_greenhouse_execution_record(
            executed_at=self.executed_at,
            status="no_high_candidate",
            discovery=self.discovery,
        )
        with tempfile.TemporaryDirectory() as directory:
            saved_path = save_execution_record(record, directory)

            self.assertTrue(saved_path.is_file())
            with self.assertRaisesRegex(ExecutionLogError, "이미 존재"):
                save_execution_record(record, directory)

    def test_failed_execution_requires_error(self) -> None:
        with self.assertRaisesRegex(ExecutionLogError, "error 문자열"):
            build_greenhouse_execution_record(
                executed_at=self.executed_at,
                status="failed",
            )


if __name__ == "__main__":
    unittest.main()
