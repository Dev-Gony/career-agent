"""Map approved skill candidates without mutating the user profile."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
import unicodedata

from .document_store import ProfileDocumentError
from .update_proposal import (
    PROFILE_UPDATE_PROPOSAL_SCHEMA_VERSION,
    profile_content_sha256,
)


PROFILE_SKILL_MAPPING_SCHEMA_VERSION = "0.1"
PROFILE_SKILL_MAPPING_RULES_VERSION = "0.1"
_SKILL_MAPPING_ID_PATTERN = re.compile(r"^profile-skill-mapping-[0-9a-f]{24}$")
_COMPOSITE_SKILL_PATTERN = re.compile(r"[,;|·]")
_UPDATE_PROPOSAL_ID_PATTERN = re.compile(
    r"^profile-update-proposal-[0-9a-f]{24}$"
)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def normalize_skill_name(value: str) -> str:
    """Normalize a skill name for conservative exact comparison."""

    normalized = unicodedata.normalize("NFKC", value)
    return " ".join(normalized.casefold().split())


def _existing_skills(profile: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    raw_skills = profile.get("skills", [])
    if not isinstance(raw_skills, list):
        raise ProfileDocumentError("profile.skills 배열이 필요함")
    skills: dict[str, dict[str, str]] = {}
    skill_ids: set[str] = set()
    for position, raw_skill in enumerate(raw_skills):
        skill = _mapping(raw_skill, f"profile.skills[{position}]")
        skill_id = _text(skill.get("skill_id"), f"profile.skills[{position}].skill_id")
        name = _text(skill.get("name"), f"profile.skills[{position}].name")
        normalized_name = normalize_skill_name(name)
        if skill_id in skill_ids:
            raise ProfileDocumentError(f"중복 skill_id: {skill_id}")
        if normalized_name in skills:
            raise ProfileDocumentError(f"중복 기술명: {name}")
        skill_ids.add(skill_id)
        skills[normalized_name] = {"skill_id": skill_id, "name": name}
    return skills


def _validated_additions(
    proposal: Mapping[str, Any],
    *,
    source_proposal_id: str,
    source_extraction_id: str,
) -> list[Mapping[str, Any]]:
    summary = _mapping(proposal.get("summary"), "summary")
    additions = proposal.get("proposed_additions")
    if not isinstance(additions, list):
        raise ProfileDocumentError("proposed_additions 배열이 필요함")
    approved_count = summary.get("approved_count")
    if isinstance(approved_count, bool) or not isinstance(approved_count, int):
        raise ProfileDocumentError("summary.approved_count 정수가 필요함")
    if approved_count != len(additions):
        raise ProfileDocumentError("승인 후보 수와 proposed_additions가 일치하지 않음")

    proposal_item_ids: set[str] = set()
    candidate_ids: set[str] = set()
    validated: list[Mapping[str, Any]] = []
    for position, raw_addition in enumerate(additions):
        addition = _mapping(raw_addition, f"proposed_additions[{position}]")
        item_id = _text(
            addition.get("proposal_item_id"),
            f"proposed_additions[{position}].proposal_item_id",
        )
        if item_id in proposal_item_ids:
            raise ProfileDocumentError(f"중복 proposal_item_id: {item_id}")
        proposal_item_ids.add(item_id)
        if addition.get("mapping_status") != "needs_mapping":
            raise ProfileDocumentError(
                f"proposed_additions[{position}].mapping_status가 올바르지 않음"
            )
        _text(
            addition.get("profile_section"),
            f"proposed_additions[{position}].profile_section",
        )
        _text(
            addition.get("candidate_text"),
            f"proposed_additions[{position}].candidate_text",
        )
        evidence = _mapping(
            addition.get("source_evidence"),
            f"proposed_additions[{position}].source_evidence",
        )
        if evidence.get("extraction_id") != source_extraction_id:
            raise ProfileDocumentError(
                f"proposed_additions[{position}]의 추출 결과 참조가 다름"
            )
        candidate_id = _text(
            evidence.get("candidate_id"),
            f"proposed_additions[{position}].source_evidence.candidate_id",
        )
        if candidate_id in candidate_ids:
            raise ProfileDocumentError(f"중복 후보 참조: {candidate_id}")
        candidate_ids.add(candidate_id)
        _text(
            evidence.get("document_id"),
            f"proposed_additions[{position}].source_evidence.document_id",
        )
        for field in ("line_start", "line_end"):
            value = evidence.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProfileDocumentError(
                    f"proposed_additions[{position}].source_evidence.{field}가 올바르지 않음"
                )
        if evidence["line_end"] < evidence["line_start"]:
            raise ProfileDocumentError(
                f"proposed_additions[{position}]의 원문 줄 범위가 올바르지 않음"
            )
        approval = _mapping(
            addition.get("approval"),
            f"proposed_additions[{position}].approval",
        )
        _text(
            approval.get("review_id"),
            f"proposed_additions[{position}].approval.review_id",
        )
        _text(
            approval.get("reviewed_at"),
            f"proposed_additions[{position}].approval.reviewed_at",
        )
        if approval.get("decision") != "approve":
            raise ProfileDocumentError(
                f"proposed_additions[{position}]에 승인 결정이 없음"
            )
        validated.append(addition)

    metadata = _mapping(proposal.get("metadata"), "metadata")
    if metadata.get("contains_candidate_text") is not bool(additions):
        raise ProfileDocumentError("갱신안의 후보 문장 포함 표시가 실제 내용과 다름")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("반영되지 않은 갱신안만 매핑할 수 있음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("갱신안에 Git 제외 표시가 없음")
    if metadata.get("schema_version") != PROFILE_UPDATE_PROPOSAL_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 갱신안이 아님")
    if _UPDATE_PROPOSAL_ID_PATTERN.fullmatch(source_proposal_id) is None:
        raise ProfileDocumentError("source proposal ID가 올바르지 않음")
    expected_status = "needs_mapping" if additions else "no_approved_candidates"
    root = _mapping(
        proposal.get("profile_update_proposal"),
        "profile_update_proposal",
    )
    if root.get("status") != expected_status:
        raise ProfileDocumentError("갱신안 상태가 승인 후보 수와 일치하지 않음")
    return validated


def build_profile_skill_mapping_proposal(
    profile_document: Mapping[str, Any],
    update_proposal: Mapping[str, Any],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    """Build a skill-only mapping proposal without creating skill objects."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProfileDocumentError("created_at은 시간대가 포함되어야 함")
    profile = _mapping(profile_document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")
    root = _mapping(
        update_proposal.get("profile_update_proposal"),
        "profile_update_proposal",
    )
    proposal_id = _text(root.get("proposal_id"), "profile_update_proposal.proposal_id")
    source_extraction_id = _text(
        root.get("source_extraction_id"),
        "profile_update_proposal.source_extraction_id",
    )
    if root.get("base_profile_id") != profile_id:
        raise ProfileDocumentError("갱신안의 기준 profile_id가 현재 프로필과 다름")
    current_profile_hash = profile_content_sha256(profile_document)
    if root.get("base_profile_content_sha256") != current_profile_hash:
        raise ProfileDocumentError("갱신안 생성 뒤 프로필 내용이 변경됨")
    additions = _validated_additions(
        update_proposal,
        source_proposal_id=proposal_id,
        source_extraction_id=source_extraction_id,
    )
    existing_skills = _existing_skills(profile)

    mappings: list[dict[str, Any]] = []
    skipped_non_skill_count = 0
    for addition in additions:
        if addition["profile_section"] != "skills":
            skipped_non_skill_count += 1
            continue
        candidate_text = addition["candidate_text"].strip()
        normalized_name = normalize_skill_name(candidate_text)
        existing = existing_skills.get(normalized_name)
        if existing is not None:
            mapping_status = "duplicate_existing"
            candidate_name: str | None = candidate_text
            missing_fields: list[str] = []
        elif _COMPOSITE_SKILL_PATTERN.search(candidate_text):
            mapping_status = "needs_separation"
            candidate_name = None
            missing_fields = ["individual_skill_names", "level", "evidence"]
        else:
            mapping_status = "needs_details"
            candidate_name = candidate_text
            missing_fields = ["level", "evidence"]
        evidence = addition["source_evidence"]
        approval = addition["approval"]
        mappings.append(
            {
                "mapping_item_id": f"skill-mapping-item-{len(mappings) + 1:03d}",
                "source": {
                    "proposal_item_id": addition["proposal_item_id"],
                    "candidate_id": evidence["candidate_id"],
                    "extraction_id": evidence["extraction_id"],
                    "document_id": evidence["document_id"],
                    "line_start": evidence["line_start"],
                    "line_end": evidence["line_end"],
                    "review_id": approval["review_id"],
                },
                "candidate_text": candidate_text,
                "candidate_name": candidate_name,
                "mapping_status": mapping_status,
                "existing_skill": existing,
                "missing_fields": missing_fields,
                "profile_change_ready": False,
            }
        )

    duplicate_count = sum(
        item["mapping_status"] == "duplicate_existing" for item in mappings
    )
    needs_details_count = sum(
        item["mapping_status"] == "needs_details" for item in mappings
    )
    needs_separation_count = sum(
        item["mapping_status"] == "needs_separation" for item in mappings
    )
    if not mappings:
        status = "no_skill_candidates"
    elif needs_details_count or needs_separation_count:
        status = "needs_confirmation"
    else:
        status = "duplicate_only"
    mapping_key = f"{proposal_id}|{current_profile_hash}|{PROFILE_SKILL_MAPPING_RULES_VERSION}"
    mapping_id = "profile-skill-mapping-" + sha256(
        mapping_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "profile_skill_mapping": {
            "mapping_id": mapping_id,
            "created_at": created_at.isoformat(timespec="microseconds"),
            "status": status,
            "base_profile_id": profile_id,
            "base_profile_content_sha256": current_profile_hash,
            "source_update_proposal_id": proposal_id,
            "rules_version": PROFILE_SKILL_MAPPING_RULES_VERSION,
        },
        "summary": {
            "approved_candidate_count": len(additions),
            "skill_candidate_count": len(mappings),
            "duplicate_existing_count": duplicate_count,
            "needs_details_count": needs_details_count,
            "needs_separation_count": needs_separation_count,
            "skipped_non_skill_count": skipped_non_skill_count,
        },
        "skill_mappings": mappings,
        "analysis_notes": {
            "facts": [
                "기술명은 Unicode 정규화, 대소문자와 연속 공백만 정리해 비교함",
                "기존 기술과 정확히 일치한 후보는 새 기술로 추가하지 않음",
            ],
            "unknowns": [
                "새 기술 후보의 숙련도와 실제 사용 증거는 사용자 확인이 필요함",
                "복합 기술 문장은 개별 기술명 분리가 필요함",
            ],
        },
        "metadata": {
            "schema_version": PROFILE_SKILL_MAPPING_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": bool(mappings),
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_skill_mapping_proposal(
    mapping_proposal: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse an identical skill mapping proposal."""

    root = _mapping(mapping_proposal.get("profile_skill_mapping"), "profile_skill_mapping")
    metadata = _mapping(mapping_proposal.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_SKILL_MAPPING_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 매핑안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("기술 매핑안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("기술 매핑안은 프로필 갱신 상태일 수 없음")
    mapping_id = _text(root.get("mapping_id"), "profile_skill_mapping.mapping_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{mapping_id}.json"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError(
                f"기존 기술 매핑안을 읽을 수 없음: {target_path}"
            ) from error
        for field in ("summary", "skill_mappings", "analysis_notes", "metadata"):
            if existing.get(field) != mapping_proposal.get(field):
                raise ProfileDocumentError(
                    f"같은 기술 매핑 ID의 기존 내용이 일치하지 않음: {field}"
                )
        existing_root = _mapping(
            existing.get("profile_skill_mapping"), "profile_skill_mapping"
        )
        for field in (
            "mapping_id",
            "status",
            "base_profile_id",
            "base_profile_content_sha256",
            "source_update_proposal_id",
            "rules_version",
        ):
            if existing_root.get(field) != root.get(field):
                raise ProfileDocumentError(
                    f"같은 기술 매핑 ID의 기존 메타데이터가 일치하지 않음: {field}"
                )
        return target_path, False

    serialized = json.dumps(mapping_proposal, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{mapping_id}.",
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
            f"기술 매핑안을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def load_profile_skill_mapping_proposal(
    mapping_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load one private skill mapping proposal without path traversal."""

    normalized_id = _text(mapping_id, "mapping_id")
    if _SKILL_MAPPING_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("mapping_id 형식이 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    try:
        mapping_proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(
            f"프로필 기술 매핑안을 읽을 수 없음: {path}"
        ) from error
    if not isinstance(mapping_proposal, dict):
        raise ProfileDocumentError("프로필 기술 매핑안 최상위 JSON은 객체여야 함")
    root = _mapping(
        mapping_proposal.get("profile_skill_mapping"),
        "profile_skill_mapping",
    )
    metadata = _mapping(mapping_proposal.get("metadata"), "metadata")
    if root.get("mapping_id") != normalized_id:
        raise ProfileDocumentError("기술 매핑안의 mapping_id가 요청과 일치하지 않음")
    if metadata.get("schema_version") != PROFILE_SKILL_MAPPING_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 매핑안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("기술 매핑안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("기술 매핑안은 프로필 갱신 상태일 수 없음")
    return mapping_proposal
