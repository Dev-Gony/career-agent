"""Project a review-only analysis draft into a private search-only profile."""

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

from .analysis_draft import validate_profile_analysis_draft
from .document_store import ProfileDocumentError
from .update_proposal import profile_content_sha256


PROVISIONAL_SEARCH_PROFILE_SCHEMA_VERSION = "0.1"
PROVISIONAL_SEARCH_PROFILE_RULES_VERSION = "draft-evidence-v1"

_PROJECTION_ID_PATTERN = re.compile(r"^provisional-search-profile-[0-9a-f]{24}$")
_MAX_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _aware_datetime(value: Any, name: str) -> datetime:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}에 시간대가 필요함")
    return parsed


def _normalized_skill_name(value: str) -> str:
    return " ".join(value.casefold().split())


def _provisional_skill_id(draft_id: str, name: str) -> str:
    digest = sha256(
        f"{draft_id}|{_normalized_skill_name(name)}".encode("utf-8")
    ).hexdigest()[:20]
    return f"provisional-skill-{digest}"


def _base_profile(base_profile: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
    document = _mapping(base_profile, "base_profile")
    profile = _mapping(document.get("profile"), "base_profile.profile")
    basic = _mapping(profile.get("basic"), "base_profile.profile.basic")
    profile_id = _text(basic.get("profile_id"), "base_profile.profile.basic.profile_id")
    target_roles = profile.get("target_roles")
    if not isinstance(target_roles, list) or not target_roles:
        raise ProfileDocumentError("검색용 기준 프로필에는 목표 직무가 1개 이상 필요함")
    skills = profile.get("skills")
    if not isinstance(skills, list):
        raise ProfileDocumentError("base_profile.profile.skills 배열이 필요함")
    return profile_id, deepcopy(dict(document))


def _project_profile(
    base_profile: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> tuple[dict[str, Any], str, str, str]:
    profile_id, projected = _base_profile(base_profile)
    validated_draft = validate_profile_analysis_draft(draft)
    draft_root = _mapping(
        validated_draft.get("profile_analysis_draft"),
        "profile_analysis_draft",
    )
    draft_id = _text(draft_root.get("draft_id"), "draft_id")
    extraction_id = _text(
        draft_root.get("source_extraction_id"), "source_extraction_id"
    )
    analysis = _mapping(validated_draft.get("analysis"), "analysis")

    profile = dict(_mapping(projected.get("profile"), "projected.profile"))
    skills = profile.get("skills")
    if not isinstance(skills, list):
        raise ProfileDocumentError("projected.profile.skills 배열이 필요함")
    existing_names: set[str] = set()
    for position, raw_skill in enumerate(skills):
        skill = _mapping(raw_skill, f"profile.skills[{position}]")
        existing_names.add(
            _normalized_skill_name(
                _text(skill.get("name"), f"profile.skills[{position}].name")
            )
        )

    grouped: dict[str, dict[str, Any]] = {}
    technology_items = analysis.get("technology_evidence")
    if not isinstance(technology_items, list):
        raise ProfileDocumentError("analysis.technology_evidence 배열이 필요함")
    for position, raw_item in enumerate(technology_items):
        item = _mapping(raw_item, f"analysis.technology_evidence[{position}]")
        name = _text(
            item.get("technology_name"),
            f"analysis.technology_evidence[{position}].technology_name",
        )
        normalized_name = _normalized_skill_name(name)
        entry = grouped.setdefault(
            normalized_name,
            {
                "name": name,
                "evidence": [],
                "candidate_ids": [],
                "confidence_levels": [],
            },
        )
        usage_evidence = _text(
            item.get("usage_evidence"),
            f"analysis.technology_evidence[{position}].usage_evidence",
        )
        if usage_evidence not in entry["evidence"]:
            entry["evidence"].append(usage_evidence)
        candidate_ids = item.get("candidate_ids")
        if not isinstance(candidate_ids, list):
            raise ProfileDocumentError("기술 근거 candidate_ids 배열이 필요함")
        for candidate_id in candidate_ids:
            normalized_id = _text(candidate_id, "candidate_id")
            if normalized_id not in entry["candidate_ids"]:
                entry["candidate_ids"].append(normalized_id)
        confidence = _text(item.get("confidence"), "confidence")
        if confidence not in entry["confidence_levels"]:
            entry["confidence_levels"].append(confidence)

    for normalized_name, entry in grouped.items():
        if normalized_name in existing_names:
            continue
        skills.append(
            {
                "skill_id": _provisional_skill_id(draft_id, entry["name"]),
                "name": entry["name"],
                "level": "unconfirmed",
                "evidence": entry["evidence"],
                "notes": "프로필 분석 초안에서 추출한 검색 보조 근거이며 사용자 확인 전",
                "verification_status": "unconfirmed",
                "provenance": {
                    "source_draft_id": draft_id,
                    "candidate_ids": entry["candidate_ids"],
                    "confidence_levels": entry["confidence_levels"],
                },
            }
        )
        existing_names.add(normalized_name)

    profile["skills"] = skills
    profile["provisional_evidence"] = {
        "status": "unconfirmed",
        "source_draft_id": draft_id,
        "career_evidence": deepcopy(analysis.get("career_evidence", [])),
        "achievement_evidence": deepcopy(analysis.get("achievement_evidence", [])),
        "technology_evidence": deepcopy(technology_items),
        "unknowns": deepcopy(analysis.get("unknowns", [])),
    }
    projected["profile"] = profile
    projected["metadata"] = {
        "schema_version": PROVISIONAL_SEARCH_PROFILE_SCHEMA_VERSION,
        "data_type": "provisional_search_profile",
        "status": "provisional_search_only",
        "evidence_status": "unconfirmed",
        "contains_personal_data": True,
        "contains_candidate_text": True,
        "git_tracking_allowed": False,
        "permanent_profile_updated": False,
    }
    return projected, profile_id, draft_id, extraction_id


def build_provisional_search_profile(
    base_profile: Mapping[str, Any],
    draft: Mapping[str, Any],
    *,
    projected_at: datetime,
) -> dict[str, Any]:
    """Build a search-only profile without confirming draft evidence."""

    if projected_at.tzinfo is None or projected_at.utcoffset() is None:
        raise ProfileDocumentError("projected_at은 시간대가 포함되어야 함")
    projected, profile_id, draft_id, extraction_id = _project_profile(
        base_profile, draft
    )
    base_hash = profile_content_sha256(base_profile)
    output_hash = profile_content_sha256(projected)
    projection_id = "provisional-search-profile-" + sha256(
        "|".join(
            (base_hash, draft_id, output_hash, PROVISIONAL_SEARCH_PROFILE_RULES_VERSION)
        ).encode("utf-8")
    ).hexdigest()[:24]
    return {
        "provisional_search_profile": {
            "projection_id": projection_id,
            "projected_at": projected_at.isoformat(timespec="microseconds"),
            "status": "provisional_search_only",
            "base_profile_id": profile_id,
            "base_profile_content_sha256": base_hash,
            "source_draft_id": draft_id,
            "source_extraction_id": extraction_id,
            "output_profile_content_sha256": output_hash,
            "rules_version": PROVISIONAL_SEARCH_PROFILE_RULES_VERSION,
        },
        "profile_document": projected,
        "metadata": {
            "schema_version": PROVISIONAL_SEARCH_PROFILE_SCHEMA_VERSION,
            "contains_profile_content": True,
            "contains_personal_data": True,
            "contains_candidate_text": True,
            "git_tracking_allowed": False,
            "permanent_profile_updated": False,
        },
    }


def validate_provisional_search_profile(
    projection: Mapping[str, Any],
    *,
    base_profile: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> dict[str, Any]:
    """Verify a projection against the exact base profile and source draft."""

    document = _mapping(projection, "projection")
    if set(document) != {
        "provisional_search_profile",
        "profile_document",
        "metadata",
    }:
        raise ProfileDocumentError("임시 검색 프로필 필드 구성이 올바르지 않음")
    root = _mapping(
        document.get("provisional_search_profile"), "provisional_search_profile"
    )
    expected_root_fields = {
        "projection_id",
        "projected_at",
        "status",
        "base_profile_id",
        "base_profile_content_sha256",
        "source_draft_id",
        "source_extraction_id",
        "output_profile_content_sha256",
        "rules_version",
    }
    if set(root) != expected_root_fields:
        raise ProfileDocumentError("임시 검색 프로필 식별 필드 구성이 올바르지 않음")
    projection_id = _text(root.get("projection_id"), "projection_id")
    if _PROJECTION_ID_PATTERN.fullmatch(projection_id) is None:
        raise ProfileDocumentError("임시 검색 프로필 ID가 올바르지 않음")
    projected_at = _aware_datetime(root.get("projected_at"), "projected_at")
    expected = build_provisional_search_profile(
        base_profile,
        draft,
        projected_at=projected_at,
    )
    if expected != document:
        raise ProfileDocumentError("임시 검색 프로필이 원본 초안 또는 기준 프로필과 일치하지 않음")
    return deepcopy(dict(document))


def save_provisional_search_profile(
    projection: Mapping[str, Any],
    directory: str | Path,
    *,
    base_profile: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> tuple[Path, bool]:
    """Atomically save or reuse one verified private projection."""

    validated = validate_provisional_search_profile(
        projection,
        base_profile=base_profile,
        draft=draft,
    )
    projection_id = validated["provisional_search_profile"]["projection_id"]
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    if target_directory.is_symlink():
        raise ProfileDocumentError("임시 검색 프로필 저장 경로가 안전하지 않음")
    if len(list(target_directory.glob("provisional-search-profile-*.json"))) > _MAX_FILES:
        raise ProfileDocumentError("임시 검색 프로필 파일이 허용 개수를 초과함")
    target_path = target_directory / f"{projection_id}.json"
    serialized = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    if target_path.exists():
        if target_path.is_symlink():
            raise ProfileDocumentError("임시 검색 프로필 심볼릭 링크는 읽을 수 없음")
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError("기존 임시 검색 프로필을 읽을 수 없음") from error
        if existing != validated:
            raise ProfileDocumentError("같은 ID의 기존 임시 검색 프로필이 일치하지 않음")
        return target_path, False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{projection_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("임시 검색 프로필을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def load_provisional_search_profile(
    projection_id: str,
    directory: str | Path,
    *,
    base_profile: Mapping[str, Any],
    draft: Mapping[str, Any],
) -> dict[str, Any]:
    """Load one private projection and verify its exact provenance."""

    normalized_id = _text(projection_id, "projection_id")
    if _PROJECTION_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("임시 검색 프로필 ID가 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("임시 검색 프로필 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("임시 검색 프로필을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError("임시 검색 프로필 최상위 JSON은 객체여야 함")
    return validate_provisional_search_profile(
        value,
        base_profile=base_profile,
        draft=draft,
    )
