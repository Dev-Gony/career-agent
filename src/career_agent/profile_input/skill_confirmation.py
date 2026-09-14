"""Record user-confirmed details for one new skill candidate."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping, Sequence

from .document_store import ProfileDocumentError
from .skill_mapping import (
    PROFILE_SKILL_MAPPING_RULES_VERSION,
    PROFILE_SKILL_MAPPING_SCHEMA_VERSION,
)


PROFILE_SKILL_CONFIRMATION_SCHEMA_VERSION = "0.1"
SKILL_LEVELS = frozenset(
    {"none", "exposure", "learning", "basic", "project", "work"}
)
MAX_SKILL_EVIDENCE_ITEMS = 10
MAX_SKILL_EVIDENCE_CHARS = 300
MAX_SKILL_CONFIRMATION_NOTES_CHARS = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _skill_mapping_item(
    mapping_proposal: Mapping[str, Any],
    mapping_item_id: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    root = _mapping(
        mapping_proposal.get("profile_skill_mapping"),
        "profile_skill_mapping",
    )
    metadata = _mapping(mapping_proposal.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_SKILL_MAPPING_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 매핑안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("기술 매핑안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("반영되지 않은 기술 매핑안만 확인할 수 있음")
    if root.get("rules_version") != PROFILE_SKILL_MAPPING_RULES_VERSION:
        raise ProfileDocumentError("현재 규칙 버전의 기술 매핑안이 아님")
    if root.get("status") != "needs_confirmation":
        raise ProfileDocumentError("확인할 새 기술 후보가 있는 매핑안이 아님")
    normalized_item_id = _text(mapping_item_id, "mapping_item_id")
    raw_items = mapping_proposal.get("skill_mappings")
    if not isinstance(raw_items, list):
        raise ProfileDocumentError("skill_mappings 배열이 필요함")
    item_ids: set[str] = set()
    matches: list[Mapping[str, Any]] = []
    for position, raw_item in enumerate(raw_items):
        item = _mapping(raw_item, f"skill_mappings[{position}]")
        item_id = _text(
            item.get("mapping_item_id"),
            f"skill_mappings[{position}].mapping_item_id",
        )
        if item_id in item_ids:
            raise ProfileDocumentError(f"중복 기술 매핑 항목 ID: {item_id}")
        item_ids.add(item_id)
        if item_id == normalized_item_id:
            matches.append(item)
    if not matches:
        raise ProfileDocumentError(f"기술 매핑 항목을 찾을 수 없음: {normalized_item_id}")
    item = matches[0]
    if item.get("mapping_status") != "needs_details":
        raise ProfileDocumentError("needs_details 상태인 기술 후보만 확인할 수 있음")
    if item.get("profile_change_ready") is not False:
        raise ProfileDocumentError("프로필 반영 전 기술 후보만 확인할 수 있음")
    _text(item.get("candidate_name"), "skill_mapping.candidate_name")
    if item.get("existing_skill") is not None:
        raise ProfileDocumentError("기존 기술과 중복된 후보는 새 기술로 확인할 수 없음")
    missing_fields = item.get("missing_fields")
    if not isinstance(missing_fields, list) or set(missing_fields) != {
        "level",
        "evidence",
    }:
        raise ProfileDocumentError("기술 후보의 확인 필요 필드가 올바르지 않음")
    return root, item


def _evidence_items(evidence: Sequence[str]) -> list[str]:
    if isinstance(evidence, (str, bytes)) or not isinstance(evidence, Sequence):
        raise ProfileDocumentError("evidence는 문자열 배열이어야 함")
    if not evidence:
        raise ProfileDocumentError("evidence는 최소 1개가 필요함")
    if len(evidence) > MAX_SKILL_EVIDENCE_ITEMS:
        raise ProfileDocumentError(
            f"evidence는 최대 {MAX_SKILL_EVIDENCE_ITEMS}개까지 허용함"
        )
    normalized: list[str] = []
    seen: set[str] = set()
    for position, value in enumerate(evidence):
        text = _text(value, f"evidence[{position}]")
        if len(text) > MAX_SKILL_EVIDENCE_CHARS:
            raise ProfileDocumentError(
                f"evidence[{position}]는 {MAX_SKILL_EVIDENCE_CHARS}자 이하여야 함"
            )
        duplicate_key = text.casefold()
        if duplicate_key in seen:
            raise ProfileDocumentError(f"중복 evidence: {text}")
        seen.add(duplicate_key)
        normalized.append(text)
    return normalized


def build_profile_skill_confirmation(
    mapping_proposal: Mapping[str, Any],
    *,
    mapping_item_id: str,
    level: str,
    evidence: Sequence[str],
    confirmed_at: datetime,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one immutable user confirmation without copying the skill name."""

    if confirmed_at.tzinfo is None or confirmed_at.utcoffset() is None:
        raise ProfileDocumentError("confirmed_at은 시간대가 포함되어야 함")
    if level not in SKILL_LEVELS:
        allowed = ", ".join(sorted(SKILL_LEVELS))
        raise ProfileDocumentError(f"level 허용값: {allowed}")
    normalized_evidence = _evidence_items(evidence)
    normalized_notes = None
    if notes is not None:
        if not isinstance(notes, str):
            raise ProfileDocumentError("notes는 문자열이어야 함")
        normalized_notes = notes.strip() or None
        if (
            normalized_notes is not None
            and len(normalized_notes) > MAX_SKILL_CONFIRMATION_NOTES_CHARS
        ):
            raise ProfileDocumentError(
                f"notes는 {MAX_SKILL_CONFIRMATION_NOTES_CHARS}자 이하여야 함"
            )

    root, item = _skill_mapping_item(mapping_proposal, mapping_item_id)
    mapping_id = _text(root.get("mapping_id"), "profile_skill_mapping.mapping_id")
    source_update_proposal_id = _text(
        root.get("source_update_proposal_id"),
        "profile_skill_mapping.source_update_proposal_id",
    )
    normalized_item_id = _text(item.get("mapping_item_id"), "mapping_item_id")
    source = _mapping(item.get("source"), "skill_mapping.source")
    line_start = source.get("line_start")
    line_end = source.get("line_end")
    for field, value in (("line_start", line_start), ("line_end", line_end)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ProfileDocumentError(f"skill_mapping.source.{field}가 올바르지 않음")
    if line_end < line_start:
        raise ProfileDocumentError("skill_mapping.source 원문 줄 범위가 올바르지 않음")
    confirmed_timestamp = confirmed_at.isoformat(timespec="microseconds")
    confirmation_key = f"{mapping_id}|{normalized_item_id}|{confirmed_timestamp}"
    confirmation_id = "profile-skill-confirmation-" + sha256(
        confirmation_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "profile_skill_confirmation": {
            "confirmation_id": confirmation_id,
            "confirmed_at": confirmed_timestamp,
            "confirmation_source": "explicit_user_input",
            "level": level,
            "evidence": normalized_evidence,
            "notes": normalized_notes,
        },
        "source": {
            "mapping_id": mapping_id,
            "mapping_item_id": normalized_item_id,
            "base_profile_id": _text(
                root.get("base_profile_id"),
                "profile_skill_mapping.base_profile_id",
            ),
            "base_profile_content_sha256": _text(
                root.get("base_profile_content_sha256"),
                "profile_skill_mapping.base_profile_content_sha256",
            ),
            "source_update_proposal_id": source_update_proposal_id,
            "proposal_item_id": _text(
                source.get("proposal_item_id"),
                "skill_mapping.source.proposal_item_id",
            ),
            "candidate_id": _text(
                source.get("candidate_id"),
                "skill_mapping.source.candidate_id",
            ),
            "extraction_id": _text(
                source.get("extraction_id"),
                "skill_mapping.source.extraction_id",
            ),
            "document_id": _text(
                source.get("document_id"),
                "skill_mapping.source.document_id",
            ),
            "line_start": line_start,
            "line_end": line_end,
            "review_id": _text(
                source.get("review_id"),
                "skill_mapping.source.review_id",
            ),
        },
        "metadata": {
            "schema_version": PROFILE_SKILL_CONFIRMATION_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_skill_confirmation(
    confirmation: Mapping[str, Any],
    directory: str | Path,
) -> Path:
    """Atomically save one immutable skill confirmation."""

    root = _mapping(
        confirmation.get("profile_skill_confirmation"),
        "profile_skill_confirmation",
    )
    metadata = _mapping(confirmation.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_SKILL_CONFIRMATION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 확인 기록이 아님")
    if metadata.get("contains_candidate_text") is not False:
        raise ProfileDocumentError("기술 확인 기록에 후보명 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("기술 확인 기록에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("기술 확인 기록은 프로필 갱신 상태일 수 없음")
    confirmation_id = _text(
        root.get("confirmation_id"),
        "profile_skill_confirmation.confirmation_id",
    )
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{confirmation_id}.json"
    if target_path.exists():
        raise ProfileDocumentError(f"기술 확인 파일이 이미 존재함: {target_path}")

    serialized = json.dumps(confirmation, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{confirmation_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError(
            f"기술 확인 기록을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path
