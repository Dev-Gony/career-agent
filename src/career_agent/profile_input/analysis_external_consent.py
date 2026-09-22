"""Record explicit consent decisions for one external profile analysis payload."""

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

from .analysis_draft import build_profile_analysis_request
from .document_store import ProfileDocumentError


PROFILE_ANALYSIS_EXTERNAL_CONSENT_SCHEMA_VERSION = "0.1"
PROFILE_ANALYSIS_EXTERNAL_CONSENT_DECISIONS = frozenset({"approve", "reject"})
_CONSENT_ID_PATTERN = re.compile(r"^profile-analysis-external-consent-[0-9a-f]{24}$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_SESSION_ID_PATTERN = re.compile(r"^slack-profile-analysis-consent-session-[0-9a-f]{24}$")
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


def profile_analysis_request_sha256(extraction: Mapping[str, Any]) -> str:
    """Hash the exact minimal provider request without storing another text copy."""

    request = build_profile_analysis_request(extraction)
    return sha256(
        json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _validate(
    consent: Mapping[str, Any],
) -> tuple[str, datetime, Mapping[str, Any]]:
    if set(consent) != {"profile_analysis_external_consent", "source", "metadata"}:
        raise ProfileDocumentError("외부 분석 동의 기록 필드 구성이 올바르지 않음")
    root = _mapping(
        consent.get("profile_analysis_external_consent"),
        "profile_analysis_external_consent",
    )
    source = _mapping(consent.get("source"), "source")
    metadata = _mapping(consent.get("metadata"), "metadata")
    if set(root) != {"consent_id", "decided_at", "decision", "decision_source"}:
        raise ProfileDocumentError("외부 분석 동의 결정 필드 구성이 올바르지 않음")
    if set(source) != {
        "extraction_id",
        "request_sha256",
        "provider_name",
        "model_name",
        "consent_session_id",
        "team_id",
        "channel_id",
        "user_id",
        "thread_ts",
    }:
        raise ProfileDocumentError("외부 분석 동의 출처 필드 구성이 올바르지 않음")
    consent_id = _identifier(root.get("consent_id"), "consent_id", _CONSENT_ID_PATTERN)
    decided_at_text = root.get("decided_at")
    if not isinstance(decided_at_text, str):
        raise ProfileDocumentError("외부 분석 동의 결정 시간이 없음")
    try:
        decided_at = datetime.fromisoformat(decided_at_text)
    except ValueError as error:
        raise ProfileDocumentError("외부 분석 동의 결정 시간이 올바르지 않음") from error
    if decided_at.tzinfo is None or decided_at.utcoffset() is None:
        raise ProfileDocumentError("외부 분석 동의 결정 시간에 시간대가 필요함")
    if root.get("decision") not in PROFILE_ANALYSIS_EXTERNAL_CONSENT_DECISIONS:
        raise ProfileDocumentError("외부 분석 동의 결정이 올바르지 않음")
    if root.get("decision_source") != "explicit_user_input":
        raise ProfileDocumentError("외부 분석 동의는 명시적 사용자 입력이어야 함")
    extraction_id = _identifier(
        source.get("extraction_id"), "extraction_id", _EXTRACTION_ID_PATTERN
    )
    request_hash = _identifier(
        source.get("request_sha256"), "request_sha256", _HASH_PATTERN
    )
    provider_name = _identifier(
        source.get("provider_name"), "provider_name", _NAME_PATTERN
    )
    model_name = _identifier(source.get("model_name"), "model_name", _NAME_PATTERN)
    consent_session_id = _identifier(
        source.get("consent_session_id"),
        "consent_session_id",
        _SESSION_ID_PATTERN,
    )
    team_id = _identifier(source.get("team_id"), "team_id", _TEAM_ID_PATTERN)
    channel_id = _identifier(
        source.get("channel_id"), "channel_id", _CHANNEL_ID_PATTERN
    )
    user_id = _identifier(source.get("user_id"), "user_id", _USER_ID_PATTERN)
    thread_ts = _identifier(
        source.get("thread_ts"), "thread_ts", _THREAD_TS_PATTERN
    )
    if metadata != {
        "schema_version": PROFILE_ANALYSIS_EXTERNAL_CONSENT_SCHEMA_VERSION,
        "contains_candidate_text": False,
        "contains_personal_data": True,
        "sends_data_externally": True,
        "git_tracking_allowed": False,
        "profile_updated": False,
    }:
        raise ProfileDocumentError("외부 분석 동의 메타데이터가 올바르지 않음")
    identity = "|".join(
        (
            extraction_id,
            request_hash,
            provider_name,
            model_name,
            consent_session_id,
            team_id,
            channel_id,
            user_id,
            thread_ts,
            decided_at_text,
            str(root["decision"]),
        )
    )
    expected_id = "profile-analysis-external-consent-" + sha256(
        identity.encode("utf-8")
    ).hexdigest()[:24]
    if consent_id != expected_id:
        raise ProfileDocumentError("외부 분석 동의 ID와 내용 지문이 일치하지 않음")
    return consent_id, decided_at, source


def validate_profile_analysis_external_consent(
    consent: Mapping[str, Any],
) -> dict[str, Any]:
    _validate(consent)
    return deepcopy(dict(consent))


def build_profile_analysis_external_consent(
    extraction: Mapping[str, Any],
    *,
    provider_name: str,
    model_name: str,
    consent_session_id: str,
    team_id: str,
    channel_id: str,
    user_id: str,
    thread_ts: str,
    decision: str,
    decided_at: datetime,
) -> dict[str, Any]:
    if decided_at.tzinfo is None or decided_at.utcoffset() is None:
        raise ProfileDocumentError("decided_at은 시간대가 포함되어야 함")
    if decision not in PROFILE_ANALYSIS_EXTERNAL_CONSENT_DECISIONS:
        raise ProfileDocumentError("외부 분석 동의 결정이 올바르지 않음")
    request = build_profile_analysis_request(extraction)
    extraction_root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    extraction_id = _identifier(
        extraction_root.get("extraction_id"), "extraction_id", _EXTRACTION_ID_PATTERN
    )
    provider_name = _identifier(provider_name, "provider_name", _NAME_PATTERN)
    model_name = _identifier(model_name, "model_name", _NAME_PATTERN)
    consent_session_id = _identifier(
        consent_session_id, "consent_session_id", _SESSION_ID_PATTERN
    )
    team_id = _identifier(team_id, "team_id", _TEAM_ID_PATTERN)
    channel_id = _identifier(channel_id, "channel_id", _CHANNEL_ID_PATTERN)
    user_id = _identifier(user_id, "user_id", _USER_ID_PATTERN)
    thread_ts = _identifier(thread_ts, "thread_ts", _THREAD_TS_PATTERN)
    request_hash = sha256(
        json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    decided_at_text = decided_at.isoformat(timespec="microseconds")
    identity = "|".join(
        (
            extraction_id,
            request_hash,
            provider_name,
            model_name,
            consent_session_id,
            team_id,
            channel_id,
            user_id,
            thread_ts,
            decided_at_text,
            decision,
        )
    )
    consent = {
        "profile_analysis_external_consent": {
            "consent_id": "profile-analysis-external-consent-"
            + sha256(identity.encode("utf-8")).hexdigest()[:24],
            "decided_at": decided_at_text,
            "decision": decision,
            "decision_source": "explicit_user_input",
        },
        "source": {
            "extraction_id": extraction_id,
            "request_sha256": request_hash,
            "provider_name": provider_name,
            "model_name": model_name,
            "consent_session_id": consent_session_id,
            "team_id": team_id,
            "channel_id": channel_id,
            "user_id": user_id,
            "thread_ts": thread_ts,
        },
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_EXTERNAL_CONSENT_SCHEMA_VERSION,
            "contains_candidate_text": False,
            "contains_personal_data": True,
            "sends_data_externally": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    return validate_profile_analysis_external_consent(consent)


def save_profile_analysis_external_consent(
    consent: Mapping[str, Any], directory: str | Path
) -> Path:
    validated = validate_profile_analysis_external_consent(consent)
    consent_id = validated["profile_analysis_external_consent"]["consent_id"]
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{consent_id}.json"
    if target_path.exists():
        raise ProfileDocumentError("외부 분석 동의 기록이 이미 존재함")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{consent_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(json.dumps(validated, ensure_ascii=False, indent=2) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("외부 분석 동의 기록을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_profile_analysis_external_consent(
    consent_id: str, directory: str | Path
) -> dict[str, Any]:
    consent_id = _identifier(consent_id, "consent_id", _CONSENT_ID_PATTERN)
    path = Path(directory) / f"{consent_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("외부 분석 동의 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("외부 분석 동의 기록을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError("외부 분석 동의 기록 최상위 JSON은 객체여야 함")
    validated = validate_profile_analysis_external_consent(value)
    if validated["profile_analysis_external_consent"]["consent_id"] != consent_id:
        raise ProfileDocumentError("외부 분석 동의 ID가 요청과 일치하지 않음")
    return validated


def select_latest_profile_analysis_external_consent_for_session(
    consent_session_id: str,
    directory: str | Path,
) -> dict[str, Any] | None:
    consent_session_id = _identifier(
        consent_session_id, "consent_session_id", _SESSION_ID_PATTERN
    )
    target_directory = Path(directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("외부 분석 동의 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("profile-analysis-external-consent-*.json"))
    if len(paths) > _MAX_FILES:
        raise ProfileDocumentError("외부 분석 동의 기록이 허용 개수를 초과함")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        consent = load_profile_analysis_external_consent(path.stem, target_directory)
        consent_id, decided_at, source = _validate(consent)
        if source["consent_session_id"] == consent_session_id:
            candidates.append((decided_at, consent_id, consent))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])
