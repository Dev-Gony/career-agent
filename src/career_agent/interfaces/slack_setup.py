"""Check local Slack Socket Mode setup without exposing credentials."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
from typing import Mapping

from .slack_events import SlackEventError, validate_slack_interface_config


MAX_ENV_FILE_BYTES = 16 * 1024
_TOKEN_PATTERNS = {
    "SLACK_APP_TOKEN": re.compile(r"^xapp-[A-Za-z0-9-]{12,}$"),
    "SLACK_BOT_TOKEN": re.compile(r"^xoxb-[A-Za-z0-9-]{12,}$"),
}


def _load_config(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SlackEventError(f"실제 Slack 설정 파일이 없음: {path}") from error
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError(f"Slack 설정 JSON을 읽을 수 없음: {path}") from error
    if not isinstance(value, dict):
        raise SlackEventError("Slack 설정 최상위 JSON은 객체여야 함")
    return value


def _dotenv_values(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        if path.stat().st_size > MAX_ENV_FILE_BYTES:
            raise SlackEventError(f"환경 변수 파일이 {MAX_ENV_FILE_BYTES}바이트보다 큼")
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        raise SlackEventError(f"환경 변수 파일을 읽을 수 없음: {path}") from error
    values: dict[str, str] = {}
    for position, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" not in stripped:
            raise SlackEventError(f"환경 변수 파일 {position}번째 줄 형식이 올바르지 않음")
        name, value = stripped.split("=", 1)
        name = name.strip()
        if name not in _TOKEN_PATTERNS:
            continue
        if name in values:
            raise SlackEventError(f"환경 변수 파일에 {name}이 중복됨")
        normalized_value = value.strip()
        if (
            len(normalized_value) >= 2
            and normalized_value[0] == normalized_value[-1]
            and normalized_value[0] in {'"', "'"}
        ):
            normalized_value = normalized_value[1:-1]
        values[name] = normalized_value
    return values


def check_slack_setup(
    config_path: str | Path,
    env_file: str | Path,
    *,
    environment: Mapping[str, str] | None = None,
) -> dict[str, bool]:
    """Validate Slack IDs and token presence without returning token values."""

    validate_slack_interface_config(_load_config(Path(config_path)))
    file_values = _dotenv_values(Path(env_file))
    process_values = os.environ if environment is None else environment
    for name, pattern in _TOKEN_PATTERNS.items():
        value = process_values.get(name) or file_values.get(name)
        if not value:
            raise SlackEventError(f"{name}이 환경 변수 또는 .env에 없음")
        if "replace" in value.casefold() or pattern.fullmatch(value) is None:
            raise SlackEventError(f"{name} 형식이 올바르지 않음")
    return {
        "config_ready": True,
        "app_token_ready": True,
        "bot_token_ready": True,
    }
