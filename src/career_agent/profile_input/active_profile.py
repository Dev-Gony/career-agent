"""Persist and resolve the latest explicitly activated private profile version."""

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

from .analysis_application import (
    PROFILE_ANALYSIS_APPLICATION_RULES_VERSION,
    PROFILE_ANALYSIS_APPLICATION_SCHEMA_VERSION,
)
from .document_store import ProfileDocumentError
from .update_proposal import profile_content_sha256


PROFILE_ACTIVATION_SCHEMA_VERSION = "0.1"
_ACTIVATION_ID_PATTERN = re.compile(r"^profile-activation-[0-9a-f]{24}$")
_APPLICATION_ID_PATTERN = re.compile(r"^profile-analysis-application-[0-9a-f]{24}$")
_PROFILE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 올바르지 않음")
    return value


def _timestamp(value: Any, name: str) -> tuple[str, datetime]:
    normalized = _text(value, name)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}에 시간대가 필요함")
    return normalized, parsed


def _validated_applied_application(
    application: Mapping[str, Any], updated_profile: Mapping[str, Any]
) -> tuple[str, str]:
    root = _mapping(application.get("profile_analysis_application"), "application")
    metadata = _mapping(application.get("metadata"), "metadata")
    application_id = _text(root.get("application_id"), "application_id")
    if _APPLICATION_ID_PATTERN.fullmatch(application_id) is None:
        raise ProfileDocumentError("활성화할 프로필 적용 ID가 올바르지 않음")
    if root.get("status") != "applied_to_new_version":
        raise ProfileDocumentError("새 버전 적용이 완료된 기록만 활성화할 수 있음")
    if root.get("rules_version") != PROFILE_ANALYSIS_APPLICATION_RULES_VERSION:
        raise ProfileDocumentError("현재 규칙의 프로필 적용 기록이 아님")
    if (
        metadata.get("schema_version") != PROFILE_ANALYSIS_APPLICATION_SCHEMA_VERSION
        or metadata.get("profile_updated") is not True
        or metadata.get("contains_profile_content") is not False
        or metadata.get("git_tracking_allowed") is not False
    ):
        raise ProfileDocumentError("프로필 적용 기록의 데이터 경계가 올바르지 않음")
    output_hash = _text(root.get("output_profile_content_sha256"), "output_profile_content_sha256")
    if _PROFILE_HASH_PATTERN.fullmatch(output_hash) is None or output_hash != profile_content_sha256(updated_profile):
        raise ProfileDocumentError("프로필 적용 기록과 새 프로필 지문이 일치하지 않음")
    expected_id = "profile-analysis-application-" + sha256(
        "|".join(
            (
                _text(root.get("base_profile_content_sha256"), "base_profile_content_sha256"),
                _text(root.get("source_final_proposal_id"), "source_final_proposal_id"),
                _text(root.get("source_final_review_id"), "source_final_review_id"),
                PROFILE_ANALYSIS_APPLICATION_RULES_VERSION,
            )
        ).encode("utf-8")
    ).hexdigest()[:24]
    if application_id != expected_id:
        raise ProfileDocumentError("프로필 적용 ID와 출처 지문이 일치하지 않음")
    return application_id, output_hash


def validate_profile_activation(activation: Mapping[str, Any]) -> dict[str, Any]:
    if set(activation) != {"profile_activation", "source", "metadata"}:
        raise ProfileDocumentError("프로필 활성화 기록 필드 구성이 올바르지 않음")
    root = _mapping(activation.get("profile_activation"), "profile_activation")
    source = _mapping(activation.get("source"), "source")
    metadata = _mapping(activation.get("metadata"), "metadata")
    if set(root) != {"activation_id", "activated_at", "status"} or root.get("status") != "active":
        raise ProfileDocumentError("프로필 활성화 상태가 올바르지 않음")
    if set(source) != {"application_id", "profile_content_sha256"}:
        raise ProfileDocumentError("프로필 활성화 출처 구성이 올바르지 않음")
    activation_id = _text(root.get("activation_id"), "activation_id")
    if _ACTIVATION_ID_PATTERN.fullmatch(activation_id) is None:
        raise ProfileDocumentError("프로필 활성화 ID가 올바르지 않음")
    activated_at_text, _ = _timestamp(root.get("activated_at"), "activated_at")
    application_id = _text(source.get("application_id"), "application_id")
    if _APPLICATION_ID_PATTERN.fullmatch(application_id) is None:
        raise ProfileDocumentError("프로필 활성화 적용 ID가 올바르지 않음")
    output_hash = _text(source.get("profile_content_sha256"), "profile_content_sha256")
    if _PROFILE_HASH_PATTERN.fullmatch(output_hash) is None:
        raise ProfileDocumentError("프로필 활성화 내용 지문이 올바르지 않음")
    if metadata != {
        "schema_version": PROFILE_ACTIVATION_SCHEMA_VERSION,
        "contains_profile_content": False,
        "contains_personal_data": True,
        "git_tracking_allowed": False,
    }:
        raise ProfileDocumentError("프로필 활성화 메타데이터가 올바르지 않음")
    expected_id = "profile-activation-" + sha256(
        "|".join((application_id, output_hash, activated_at_text)).encode("utf-8")
    ).hexdigest()[:24]
    if activation_id != expected_id:
        raise ProfileDocumentError("프로필 활성화 ID와 내용 지문이 일치하지 않음")
    return deepcopy(dict(activation))


