"""Persist a private Slack thread binding for one profile review item."""

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
    PROFILE_ANALYSIS_ITEM_TYPES,
    ProfileDocumentError,
    select_latest_profile_analysis_reviews,
)

from .slack_events import SlackEventError


SLACK_PROFILE_REVIEW_SESSION_SCHEMA_VERSION = "0.1"
_SESSION_ID_PATTERN = re.compile(r"^slack-profile-review-session-[0-9a-f]{24}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_THREAD_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_DRAFT_ID_PATTERN = re.compile(r"^profile-analysis-draft-[0-9a-f]{24}$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_MAX_STORED_SESSION_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SlackEventError(f"{name} 형식이 올바르지 않음")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise SlackEventError(f"{name} 필드 구성이 올바르지 않음")


def _validated_session(
    session: Mapping[str, Any],
) -> tuple[str, datetime, Mapping[str, Any], Mapping[str, Any]]:
    _exact_keys(
        session,
        {"slack_profile_review_session", "source", "target", "metadata"},
        "slack_profile_review_session_document",
    )
    root = _mapping(session.get("slack_profile_review_session"), "session")
    source = _mapping(session.get("source"), "source")
    target = _mapping(session.get("target"), "target")
    metadata = _mapping(session.get("metadata"), "metadata")
    _exact_keys(root, {"session_id", "created_at", "status"}, "session")
    _exact_keys(source, {"team_id", "channel_id", "user_id", "thread_ts"}, "source")
    _exact_keys(
        target,
        {"draft_id", "extraction_id", "item_type", "item_position"},
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
        },
        "metadata",
    )
    session_id = _text(root.get("session_id"), "session.session_id", _SESSION_ID_PATTERN)
    created_at_text = root.get("created_at")
    if not isinstance(created_at_text, str):
        raise SlackEventError("session.created_at 문자열이 필요함")
    try:
        created_at = datetime.fromisoformat(created_at_text)
    except ValueError as error:
        raise SlackEventError("Slack 검토 세션 시간이 올바르지 않음") from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise SlackEventError("Slack 검토 세션 시간에 시간대가 필요함")
    if root.get("status") != "awaiting_decision":
        raise SlackEventError("Slack 검토 세션 상태가 올바르지 않음")

    team_id = _text(source.get("team_id"), "source.team_id", _TEAM_ID_PATTERN)
    channel_id = _text(source.get("channel_id"), "source.channel_id", _CHANNEL_ID_PATTERN)
    user_id = _text(source.get("user_id"), "source.user_id", _USER_ID_PATTERN)
    thread_ts = _text(source.get("thread_ts"), "source.thread_ts", _THREAD_TS_PATTERN)
    draft_id = _text(target.get("draft_id"), "target.draft_id", _DRAFT_ID_PATTERN)
    extraction_id = _text(
        target.get("extraction_id"), "target.extraction_id", _EXTRACTION_ID_PATTERN
    )
    item_type = target.get("item_type")
    if item_type not in PROFILE_ANALYSIS_ITEM_TYPES:
        raise SlackEventError("Slack 검토 세션 항목 종류가 올바르지 않음")
    item_position = target.get("item_position")
    if isinstance(item_position, bool) or not isinstance(item_position, int) or item_position < 1:
        raise SlackEventError("Slack 검토 세션 항목 순번이 올바르지 않음")

    if metadata.get("schema_version") != SLACK_PROFILE_REVIEW_SESSION_SCHEMA_VERSION:
        raise SlackEventError("현재 버전의 Slack 검토 세션이 아님")
    for field in (
        "contains_message_text",
        "contains_analysis_text",
        "contains_candidate_text",
        "git_tracking_allowed",
    ):
        if metadata.get(field) is not False:
            raise SlackEventError(f"Slack 검토 세션 {field} 표시가 올바르지 않음")
    if metadata.get("contains_personal_data") is not True:
        raise SlackEventError("Slack 검토 세션 개인정보 표시가 없음")

    identity = "|".join(
        (
            team_id,
            channel_id,
            user_id,
            thread_ts,
            draft_id,
            extraction_id,
            str(item_type),
            str(item_position),
            created_at_text,
        )
    )
    expected_id = "slack-profile-review-session-" + sha256(
        identity.encode("utf-8")
    ).hexdigest()[:24]
    if session_id != expected_id:
        raise SlackEventError("Slack 검토 세션 ID와 내용 지문이 일치하지 않음")
    return session_id, created_at, source, target


