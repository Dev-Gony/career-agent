from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.discovery import (  # noqa: E402
    DiscoveryStoreError,
    merge_discovery_records,
)


class DiscoveryStoreTest(unittest.TestCase):
    def setUp(self) -> None:
        self.record = json.loads(
            (REPOSITORY_ROOT / "data/job_discovery.example.json").read_text(
                encoding="utf-8"
            )
        )["job_discovery"]

    def test_deduplicates_same_record_across_runs(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "discoveries.json"

            first_result = merge_discovery_records([self.record], store_path)
            second_result = merge_discovery_records([self.record], store_path)
            stored = json.loads(store_path.read_text(encoding="utf-8"))

            self.assertEqual(1, len(first_result["new_records"]))
            self.assertEqual([], first_result["duplicate_keys"])
            self.assertEqual(1, first_result["total_records"])
            self.assertEqual([], second_result["new_records"])
            self.assertEqual(
                ["incruit:0000000000000"], second_result["duplicate_keys"]
            )
            self.assertEqual(1, second_result["total_records"])
            self.assertEqual(1, len(stored["records"]))

    def test_does_not_overwrite_invalid_store(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            store_path = Path(directory) / "discoveries.json"
            original_text = "invalid json"
            store_path.write_text(original_text, encoding="utf-8")

            with self.assertRaisesRegex(DiscoveryStoreError, "읽을 수 없음"):
                merge_discovery_records([self.record], store_path)

            self.assertEqual(original_text, store_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