def build_profile_activation(
    application: Mapping[str, Any],
    updated_profile: Mapping[str, Any],
    *,
    activated_at: datetime,
) -> dict[str, Any]:
    if activated_at.tzinfo is None or activated_at.utcoffset() is None:
        raise ProfileDocumentError("activated_at은 시간대가 포함되어야 함")
    application_id, output_hash = _validated_applied_application(application, updated_profile)
    activated_at_text = activated_at.isoformat(timespec="microseconds")
    activation_id = "profile-activation-" + sha256(
        "|".join((application_id, output_hash, activated_at_text)).encode("utf-8")
    ).hexdigest()[:24]
    return validate_profile_activation(
        {
            "profile_activation": {
                "activation_id": activation_id,
                "activated_at": activated_at_text,
                "status": "active",
            },
            "source": {
                "application_id": application_id,
                "profile_content_sha256": output_hash,
            },
            "metadata": {
                "schema_version": PROFILE_ACTIVATION_SCHEMA_VERSION,
                "contains_profile_content": False,
                "contains_personal_data": True,
                "git_tracking_allowed": False,
            },
        }
    )


def save_profile_activation(activation: Mapping[str, Any], directory: str | Path) -> Path:
    validated = validate_profile_activation(activation)
    activation_id = validated["profile_activation"]["activation_id"]
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{activation_id}.json"
    if target_path.exists():
        raise ProfileDocumentError("프로필 활성화 기록이 이미 존재함")
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=target_directory, prefix=f".{activation_id}.", suffix=".tmp", delete=False) as temporary_file:
            temporary_file.write(json.dumps(validated, ensure_ascii=False, indent=2) + "\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("프로필 활성화 기록을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def resolve_active_profile_path(
    activation_directory: str | Path,
    application_directory: str | Path,
) -> Path | None:
    """Resolve the newest verified activation to a fixed private profile path."""

    activation_root = Path(activation_directory)
    if not activation_root.exists():
        return None
    if not activation_root.is_dir() or activation_root.is_symlink():
        raise ProfileDocumentError("프로필 활성화 경로가 안전한 디렉터리가 아님")
    paths = sorted(activation_root.glob("profile-activation-*.json"))
    if len(paths) > _MAX_FILES:
        raise ProfileDocumentError("프로필 활성화 기록이 허용 개수를 초과함")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        if path.is_symlink():
            raise ProfileDocumentError("프로필 활성화 심볼릭 링크는 읽을 수 없음")
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError("프로필 활성화 기록을 읽을 수 없음") from error
        if not isinstance(value, dict):
            raise ProfileDocumentError("프로필 활성화 기록 최상위 JSON은 객체여야 함")
        activation = validate_profile_activation(value)
        root = activation["profile_activation"]
        _, activated_at = _timestamp(root["activated_at"], "activated_at")
        candidates.append((activated_at, str(root["activation_id"]), activation))
    if not candidates:
        return None
    activation = max(candidates, key=lambda value: (value[0], value[1]))[2]
    source = activation["source"]
    application_id = source["application_id"]
    application_root = Path(application_directory)
    target_directory = application_root / application_id
    application_path = target_directory / "application.json"
    profile_path = target_directory / "profile.json"
    if (
        target_directory.is_symlink()
        or application_path.is_symlink()
        or profile_path.is_symlink()
    ):
        raise ProfileDocumentError("활성 프로필 경로에 심볼릭 링크를 사용할 수 없음")
    try:
        application = json.loads(application_path.read_text(encoding="utf-8"))
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("활성 프로필 적용 결과를 읽을 수 없음") from error
    if not isinstance(application, dict) or not isinstance(profile, dict):
        raise ProfileDocumentError("활성 프로필 적용 결과 형식이 올바르지 않음")
    verified_id, verified_hash = _validated_applied_application(application, profile)
    if verified_id != application_id or verified_hash != source["profile_content_sha256"]:
        raise ProfileDocumentError("활성 프로필 기록과 적용 결과가 일치하지 않음")
    return profile_path.resolve()
