from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.config import (  # noqa: E402
    GreenhouseBoardConfigError,
    load_enabled_greenhouse_board,
)


def _document(*boards: dict) -> dict:
    return {"greenhouse_boards": {"boards": list(boards)}}


def _board(token: str = "example", *, enabled: bool = True) -> dict:
    return {
        "board_token": token,
        "company": "Example Company",
        "careers_url": "https://example.com/careers",
        "access_method": "greenhouse_job_board_api",
        "policy_checked_at": "2026-09-14",
        "enabled": enabled,
    }


class GreenhouseBoardConfigTest(unittest.TestCase):
    def test_public_example_loads_sendbird(self) -> None:
        document = json.loads(
            (REPOSITORY_ROOT / "data/greenhouse_boards.example.json").read_text(
                encoding="utf-8"
            )
        )

        actual = load_enabled_greenhouse_board(document)

        self.assertEqual("sendbird", actual["board_token"])

    def test_loads_single_enabled_board(self) -> None:
        actual = load_enabled_greenhouse_board(
            _document(_board("disabled", enabled=False), _board("enabled"))
        )

        self.assertEqual("enabled", actual["board_token"])
        self.assertEqual("2026-09-14", actual["policy_checked_at"].isoformat())

    def test_rejects_multiple_enabled_boards_for_current_mvp(self) -> None:
        with self.assertRaisesRegex(GreenhouseBoardConfigError, "정확히 1개"):
            load_enabled_greenhouse_board(_document(_board("one"), _board("two")))

    def test_rejects_duplicate_board_tokens(self) -> None:
        with self.assertRaisesRegex(GreenhouseBoardConfigError, "중복 board_token"):
            load_enabled_greenhouse_board(
                _document(_board("Example"), _board("example", enabled=False))
            )

    def test_rejects_non_https_careers_url(self) -> None:
        board = _board()
        board["careers_url"] = "http://example.com/careers"

        with self.assertRaisesRegex(GreenhouseBoardConfigError, "HTTPS"):
            load_enabled_greenhouse_board(_document(board))

    def test_rejects_unapproved_access_method(self) -> None:
        board = _board()
        board["access_method"] = "html_scraping"

        with self.assertRaisesRegex(
            GreenhouseBoardConfigError, "greenhouse_job_board_api"
        ):
            load_enabled_greenhouse_board(_document(board))


if __name__ == "__main__":
    unittest.main()
