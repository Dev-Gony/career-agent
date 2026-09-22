"""Select one exact, explicit approval before an external profile analysis call."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping

from .analysis_external_consent import (
    profile_analysis_request_sha256,
    select_latest_profile_analysis_external_consent_for_session,
)
from .document_store import ProfileDocumentError


_SESSION_SCHEMA_VERSION = "0.1"
_SESSION_ID_PATTERN = re.compile(r"^slack-profile-analysis-consent-session-[0-9a-f]{24}$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_TEAM_ID_PATTERN = re.compile(r"^T[A-Za-z0-9]{6,31}$")
_USER_ID_PATTERN = re.compile(r"^[UW][A-Za-z0-9]{6,31}$")
_CHANNEL_ID_PATTERN = re.compile(r"^[CGD][A-Za-z0-9]{6,31}$")
_THREAD_TS_PATTERN = re.compile(r"^[0-9]{1,20}(?:\.[0-9]{1,20})?$")
_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,99}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _identifier(value: Any, name: str, pattern: re.Pattern[str]) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProfileDocumentError(f"{name} 형식이 올바르지 않음")
    return value


def _validated_session(
    value: Mapping[str, Any],
) -> tuple[str, datetime, Mapping[str, Any], Mapping[str, Any]]:
    if set(value) != {
        "slack_profile_analysis_consent_session",
        "source",
        "target",
        "metadata",
    }:
        raise ProfileDocumentError("외부 분석 동의 세션 필드 구성이 올바르지 않음")
    root = _mapping(
        value.get("slack_profile_analysis_consent_session"),
        "slack_profile_analysis_consent_session",
    )
    source = _mapping(value.get("source"), "source")
    target = _mapping(value.get("target"), "target")
    metadata = _mapping(value.get("metadata"), "metadata")
    if set(root) != {"session_id", "created_at", "status"}:
        raise ProfileDocumentError("외부 분석 동의 세션 상태 필드가 올바르지 않음")
    if root.get("status") != "awaiting_external_transfer_decision":
        raise ProfileDocumentError("외부 분석 동의 세션 상태가 올바르지 않음")
    if set(source) != {"team_id", "channel_id", "user_id", "thread_ts"}:
        raise ProfileDocumentError("외부 분석 동의 세션 출처가 올바르지 않음")
    if set(target) != {
        "extraction_id",
        "request_sha256",
        "provider_name",
        "model_name",
    }:
        raise ProfileDocumentError("외부 분석 동의 세션 대상이 올바르지 않음")
    session_id = _identifier(root.get("session_id"), "session_id", _SESSION_ID_PATTERN)
    created_at_text = root.get("created_at")
    if not isinstance(created_at_text, str):
        raise ProfileDocumentError("외부 분석 동의 세션 생성 시간이 없음")
    try:
        created_at = datetime.fromisoformat(created_at_text)
    except ValueError as error:
        raise ProfileDocumentError("외부 분석 동의 세션 생성 시간이 올바르지 않음") from error
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProfileDocumentError("외부 분석 동의 세션 생성 시간에 시간대가 필요함")
    normalized_source = {
        "team_id": _identifier(source.get("team_id"), "team_id", _TEAM_ID_PATTERN),
        "channel_id": _identifier(
            source.get("channel_id"), "channel_id", _CHANNEL_ID_PATTERN
        ),
        "user_id": _identifier(source.get("user_id"), "user_id", _USER_ID_PATTERN),
        "thread_ts": _identifier(
            source.get("thread_ts"), "thread_ts", _THREAD_TS_PATTERN
        ),
    }
    normalized_target = {
        "extraction_id": _identifier(
            target.get("extraction_id"), "extraction_id", _EXTRACTION_ID_PATTERN
        ),
        "request_sha256": _identifier(
            target.get("request_sha256"), "request_sha256", _HASH_PATTERN
        ),
        "provider_name": _identifier(
            target.get("provider_name"), "provider_name", _NAME_PATTERN
        ),
        "model_name": _identifier(
            target.get("model_name"), "model_name", _NAME_PATTERN
        ),
    }
    if metadata != {
        "schema_version": _SESSION_SCHEMA_VERSION,
        "contains_message_text": False,
        "contains_candidate_text": False,
        "contains_personal_data": True,
        "sends_data_externally": True,
        "git_tracking_allowed": False,
        "profile_updated": False,
    }:
        raise ProfileDocumentError("외부 분석 동의 세션 메타데이터가 올바르지 않음")
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
        raise ProfileDocumentError("외부 분석 동의 세션 ID와 내용 지문이 일치하지 않음")
    return session_id, created_at, normalized_source, normalized_target


def _load_session(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise ProfileDocumentError("외부 분석 동의 세션 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("외부 분석 동의 세션을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError("외부 분석 동의 세션 최상위 JSON은 객체여야 함")
    session_id, _, _, _ = _validated_session(value)
    if path.stem != session_id:
        raise ProfileDocumentError("외부 분석 동의 세션 파일명과 ID가 일치하지 않음")
    return value


def require_approved_profile_analysis_external_consent(
    extraction: Mapping[str, Any],
    *,
    provider_name: str,
    model_name: str,
    session_directory: str | Path,
    consent_directory: str | Path,
    team_id: str | None = None,
    channel_id: str | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Return the exact latest session approval or fail before any external call."""

    extraction_root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    extraction_id = _identifier(
        extraction_root.get("extraction_id"), "extraction_id", _EXTRACTION_ID_PATTERN
    )
    provider_name = _identifier(provider_name, "provider_name", _NAME_PATTERN)
    model_name = _identifier(model_name, "model_name", _NAME_PATTERN)
    request_hash = profile_analysis_request_sha256(extraction)
    expected_target = {
        "extraction_id": extraction_id,
        "request_sha256": request_hash,
        "provider_name": provider_name,
        "model_name": model_name,
    }
    actor_values = (team_id, channel_id, user_id)
    if any(value is not None for value in actor_values) and not all(
        value is not None for value in actor_values
    ):
        raise ProfileDocumentError(
            "Slack 사용자 범위에는 team_id, channel_id, user_id가 모두 필요함"
        )
    expected_actor = None
    if all(value is not None for value in actor_values):
        expected_actor = {
            "team_id": _identifier(team_id, "team_id", _TEAM_ID_PATTERN),
            "channel_id": _identifier(channel_id, "channel_id", _CHANNEL_ID_PATTERN),
            "user_id": _identifier(user_id, "user_id", _USER_ID_PATTERN),
        }

    target_directory = Path(session_directory)
    if not target_directory.exists():
        raise ProfileDocumentError("외부 분석 동의 세션이 없음")
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("외부 분석 동의 세션 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("slack-profile-analysis-consent-session-*.json"))
    if len(paths) > _MAX_FILES:
        raise ProfileDocumentError("외부 분석 동의 세션이 허용 개수를 초과함")
    candidates: list[
        tuple[datetime, str, Mapping[str, Any], Mapping[str, Any]]
    ] = []
    for path in paths:
        session = _load_session(path)
        session_id, created_at, source, target = _validated_session(session)
        actor_matches = expected_actor is None or all(
            source.get(field) == value for field, value in expected_actor.items()
        )
        if dict(target) == expected_target and actor_matches:
            candidates.append((created_at, session_id, source, target))
    if not candidates:
        raise ProfileDocumentError(
            "현재 사용자, 채널, 문서와 공급자에 맞는 외부 분석 동의 세션이 없음"
        )
    created_at, session_id, session_source, session_target = max(
        candidates, key=lambda item: (item[0], item[1])
    )

    consent = select_latest_profile_analysis_external_consent_for_session(
        session_id,
        consent_directory,
    )
    if consent is None:
        raise ProfileDocumentError("최신 외부 분석 동의 세션에 사용자 결정이 없음")
    consent_root = _mapping(
        consent.get("profile_analysis_external_consent"),
        "profile_analysis_external_consent",
    )
    consent_source = _mapping(consent.get("source"), "source")
    expected_source = {
        **dict(session_target),
        "consent_session_id": session_id,
        **dict(session_source),
    }
    if dict(consent_source) != expected_source:
        raise ProfileDocumentError("외부 분석 동의 기록이 최신 세션과 일치하지 않음")
    decided_at_text = consent_root.get("decided_at")
    if not isinstance(decided_at_text, str):
        raise ProfileDocumentError("외부 분석 동의 결정 시간이 없음")
    try:
        decided_at = datetime.fromisoformat(decided_at_text)
    except ValueError as error:
        raise ProfileDocumentError("외부 분석 동의 결정 시간이 올바르지 않음") from error
    if decided_at < created_at:
        raise ProfileDocumentError("외부 분석 동의 결정이 최신 세션보다 먼저 생성됨")
    if consent_root.get("decision") != "approve":
        raise ProfileDocumentError("최신 외부 분석 동의 결정이 승인이 아님")
    return deepcopy(dict(consent))
