"""Build complete but unapplied skill additions from confirmed candidates."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Iterable, Mapping

from .document_store import ProfileDocumentError
from .skill_confirmation import (
    MAX_SKILL_CONFIRMATION_NOTES_CHARS,
    MAX_SKILL_EVIDENCE_CHARS,
    MAX_SKILL_EVIDENCE_ITEMS,
    PROFILE_SKILL_CONFIRMATION_SCHEMA_VERSION,
    SKILL_LEVELS,
)
from .skill_mapping import (
    PROFILE_SKILL_MAPPING_RULES_VERSION,
    PROFILE_SKILL_MAPPING_SCHEMA_VERSION,
    normalize_skill_name,
)
from .update_proposal import profile_content_sha256


PROFILE_SKILL_ADDITION_SCHEMA_VERSION = "0.1"
PROFILE_SKILL_ADDITION_RULES_VERSION = "0.1"
_MAPPING_STATUSES = frozenset(
    {"no_skill_candidates", "duplicate_only", "needs_confirmation"}
)
_ITEM_STATUSES = frozenset(
    {"duplicate_existing", "needs_details", "needs_separation"}
)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _timestamp(value: Any, name: str) -> tuple[float, str]:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}은 시간대가 포함되어야 함")
    return parsed.timestamp(), text


def _profile_skill_index(profile: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    raw_skills = profile.get("skills", [])
    if not isinstance(raw_skills, list):
        raise ProfileDocumentError("profile.skills 배열이 필요함")
    names: set[str] = set()
    identifiers: set[str] = set()
    for position, raw_skill in enumerate(raw_skills):
        skill = _mapping(raw_skill, f"profile.skills[{position}]")
        skill_id = _text(skill.get("skill_id"), f"profile.skills[{position}].skill_id")
        name = _text(skill.get("name"), f"profile.skills[{position}].name")
        normalized_name = normalize_skill_name(name)
        if skill_id in identifiers:
            raise ProfileDocumentError(f"중복 skill_id: {skill_id}")
        if normalized_name in names:
            raise ProfileDocumentError(f"중복 기술명: {name}")
        identifiers.add(skill_id)
        names.add(normalized_name)
    return names, identifiers


def _mapping_item_index(
    mapping_proposal: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]], dict[str, int]]:
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
        raise ProfileDocumentError("반영되지 않은 기술 매핑안만 사용할 수 있음")
    if root.get("rules_version") != PROFILE_SKILL_MAPPING_RULES_VERSION:
        raise ProfileDocumentError("현재 규칙 버전의 기술 매핑안이 아님")
    if root.get("status") not in _MAPPING_STATUSES:
        raise ProfileDocumentError("기술 매핑안 상태가 올바르지 않음")
    raw_items = mapping_proposal.get("skill_mappings")
    if not isinstance(raw_items, list):
        raise ProfileDocumentError("skill_mappings 배열이 필요함")

    item_index: dict[str, Mapping[str, Any]] = {}
    status_counts = {status: 0 for status in _ITEM_STATUSES}
    new_names: set[str] = set()
    candidate_ids: set[str] = set()
    for position, raw_item in enumerate(raw_items):
        item = _mapping(raw_item, f"skill_mappings[{position}]")
        item_id = _text(
            item.get("mapping_item_id"),
            f"skill_mappings[{position}].mapping_item_id",
        )
        if item_id in item_index:
            raise ProfileDocumentError(f"중복 기술 매핑 항목 ID: {item_id}")
        status = item.get("mapping_status")
        if status not in _ITEM_STATUSES:
            raise ProfileDocumentError(
                f"skill_mappings[{position}].mapping_status가 올바르지 않음"
            )
        if item.get("profile_change_ready") is not False:
            raise ProfileDocumentError(
                f"skill_mappings[{position}]는 프로필 반영 전 상태여야 함"
            )
        _text(
            item.get("candidate_text"),
            f"skill_mappings[{position}].candidate_text",
        )
        source = _mapping(item.get("source"), f"skill_mappings[{position}].source")
        for field in (
            "proposal_item_id",
            "candidate_id",
            "extraction_id",
            "document_id",
            "review_id",
        ):
            _text(source.get(field), f"skill_mappings[{position}].source.{field}")
        candidate_id = source["candidate_id"].strip()
        if candidate_id in candidate_ids:
            raise ProfileDocumentError(f"중복 기술 후보 참조: {candidate_id}")
        candidate_ids.add(candidate_id)
        for field in ("line_start", "line_end"):
            value = source.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProfileDocumentError(
                    f"skill_mappings[{position}].source.{field}가 올바르지 않음"
                )
        if source["line_end"] < source["line_start"]:
            raise ProfileDocumentError(
                f"skill_mappings[{position}]의 원문 줄 범위가 올바르지 않음"
            )
        if status == "needs_details":
            name = _text(
                item.get("candidate_name"),
                f"skill_mappings[{position}].candidate_name",
            )
            normalized_name = normalize_skill_name(name)
            if normalized_name in new_names:
                raise ProfileDocumentError(f"중복 새 기술 후보명: {name}")
            new_names.add(normalized_name)
            if item.get("existing_skill") is not None:
                raise ProfileDocumentError("새 기술 후보에 기존 기술 참조가 있음")
            if set(item.get("missing_fields", [])) != {"level", "evidence"}:
                raise ProfileDocumentError("새 기술 후보의 확인 필요 필드가 올바르지 않음")
        elif status == "duplicate_existing":
            _text(
                item.get("candidate_name"),
                f"skill_mappings[{position}].candidate_name",
            )
            existing_skill = _mapping(
                item.get("existing_skill"),
                f"skill_mappings[{position}].existing_skill",
            )
            _text(
                existing_skill.get("skill_id"),
                f"skill_mappings[{position}].existing_skill.skill_id",
            )
            _text(
                existing_skill.get("name"),
                f"skill_mappings[{position}].existing_skill.name",
            )
            if item.get("missing_fields") != []:
                raise ProfileDocumentError("중복 기술 후보에 확인 필요 필드가 있음")
        else:
            if item.get("candidate_name") is not None:
                raise ProfileDocumentError("분리 필요 기술 후보에 단일 기술명이 있음")
            if item.get("existing_skill") is not None:
                raise ProfileDocumentError("분리 필요 기술 후보에 기존 기술 참조가 있음")
            if set(item.get("missing_fields", [])) != {
                "individual_skill_names",
                "level",
                "evidence",
            }:
                raise ProfileDocumentError("분리 필요 기술 후보의 필드가 올바르지 않음")
        status_counts[status] += 1
        item_index[item_id] = item
    if not raw_items:
        expected_status = "no_skill_candidates"
    elif status_counts["needs_details"] or status_counts["needs_separation"]:
        expected_status = "needs_confirmation"
    else:
        expected_status = "duplicate_only"
    if root.get("status") != expected_status:
        raise ProfileDocumentError("기술 매핑안 상태가 항목 구성과 일치하지 않음")
    if metadata.get("contains_candidate_text") is not bool(raw_items):
        raise ProfileDocumentError("기술 매핑안의 후보 문장 포함 표시가 내용과 다름")
    return root, item_index, status_counts


def _validated_evidence(value: Any, position: int) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ProfileDocumentError(f"confirmations[{position}].evidence 배열이 필요함")
    if len(value) > MAX_SKILL_EVIDENCE_ITEMS:
        raise ProfileDocumentError(f"confirmations[{position}].evidence가 너무 많음")
    normalized: list[str] = []
    seen: set[str] = set()
    for evidence_position, raw_text in enumerate(value):
        text = _text(
            raw_text,
            f"confirmations[{position}].evidence[{evidence_position}]",
        )
        if len(text) > MAX_SKILL_EVIDENCE_CHARS:
            raise ProfileDocumentError(
                f"confirmations[{position}].evidence[{evidence_position}]가 너무 김"
            )
        if text != raw_text:
            raise ProfileDocumentError(
                f"confirmations[{position}].evidence[{evidence_position}]가 정규화되지 않음"
            )
        duplicate_key = text.casefold()
        if duplicate_key in seen:
            raise ProfileDocumentError(f"confirmations[{position}]에 중복 evidence가 있음")
        seen.add(duplicate_key)
        normalized.append(text)
    return normalized


def _latest_confirmations(
    confirmations: Iterable[Mapping[str, Any]],
    *,
    mapping_root: Mapping[str, Any],
    mapping_items: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    mapping_id = _text(mapping_root.get("mapping_id"), "profile_skill_mapping.mapping_id")
    latest: dict[str, tuple[tuple[float, str], dict[str, Any]]] = {}
    for position, raw_confirmation in enumerate(confirmations):
        confirmation = _mapping(raw_confirmation, f"confirmations[{position}]")
        root = _mapping(
            confirmation.get("profile_skill_confirmation"),
            f"confirmations[{position}].profile_skill_confirmation",
        )
        source = _mapping(confirmation.get("source"), f"confirmations[{position}].source")
        metadata = _mapping(
            confirmation.get("metadata"),
            f"confirmations[{position}].metadata",
        )
        if metadata.get("schema_version") != PROFILE_SKILL_CONFIRMATION_SCHEMA_VERSION:
            raise ProfileDocumentError(f"confirmations[{position}]의 스키마 버전이 다름")
        if metadata.get("contains_candidate_text") is not False:
            raise ProfileDocumentError(f"confirmations[{position}]에 후보명 제외 표시가 없음")
        if metadata.get("git_tracking_allowed") is not False:
            raise ProfileDocumentError(f"confirmations[{position}]에 Git 제외 표시가 없음")
        if metadata.get("profile_updated") is not False:
            raise ProfileDocumentError(f"confirmations[{position}]는 반영 전 기록이어야 함")
        confirmation_id = _text(
            root.get("confirmation_id"),
            f"confirmations[{position}].confirmation_id",
        )
        confirmed_order = _timestamp(
            root.get("confirmed_at"),
            f"confirmations[{position}].confirmed_at",
        )
        if root.get("confirmation_source") != "explicit_user_input":
            raise ProfileDocumentError(f"confirmations[{position}]가 명시적 사용자 확인이 아님")
        level = root.get("level")
        if level not in SKILL_LEVELS:
            raise ProfileDocumentError(f"confirmations[{position}].level이 올바르지 않음")
        evidence = _validated_evidence(root.get("evidence"), position)
        notes = root.get("notes")
        if notes is not None:
            notes = _text(notes, f"confirmations[{position}].notes")
            if len(notes) > MAX_SKILL_CONFIRMATION_NOTES_CHARS:
                raise ProfileDocumentError(f"confirmations[{position}].notes가 너무 김")
        confirmation_mapping_id = _text(
            source.get("mapping_id"),
            f"confirmations[{position}].source.mapping_id",
        )
        item_id = _text(
            source.get("mapping_item_id"),
            f"confirmations[{position}].source.mapping_item_id",
        )
        expected_id = "profile-skill-confirmation-" + sha256(
            f"{confirmation_mapping_id}|{item_id}|{confirmed_order[1]}".encode("utf-8")
        ).hexdigest()[:24]
        if confirmation_id != expected_id:
            raise ProfileDocumentError(f"confirmations[{position}]의 확인 ID가 참조와 다름")
        if confirmation_mapping_id != mapping_id:
            continue
        item = mapping_items.get(item_id)
        if item is None:
            raise ProfileDocumentError(
                f"confirmations[{position}]가 없는 매핑 항목을 참조함: {item_id}"
            )
        if item.get("mapping_status") != "needs_details":
            raise ProfileDocumentError(
                f"confirmations[{position}]가 확인 대상이 아닌 항목을 참조함"
            )
        item_source = _mapping(item.get("source"), f"skill_mapping[{item_id}].source")
        expected_source = {
            "mapping_id": mapping_id,
            "mapping_item_id": item_id,
            "base_profile_id": mapping_root.get("base_profile_id"),
            "base_profile_content_sha256": mapping_root.get(
                "base_profile_content_sha256"
            ),
            "source_update_proposal_id": mapping_root.get(
                "source_update_proposal_id"
            ),
            "proposal_item_id": item_source.get("proposal_item_id"),
            "candidate_id": item_source.get("candidate_id"),
            "extraction_id": item_source.get("extraction_id"),
            "document_id": item_source.get("document_id"),
            "line_start": item_source.get("line_start"),
            "line_end": item_source.get("line_end"),
            "review_id": item_source.get("review_id"),
        }
        if any(source.get(key) != value for key, value in expected_source.items()):
            raise ProfileDocumentError(f"confirmations[{position}]의 원문 참조가 매핑안과 다름")
        value = {
            "confirmation_id": confirmation_id,
            "confirmed_at": confirmed_order[1],
            "level": level,
            "evidence": evidence,
            "notes": notes,
        }
        ordering = (confirmed_order[0], confirmation_id)
        existing = latest.get(item_id)
        if existing is None or ordering > existing[0]:
            latest[item_id] = (ordering, value)
    return {item_id: value for item_id, (_, value) in latest.items()}


def build_profile_skill_addition_proposal(
    profile_document: Mapping[str, Any],
    mapping_proposal: Mapping[str, Any],
    confirmations: Iterable[Mapping[str, Any]],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    """Build complete skill objects that still require final review."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProfileDocumentError("created_at은 시간대가 포함되어야 함")
    profile = _mapping(profile_document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")
    mapping_root, mapping_items, status_counts = _mapping_item_index(mapping_proposal)
    if mapping_root.get("base_profile_id") != profile_id:
        raise ProfileDocumentError("기술 매핑안의 기준 profile_id가 현재 프로필과 다름")
    current_hash = profile_content_sha256(profile_document)
    if mapping_root.get("base_profile_content_sha256") != current_hash:
        raise ProfileDocumentError("기술 매핑안 생성 뒤 프로필 내용이 변경됨")
    existing_names, existing_ids = _profile_skill_index(profile)
    latest = _latest_confirmations(
        confirmations,
        mapping_root=mapping_root,
        mapping_items=mapping_items,
    )

    additions: list[dict[str, Any]] = []
    proposed_names: set[str] = set()
    for item_id, item in mapping_items.items():
        if item.get("mapping_status") != "needs_details" or item_id not in latest:
            continue
        name = _text(item.get("candidate_name"), f"skill_mapping[{item_id}].candidate_name")
        normalized_name = normalize_skill_name(name)
        if normalized_name in existing_names:
            raise ProfileDocumentError(f"확인된 새 기술이 기존 기술과 중복됨: {name}")
        if normalized_name in proposed_names:
            raise ProfileDocumentError(f"완성 기술 추가안에 중복 기술명이 있음: {name}")
        proposed_names.add(normalized_name)
        confirmation = latest[item_id]
        skill_id = "skill-import-" + sha256(
            f"{mapping_root['mapping_id']}|{item_id}|{normalized_name}".encode("utf-8")
        ).hexdigest()[:12]
        if skill_id in existing_ids:
            raise ProfileDocumentError(f"생성된 skill_id가 기존 프로필과 중복됨: {skill_id}")
        item_source = _mapping(item.get("source"), f"skill_mapping[{item_id}].source")
        additions.append(
            {
                "addition_item_id": f"skill-addition-item-{len(additions) + 1:03d}",
                "proposed_skill": {
                    "skill_id": skill_id,
                    "name": name,
                    "level": confirmation["level"],
                    "evidence": confirmation["evidence"],
                    "notes": confirmation["notes"],
                },
                "source": {
                    "mapping_item_id": item_id,
                    "proposal_item_id": item_source["proposal_item_id"],
                    "candidate_id": item_source["candidate_id"],
                    "extraction_id": item_source["extraction_id"],
                    "document_id": item_source["document_id"],
                    "line_start": item_source["line_start"],
                    "line_end": item_source["line_end"],
                    "review_id": item_source["review_id"],
                    "confirmation_id": confirmation["confirmation_id"],
                },
                "application_status": "needs_final_review",
            }
        )

    mapping_id = _text(mapping_root.get("mapping_id"), "profile_skill_mapping.mapping_id")
    proposal_key_parts = [
        mapping_id,
        current_hash,
        PROFILE_SKILL_ADDITION_RULES_VERSION,
    ]
    for item_id in sorted(latest):
        confirmation_signature = sha256(
            json.dumps(
                latest[item_id],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        proposal_key_parts.append(f"{item_id}:{confirmation_signature}")
    addition_proposal_id = "profile-skill-addition-" + sha256(
        "|".join(proposal_key_parts).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "profile_skill_addition": {
            "proposal_id": addition_proposal_id,
            "created_at": created_at.isoformat(timespec="microseconds"),
            "status": "needs_final_review" if additions else "no_confirmed_skills",
            "base_profile_id": profile_id,
            "base_profile_content_sha256": current_hash,
            "source_mapping_id": mapping_id,
            "rules_version": PROFILE_SKILL_ADDITION_RULES_VERSION,
        },
        "summary": {
            "new_skill_candidate_count": status_counts["needs_details"],
            "confirmed_skill_count": len(additions),
            "unconfirmed_skill_count": (
                status_counts["needs_details"] - len(additions)
            ),
            "duplicate_existing_count": status_counts["duplicate_existing"],
            "needs_separation_count": status_counts["needs_separation"],
        },
        "skill_additions": additions,
        "analysis_notes": {
            "facts": [
                "기술 후보별 가장 최근 명시적 사용자 확인만 사용함",
                "확인이 끝난 새 기술 후보만 완성된 기술 객체로 구성함",
            ],
            "unknowns": ["완성된 기술 추가안의 최종 적용 여부는 아직 확인하지 않음"],
        },
        "metadata": {
            "schema_version": PROFILE_SKILL_ADDITION_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": bool(additions),
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_skill_addition_proposal(
    proposal: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse an identical skill addition proposal."""

    root = _mapping(proposal.get("profile_skill_addition"), "profile_skill_addition")
    metadata = _mapping(proposal.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_SKILL_ADDITION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 추가안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("기술 추가안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("기술 추가안은 프로필 갱신 상태일 수 없음")
    proposal_id = _text(root.get("proposal_id"), "profile_skill_addition.proposal_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{proposal_id}.json"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError(
                f"기존 기술 추가안을 읽을 수 없음: {target_path}"
            ) from error
        for field in ("summary", "skill_additions", "analysis_notes", "metadata"):
            if existing.get(field) != proposal.get(field):
                raise ProfileDocumentError(
                    f"같은 기술 추가안 ID의 기존 내용이 일치하지 않음: {field}"
                )
        existing_root = _mapping(
            existing.get("profile_skill_addition"), "profile_skill_addition"
        )
        for field in (
            "proposal_id",
            "status",
            "base_profile_id",
            "base_profile_content_sha256",
            "source_mapping_id",
            "rules_version",
        ):
            if existing_root.get(field) != root.get(field):
                raise ProfileDocumentError(
                    f"같은 기술 추가안 ID의 기존 메타데이터가 일치하지 않음: {field}"
                )
        return target_path, False

    serialized = json.dumps(proposal, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{proposal_id}.",
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
            f"기술 추가안을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True
