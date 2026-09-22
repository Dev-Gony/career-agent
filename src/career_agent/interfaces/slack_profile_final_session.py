"""Bind one final profile proposal to a private Slack review thread."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from career_agent.profile_input import (
    ProfileDocumentError,
    select_latest_profile_analysis_final_review,
)

from .slack_events import SlackEventError


SLACK_PROFILE_FINAL_SESSION_SCHEMA_VERSION = "0.1"
_SESSION_ID_PATTERN = re.compile(r"^slack-profile-final-session-[0-9a-f]{24}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_THREAD_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_FINAL_ID_PATTERN = re.compile(r"^profile-analysis-final-proposal-[0-9a-f]{24}$")
_MAX_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SlackEventError(f"{name} 형식이 올바르지 않음")
    return value


def _validate(session: Mapping[str, Any]) -> tuple[str, datetime, Mapping[str, Any], str]:
    if set(session) != {"slack_profile_final_session", "source", "target", "metadata"}:
        raise SlackEventError("Slack 최종 검토 세션 필드 구성이 올바르지 않음")
    root = _mapping(session.get("slack_profile_final_session"), "session")
    source = _mapping(session.get("source"), "source")
    target = _mapping(session.get("target"), "target")
    metadata = _mapping(session.get("metadata"), "metadata")
    if set(root) != {"session_id", "created_at", "status"} or root.get("status") != "awaiting_final_decision":
        raise SlackEventError("Slack 최종 검토 세션 상태가 올바르지 않음")
    if set(source) != {"team_id", "channel_id", "user_id", "thread_ts"} or set(target) != {"final_proposal_id"}:
        raise SlackEventError("Slack 최종 검토 세션 연결 정보가 올바르지 않음")
    session_id = _identifier(root.get("session_id"), "session_id", _SESSION_ID_PATTERN)
    created_at_text = root.get("created_at")
    if not isinstance(created_at_text, str):
        raise SlackEventError("Slack 최종 검토 세션 시간이 없음")
    try:
        created_at = datetime.fromisoformat(created_at_text)
    except ValueError as error:
        raise SlackEventError("Slack 최종 검토 세션 시간이 올바르지 않음") from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise SlackEventError("Slack 최종 검토 세션 시간에 시간대가 필요함")
    normalized_source = {
        "team_id": _identifier(source.get("team_id"), "team_id", _TEAM_ID_PATTERN),
        "channel_id": _identifier(source.get("channel_id"), "channel_id", _CHANNEL_ID_PATTERN),
        "user_id": _identifier(source.get("user_id"), "user_id", _USER_ID_PATTERN),
        "thread_ts": _identifier(source.get("thread_ts"), "thread_ts", _THREAD_TS_PATTERN),
    }
    final_id = _identifier(target.get("final_proposal_id"), "final_proposal_id", _FINAL_ID_PATTERN)
    expected_metadata = {
        "schema_version": SLACK_PROFILE_FINAL_SESSION_SCHEMA_VERSION,
        "contains_message_text": False,
        "contains_proposal_content": False,
        "contains_personal_data": True,
        "git_tracking_allowed": False,
        "profile_updated": False,
    }
    if metadata != expected_metadata:
        raise SlackEventError("Slack 최종 검토 세션 메타데이터가 올바르지 않음")
    identity = json.dumps({"source": normalized_source, "final_proposal_id": final_id, "created_at": created_at_text}, sort_keys=True, separators=(",", ":"))
    expected_id = "slack-profile-final-session-" + sha256(identity.encode("utf-8")).hexdigest()[:24]
    if session_id != expected_id:
        raise SlackEventError("Slack 최종 검토 세션 ID와 내용 지문이 일치하지 않음")
    return session_id, created_at, source, final_id


def build_slack_profile_final_session(*, team_id: str, channel_id: str, user_id: str, thread_ts: str, final_proposal_id: str, created_at: datetime) -> dict[str, Any]:
    created_at_text = created_at.isoformat(timespec="microseconds")
    source = {"team_id": team_id, "channel_id": channel_id, "user_id": user_id, "thread_ts": thread_ts}
    identity = json.dumps({"source": source, "final_proposal_id": final_proposal_id, "created_at": created_at_text}, sort_keys=True, separators=(",", ":"))
    session = {
        "slack_profile_final_session": {
            "session_id": "slack-profile-final-session-" + sha256(identity.encode("utf-8")).hexdigest()[:24],
            "created_at": created_at_text,
            "status": "awaiting_final_decision",
        },
        "source": source,
        "target": {"final_proposal_id": final_proposal_id},
        "metadata": {
            "schema_version": SLACK_PROFILE_FINAL_SESSION_SCHEMA_VERSION,
            "contains_message_text": False,
            "contains_proposal_content": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    _validate(session)
    return session


def save_slack_profile_final_session(session: Mapping[str, Any], directory: str | Path) -> Path:
    session_id, _, _, _ = _validate(session)
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{session_id}.json"
    if target_path.exists():
        raise SlackEventError("Slack 최종 검토 세션 파일이 이미 존재함")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=target_directory, prefix=f".{session_id}.", suffix=".tmp", delete=False) as temporary_file:
            temporary_file.write(json.dumps(session, ensure_ascii=False, indent=2) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise SlackEventError("Slack 최종 검토 세션을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_slack_profile_final_session(session_id: str, directory: str | Path) -> dict[str, Any]:
    session_id = _identifier(session_id, "session_id", _SESSION_ID_PATTERN)
    path = Path(directory) / f"{session_id}.json"
    if path.is_symlink():
        raise SlackEventError("Slack 최종 검토 세션 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("Slack 최종 검토 세션을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise SlackEventError("Slack 최종 검토 세션 최상위 JSON은 객체여야 함")
    stored_id, _, _, _ = _validate(value)
    if stored_id != session_id:
        raise SlackEventError("Slack 최종 검토 세션 ID가 요청과 일치하지 않음")
    return deepcopy(value)


def select_active_slack_profile_final_session(*, team_id: str, channel_id: str, user_id: str, thread_ts: str, session_directory: str | Path, review_directory: str | Path) -> dict[str, Any] | None:
    expected_source = {"team_id": team_id, "channel_id": channel_id, "user_id": user_id, "thread_ts": thread_ts}
    target_directory = Path(session_directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise SlackEventError("Slack 최종 검토 세션 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("slack-profile-final-session-*.json"))
    if len(paths) > _MAX_FILES:
        raise SlackEventError("Slack 최종 검토 세션 파일이 허용 개수를 초과함")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        session = load_slack_profile_final_session(path.stem, target_directory)
        session_id, created_at, source, final_id = _validate(session)
        if dict(source) != expected_source:
            continue
        try:
            review = select_latest_profile_analysis_final_review(final_id, review_directory)
        except ProfileDocumentError as error:
            raise SlackEventError("최종 변경안 검토 기록을 안전하게 확인할 수 없음") from error
        if review is None:
            candidates.append((created_at, session_id, session))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])
