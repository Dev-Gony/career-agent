"""Bind one profile-change mapping prompt to a private Slack thread."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping, Sequence

from career_agent.profile_input import (
    ProfileDocumentError,
    select_latest_profile_analysis_mapping_reviews,
)

from .slack_events import SlackEventError


SLACK_PROFILE_MAPPING_SESSION_SCHEMA_VERSION = "0.1"
_SESSION_ID_PATTERN = re.compile(r"^slack-profile-mapping-session-[0-9a-f]{24}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_THREAD_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_PROPOSAL_ID_PATTERN = re.compile(r"^profile-analysis-update-proposal-[0-9a-f]{24}$")
_CHANGE_ID_PATTERN = re.compile(r"^analysis-change-[0-9]{3}$")
_CAREER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_MAPPING_STATUSES = {
    "needs_career_selection",
    "needs_skill_level_confirmation",
}
_SKILL_LEVELS = {"none", "exposure", "learning", "basic", "project", "work"}
_MAX_STORED_SESSION_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SlackEventError(f"{name} 형식이 올바르지 않음")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise SlackEventError(f"{name} 필드 구성이 올바르지 않음")


def _validated_session(
    session: Mapping[str, Any],
) -> tuple[str, datetime, Mapping[str, Any], Mapping[str, Any]]:
    _exact_keys(
        session,
        {"slack_profile_mapping_session", "source", "target", "metadata"},
        "slack_profile_mapping_session_document",
    )
    root = _mapping(session.get("slack_profile_mapping_session"), "session")
    source = _mapping(session.get("source"), "source")
    target = _mapping(session.get("target"), "target")
    metadata = _mapping(session.get("metadata"), "metadata")
    _exact_keys(root, {"session_id", "created_at", "status"}, "session")
    _exact_keys(source, {"team_id", "channel_id", "user_id", "thread_ts"}, "source")
    _exact_keys(
        target,
        {"proposal_id", "change_id", "mapping_status", "allowed_values"},
        "target",
    )
    _exact_keys(
        metadata,
        {
            "schema_version",
            "contains_message_text",
            "contains_analysis_text",
            "contains_candidate_text",
            "contains_personal_data",
            "git_tracking_allowed",
            "profile_updated",
        },
        "metadata",
    )
    session_id = _identifier(root.get("session_id"), "session.session_id", _SESSION_ID_PATTERN)
    created_at_text = root.get("created_at")
    if not isinstance(created_at_text, str):
        raise SlackEventError("session.created_at 문자열이 필요함")
    try:
        created_at = datetime.fromisoformat(created_at_text)
    except ValueError as error:
        raise SlackEventError("Slack 매핑 세션 시간이 올바르지 않음") from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise SlackEventError("Slack 매핑 세션 시간에 시간대가 필요함")
    if root.get("status") != "awaiting_selection":
        raise SlackEventError("Slack 매핑 세션 상태가 올바르지 않음")

    team_id = _identifier(source.get("team_id"), "source.team_id", _TEAM_ID_PATTERN)
    channel_id = _identifier(source.get("channel_id"), "source.channel_id", _CHANNEL_ID_PATTERN)
    user_id = _identifier(source.get("user_id"), "source.user_id", _USER_ID_PATTERN)
    thread_ts = _identifier(source.get("thread_ts"), "source.thread_ts", _THREAD_TS_PATTERN)
    proposal_id = _identifier(target.get("proposal_id"), "target.proposal_id", _PROPOSAL_ID_PATTERN)
    change_id = _identifier(target.get("change_id"), "target.change_id", _CHANGE_ID_PATTERN)
    mapping_status = target.get("mapping_status")
    if mapping_status not in _MAPPING_STATUSES:
        raise SlackEventError("Slack 매핑 세션 상태가 올바르지 않음")
    raw_allowed_values = target.get("allowed_values")
    if not isinstance(raw_allowed_values, list) or not raw_allowed_values:
        raise SlackEventError("Slack 매핑 세션 허용값 배열이 필요함")
    allowed_values: list[str] = []
    for position, value in enumerate(raw_allowed_values):
        if not isinstance(value, str):
            raise SlackEventError(f"target.allowed_values[{position}] 문자열이 필요함")
        if mapping_status == "needs_career_selection":
            _identifier(value, f"target.allowed_values[{position}]", _CAREER_ID_PATTERN)
        elif value not in _SKILL_LEVELS:
            raise SlackEventError("Slack 매핑 세션 기술 숙련도가 올바르지 않음")
        allowed_values.append(value)
    if len(set(allowed_values)) != len(allowed_values):
        raise SlackEventError("Slack 매핑 세션 허용값에 중복이 있음")

    if metadata.get("schema_version") != SLACK_PROFILE_MAPPING_SESSION_SCHEMA_VERSION:
        raise SlackEventError("현재 버전의 Slack 매핑 세션이 아님")
    for field in (
        "contains_message_text",
        "contains_analysis_text",
        "contains_candidate_text",
        "git_tracking_allowed",
        "profile_updated",
    ):
        if metadata.get(field) is not False:
            raise SlackEventError(f"Slack 매핑 세션 {field} 표시가 올바르지 않음")
    if metadata.get("contains_personal_data") is not True:
        raise SlackEventError("Slack 매핑 세션 개인정보 표시가 없음")

    identity = json.dumps(
        {
            "source": dict(source),
            "proposal_id": proposal_id,
            "change_id": change_id,
            "mapping_status": mapping_status,
            "allowed_values": allowed_values,
            "created_at": created_at_text,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_id = "slack-profile-mapping-session-" + sha256(
        identity.encode("utf-8")
    ).hexdigest()[:24]
    if session_id != expected_id:
        raise SlackEventError("Slack 매핑 세션 ID와 내용 지문이 일치하지 않음")
    return session_id, created_at, source, target


def build_slack_profile_mapping_session(
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    proposal_id: str,
    change_id: str,
    mapping_status: str,
    allowed_values: Sequence[str],
    created_at: datetime,
) -> dict[str, Any]:
    """Build a thread-bound selection session without copying analysis text."""

    created_at_text = created_at.isoformat(timespec="microseconds")
    source = {
        "team_id": team_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "thread_ts": thread_ts,
    }
    target = {
        "proposal_id": proposal_id,
        "change_id": change_id,
        "mapping_status": mapping_status,
        "allowed_values": list(allowed_values),
    }
    identity = json.dumps(
        {
            "source": source,
            **target,
            "created_at": created_at_text,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    session = {
        "slack_profile_mapping_session": {
            "session_id": "slack-profile-mapping-session-"
            + sha256(identity.encode("utf-8")).hexdigest()[:24],
            "created_at": created_at_text,
            "status": "awaiting_selection",
        },
        "source": source,
        "target": target,
        "metadata": {
            "schema_version": SLACK_PROFILE_MAPPING_SESSION_SCHEMA_VERSION,
            "contains_message_text": False,
            "contains_analysis_text": False,
            "contains_candidate_text": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    _validated_session(session)
    return session


def save_slack_profile_mapping_session(
    session: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save one immutable private Slack mapping session."""

    session_id, _, _, _ = _validated_session(session)
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{session_id}.json"
    if target_path.exists():
        raise SlackEventError("Slack 매핑 세션 파일이 이미 존재함")
    serialized = json.dumps(session, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{session_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise SlackEventError("Slack 매핑 세션을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_slack_profile_mapping_session(
    session_id: str, directory: str | Path
) -> dict[str, Any]:
    """Load and verify one immutable private Slack mapping session."""

    session_id = _identifier(session_id, "session_id", _SESSION_ID_PATTERN)
    path = Path(directory) / f"{session_id}.json"
    if path.is_symlink():
        raise SlackEventError("Slack 매핑 세션 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("Slack 매핑 세션을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise SlackEventError("Slack 매핑 세션 최상위 JSON은 객체여야 함")
    stored_id, _, _, _ = _validated_session(value)
    if stored_id != session_id:
        raise SlackEventError("Slack 매핑 세션 ID가 요청과 일치하지 않음")
    return deepcopy(value)


def select_active_slack_profile_mapping_session(
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    session_directory: str | Path,
    review_directory: str | Path,
) -> dict[str, Any] | None:
    """Select the newest same-thread session whose target has no saved choice."""

    expected_source = {
        "team_id": team_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "thread_ts": thread_ts,
    }
    target_directory = Path(session_directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise SlackEventError("Slack 매핑 세션 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("slack-profile-mapping-session-*.json"))
    if len(paths) > _MAX_STORED_SESSION_FILES:
        raise SlackEventError("Slack 매핑 세션 파일이 허용 개수를 초과함")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    reviews_by_proposal: dict[str, dict[str, dict[str, Any]]] = {}
    for path in paths:
        session = load_slack_profile_mapping_session(path.stem, target_directory)
        session_id, created_at, source, target = _validated_session(session)
        if dict(source) != expected_source:
            continue
        proposal_id = str(target["proposal_id"])
        try:
            if proposal_id not in reviews_by_proposal:
                reviews_by_proposal[proposal_id] = (
                    select_latest_profile_analysis_mapping_reviews(
                        proposal_id,
                        review_directory,
                    )
                )
        except ProfileDocumentError as error:
            raise SlackEventError("프로필 변경 매핑 기록을 안전하게 확인할 수 없음") from error
        if str(target["change_id"]) not in reviews_by_proposal[proposal_id]:
            candidates.append((created_at, session_id, session))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])