def build_slack_profile_review_session(
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    draft_id: str,
    extraction_id: str,
    item_type: str,
    item_position: int,
    created_at: datetime,
) -> dict[str, Any]:
    """Build one thread-bound session without storing message or analysis text."""

    created_at_text = created_at.isoformat(timespec="microseconds")
    identity = "|".join(
        (
            team_id,
            channel_id,
            user_id,
            thread_ts,
            draft_id,
            extraction_id,
            item_type,
            str(item_position),
            created_at_text,
        )
    )
    session = {
        "slack_profile_review_session": {
            "session_id": "slack-profile-review-session-"
            + sha256(identity.encode("utf-8")).hexdigest()[:24],
            "created_at": created_at_text,
            "status": "awaiting_decision",
        },
        "source": {
            "team_id": team_id,
            "channel_id": channel_id,
            "user_id": user_id,
            "thread_ts": thread_ts,
        },
        "target": {
            "draft_id": draft_id,
            "extraction_id": extraction_id,
            "item_type": item_type,
            "item_position": item_position,
        },
        "metadata": {
            "schema_version": SLACK_PROFILE_REVIEW_SESSION_SCHEMA_VERSION,
            "contains_message_text": False,
            "contains_analysis_text": False,
            "contains_candidate_text": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
        },
    }
    _validated_session(session)
    return session


def save_slack_profile_review_session(
    session: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save one immutable private Slack profile review session."""

    session_id, _, _, _ = _validated_session(session)
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{session_id}.json"
    if target_path.exists():
        raise SlackEventError("Slack 검토 세션 파일이 이미 존재함")
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
        raise SlackEventError("Slack 검토 세션을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_slack_profile_review_session(
    session_id: str, directory: str | Path
) -> dict[str, Any]:
    """Load and verify one immutable private Slack profile review session."""

    normalized_id = _text(session_id, "session_id", _SESSION_ID_PATTERN)
    path = Path(directory) / f"{normalized_id}.json"
    if path.is_symlink():
        raise SlackEventError("Slack 검토 세션 심볼릭 링크는 읽을 수 없음")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("Slack 검토 세션을 읽을 수 없음") from error
    if not isinstance(session, dict):
        raise SlackEventError("Slack 검토 세션 최상위 JSON은 객체여야 함")
    stored_id, _, _, _ = _validated_session(session)
    if stored_id != normalized_id:
        raise SlackEventError("Slack 검토 세션 ID가 요청과 일치하지 않음")
    return deepcopy(session)


def select_active_slack_profile_review_session(
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    session_directory: str | Path,
    review_directory: str | Path,
) -> dict[str, Any] | None:
    """Select the newest same-thread session whose target has no decision."""

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
        raise SlackEventError("Slack 검토 세션 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("slack-profile-review-session-*.json"))
    if len(paths) > _MAX_STORED_SESSION_FILES:
        raise SlackEventError("Slack 검토 세션 파일이 허용 개수를 초과함")

    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    reviews_by_draft: dict[str, dict[tuple[str, int], dict[str, Any]]] = {}
    for path in paths:
        session = load_slack_profile_review_session(path.stem, target_directory)
        session_id, created_at, source, target = _validated_session(session)
        if dict(source) != expected_source:
            continue
        draft_id = str(target["draft_id"])
        try:
            if draft_id not in reviews_by_draft:
                reviews_by_draft[draft_id] = select_latest_profile_analysis_reviews(
                    draft_id,
                    review_directory,
                )
            reviews = reviews_by_draft[draft_id]
        except ProfileDocumentError as error:
            raise SlackEventError("프로필 분석 검토 기록을 안전하게 확인할 수 없음") from error
        item_key = (str(target["item_type"]), int(target["item_position"]))
        if item_key not in reviews:
            candidates.append((created_at, session_id, session))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])
