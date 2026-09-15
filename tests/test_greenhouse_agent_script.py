from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))

from scripts.run_greenhouse_agent import _save_discovery_snapshot  # noqa: E402


class GreenhouseAgentScriptTest(unittest.TestCase):
    def test_saves_discovery_without_profile_or_analysis_content(self) -> None:
        result = {
            "status": "reused",
            "discovery": {
                "executed_at": "2026-09-15T17:43:23+09:00",
                "board_results": [],
            },
            "selection": {"external_job_id": "100"},
            "analysis": {"private": "must not be copied"},
            "reuse": {"analysis_id": "existing"},
        }
        executed_at = datetime.fromisoformat("2026-09-15T17:43:23+09:00")

        with tempfile.TemporaryDirectory() as directory:
            path = _save_discovery_snapshot(
                result,
                Path(directory),
                executed_at=executed_at,
            )
            document = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("greenhouse_discovery_snapshot", document["workflow"])
        self.assertEqual(result["discovery"], document["discovery"])
        self.assertIsNone(document["analysis"])
        self.assertFalse(document["metadata"]["contains_profile_content"])
        self.assertFalse(
            document["metadata"]["contains_job_description_content"]
        )
        self.assertNotIn("private", json.dumps(document))


if __name__ == "__main__":
    unittest.main()
