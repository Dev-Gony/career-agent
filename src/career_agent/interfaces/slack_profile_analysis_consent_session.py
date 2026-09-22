"""Bind one external profile analysis consent prompt to a private Slack thread."""

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
    profile_analysis_request_sha256,
    select_latest_profile_analysis_external_consent_for_session,
)

from .slack_events import SlackEventError


SLACK_PROFILE_ANALYSIS_CONSENT_SESSION_SCHEMA_VERSION = "0.1"
_SESSION_ID_PATTERN = re.compile(r"^slack-profile-analysis-consent-session-[0-9a-f]{24}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_THREAD_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise SlackEventError(f"{name} 형식이 올바르지 않음")
    return value


def _validate(
    session: Mapping[str, Any],
) -> tuple[str, datetime, Mapping[str, Any], Mapping[str, Any]]:
    if set(session) != {
        "slack_profile_analysis_consent_session",
        "source",
        "target",
        "metadata",
    }:
        raise SlackEventError("Slack 외부 분석 동의 세션 필드 구성이 올바르지 않음")
    root = _mapping(session.get("slack_profile_analysis_consent_session"), "session")
    source = _mapping(session.get("source"), "source")
    target = _mapping(session.get("target"), "target")
    metadata = _mapping(session.get("metadata"), "metadata")
    if set(root) != {"session_id", "created_at", "status"} or root.get("status") != "awaiting_external_transfer_decision":
        raise SlackEventError("Slack 외부 분석 동의 세션 상태가 올바르지 않음")
    if set(source) != {"team_id", "channel_id", "user_id", "thread_ts"}:
        raise SlackEventError("Slack 외부 분석 동의 세션 출처가 올바르지 않음")
    if set(target) != {
        "extraction_id",
        "request_sha256",
        "provider_name",
        "model_name",
    }:
        raise SlackEventError("Slack 외부 분석 동의 세션 대상이 올바르지 않음")
    session_id = _identifier(root.get("session_id"), "session_id", _SESSION_ID_PATTERN)
    created_at_text = root.get("created_at")
    if not isinstance(created_at_text, str):
        raise SlackEventError("Slack 외부 분석 동의 세션 시간이 없음")
    try:
        created_at = datetime.fromisoformat(created_at_text)
    except ValueError as error:
        raise SlackEventError("Slack 외부 분석 동의 세션 시간이 올바르지 않음") from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise SlackEventError("Slack 외부 분석 동의 세션 시간에 시간대가 필요함")
    normalized_source = {
        "team_id": _identifier(source.get("team_id"), "team_id", _TEAM_ID_PATTERN),
        "channel_id": _identifier(source.get("channel_id"), "channel_id", _CHANNEL_ID_PATTERN),
        "user_id": _identifier(source.get("user_id"), "user_id", _USER_ID_PATTERN),
        "thread_ts": _identifier(source.get("thread_ts"), "thread_ts", _THREAD_TS_PATTERN),
    }
    normalized_target = {
        "extraction_id": _identifier(target.get("extraction_id"), "extraction_id", _EXTRACTION_ID_PATTERN),
        "request_sha256": _identifier(target.get("request_sha256"), "request_sha256", _HASH_PATTERN),
        "provider_name": _identifier(target.get("provider_name"), "provider_name", _NAME_PATTERN),
        "model_name": _identifier(target.get("model_name"), "model_name", _NAME_PATTERN),
    }
    if metadata != {
        "schema_version": SLACK_PROFILE_ANALYSIS_CONSENT_SESSION_SCHEMA_VERSION,
        "contains_message_text": False,
        "contains_candidate_text": False,
        "contains_personal_data": True,
        "sends_data_externally": True,
        "git_tracking_allowed": False,
        "profile_updated": False,
    }:
        raise SlackEventError("Slack 외부 분석 동의 세션 메타데이터가 올바르지 않음")
    identity = json.dumps(
        {
            "source": normalized_source,
            "target": normalized_target,
            "created_at": created_at_text,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    expected_id = "slack-profile-analysis-consent-session-" + sha256(
        identity.encode("utf-8")
    ).hexdigest()[:24]
    if session_id != expected_id:
        raise SlackEventError("Slack 외부 분석 동의 세션 ID와 내용 지문이 일치하지 않음")
    return session_id, created_at, source, target


def build_slack_profile_analysis_consent_session(
    extraction: Mapping[str, Any],
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    provider_name: str,
    model_name: str,
    created_at: datetime,
) -> dict[str, Any]:
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise SlackEventError("created_at은 시간대가 포함되어야 함")
    root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    extraction_id = _identifier(
        root.get("extraction_id"), "extraction_id", _EXTRACTION_ID_PATTERN
    )
    source = {
        "team_id": team_id,
        "channel_id": channel_id,
        "user_id": user_id,
        "thread_ts": thread_ts,
    }
    target = {
        "extraction_id": extraction_id,
        "request_sha256": profile_analysis_request_sha256(extraction),
        "provider_name": provider_name,
        "model_name": model_name,
    }
    created_at_text = created_at.isoformat(timespec="microseconds")
    identity = json.dumps(
        {"source": source, "target": target, "created_at": created_at_text},
        sort_keys=True,
        separators=(",", ":"),
    )
    session = {
        "slack_profile_analysis_consent_session": {
            "session_id": "slack-profile-analysis-consent-session-"
            + sha256(identity.encode("utf-8")).hexdigest()[:24],
            "created_at": created_at_text,
            "status": "awaiting_external_transfer_decision",
        },
        "source": source,
        "target": target,
        "metadata": {
            "schema_version": SLACK_PROFILE_ANALYSIS_CONSENT_SESSION_SCHEMA_VERSION,
            "contains_message_text": False,
            "contains_candidate_text": False,
            "contains_personal_data": True,
            "sends_data_externally": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    _validate(session)
    return session


def save_slack_profile_analysis_consent_session(
    session: Mapping[str, Any], directory: str | Path
) -> Path:
    session_id, _, _, _ = _validate(session)
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{session_id}.json"
    if target_path.exists():
        raise SlackEventError("Slack 외부 분석 동의 세션이 이미 존재함")
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
            temporary_file.write(json.dumps(session, ensure_ascii=False, indent=2) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise SlackEventError("Slack 외부 분석 동의 세션을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_slack_profile_analysis_consent_session(
    session_id: str, directory: str | Path
) -> dict[str, Any]:
    session_id = _identifier(session_id, "session_id", _SESSION_ID_PATTERN)
    path = Path(directory) / f"{session_id}.json"
    if path.is_symlink():
        raise SlackEventError("Slack 외부 분석 동의 세션 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("Slack 외부 분석 동의 세션을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise SlackEventError("Slack 외부 분석 동의 세션 최상위 JSON은 객체여야 함")
    stored_id, _, _, _ = _validate(value)
    if stored_id != session_id:
        raise SlackEventError("Slack 외부 분석 동의 세션 ID가 요청과 일치하지 않음")
    return deepcopy(value)


def select_active_slack_profile_analysis_consent_session(
    *,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    session_directory: str | Path,
    consent_directory: str | Path,
) -> dict[str, Any] | None:
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
        raise SlackEventError("Slack 외부 분석 동의 세션 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("slack-profile-analysis-consent-session-*.json"))
    if len(paths) > _MAX_FILES:
        raise SlackEventError("Slack 외부 분석 동의 세션이 허용 개수를 초과함")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        session = load_slack_profile_analysis_consent_session(path.stem, target_directory)
        session_id, created_at, source, _ = _validate(session)
        if dict(source) != expected_source:
            continue
        candidates.append((created_at, session_id, session))
    if not candidates:
        return None
    created_at, session_id, session = max(
        candidates, key=lambda value: (value[0], value[1])
    )
    target = session["target"]
    try:
        consent = select_latest_profile_analysis_external_consent_for_session(
            session_id,
            consent_directory,
        )
    except ProfileDocumentError as error:
        raise SlackEventError("외부 분석 동의 기록을 안전하게 확인할 수 없음") from error
    if consent is None:
        return deepcopy(session)
    consent_root = consent["profile_analysis_external_consent"]
    consent_source = consent["source"]
    try:
        decided_at = datetime.fromisoformat(consent_root["decided_at"])
    except (TypeError, ValueError) as error:
        raise SlackEventError("외부 분석 동의 결정 시간이 올바르지 않음") from error
    expected_consent_source = {
        **dict(target),
        "consent_session_id": session_id,
        **expected_source,
    }
    if dict(consent_source) != expected_consent_source:
        raise SlackEventError("외부 분석 동의 기록이 Slack 세션과 일치하지 않음")
    if decided_at < created_at:
        raise SlackEventError("외부 분석 동의 결정이 세션보다 먼저 생성됨")
    return None
