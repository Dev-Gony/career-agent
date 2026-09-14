"""Validate the constrained Greenhouse source registry for the personal MVP."""

from __future__ import annotations

from datetime import date
import re
from typing import Any, Mapping
from urllib.parse import urlsplit


_BOARD_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")


class GreenhouseBoardConfigError(ValueError):
    """Raised when the Greenhouse board registry is unsafe or unsupported."""


def load_enabled_greenhouse_board(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return the single enabled board allowed by the current MVP."""

    if not isinstance(document, Mapping):
        raise GreenhouseBoardConfigError("Greenhouse 보드 설정은 JSON 객체여야 함")
    root = document.get("greenhouse_boards")
    if not isinstance(root, Mapping):
        raise GreenhouseBoardConfigError("greenhouse_boards 객체가 필요함")
    boards = root.get("boards")
    if not isinstance(boards, list) or not boards:
        raise GreenhouseBoardConfigError("greenhouse_boards.boards 배열이 필요함")

    normalized: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    for position, board in enumerate(boards, start=1):
        if not isinstance(board, Mapping):
            raise GreenhouseBoardConfigError(f"boards[{position}]는 객체여야 함")
        token = _required_text(board, "board_token", position)
        if not _BOARD_TOKEN_PATTERN.fullmatch(token):
            raise GreenhouseBoardConfigError(
                f"boards[{position}].board_token 형식이 올바르지 않음"
            )
        token_key = token.casefold()
        if token_key in seen_tokens:
            raise GreenhouseBoardConfigError(f"중복 board_token: {token}")
        seen_tokens.add(token_key)
        company = _required_text(board, "company", position)
        careers_url = _required_https_url(board, "careers_url", position)
        access_method = _required_text(board, "access_method", position)
        if access_method != "greenhouse_job_board_api":
            raise GreenhouseBoardConfigError(
                f"boards[{position}].access_method는 greenhouse_job_board_api여야 함"
            )
        checked_at_text = _required_text(board, "policy_checked_at", position)
        try:
            checked_at = date.fromisoformat(checked_at_text)
        except ValueError as error:
            raise GreenhouseBoardConfigError(
                f"boards[{position}].policy_checked_at은 YYYY-MM-DD여야 함"
            ) from error
        enabled = board.get("enabled")
        if not isinstance(enabled, bool):
            raise GreenhouseBoardConfigError(
                f"boards[{position}].enabled는 boolean이어야 함"
            )
        normalized.append(
            {
                "board_token": token,
                "company": company,
                "careers_url": careers_url,
                "access_method": access_method,
                "policy_checked_at": checked_at,
                "enabled": enabled,
            }
        )

    enabled_boards = [board for board in normalized if board["enabled"]]
    if len(enabled_boards) != 1:
        raise GreenhouseBoardConfigError(
            "현재 개인용 MVP는 enabled 보드를 정확히 1개만 허용함"
        )
    return enabled_boards[0]


def _required_text(
    document: Mapping[str, Any], key: str, position: int
) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseBoardConfigError(f"boards[{position}].{key} 문자열이 필요함")
    return value.strip()


def _required_https_url(
    document: Mapping[str, Any], key: str, position: int
) -> str:
    value = _required_text(document, key, position)
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise GreenhouseBoardConfigError(
            f"boards[{position}].{key}는 인증정보 없는 HTTPS URL이어야 함"
        )
    return value
