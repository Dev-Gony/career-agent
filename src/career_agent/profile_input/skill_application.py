"""Apply finally approved skills to a new private profile version."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Iterable, Mapping

from .document_store import ProfileDocumentError
from .skill_addition_review import (
    MAX_SKILL_ADDITION_REVIEW_NOTES_CHARS,
    PROFILE_SKILL_ADDITION_REVIEW_SCHEMA_VERSION,
    SKILL_ADDITION_REVIEW_DECISIONS,
    validated_profile_skill_addition_index,
)
from .skill_mapping import normalize_skill_name
from .update_proposal import profile_content_sha256


PROFILE_SKILL_APPLICATION_SCHEMA_VERSION = "0.1"
PROFILE_SKILL_APPLICATION_RULES_VERSION = "0.1"
_APPLICATION_ID_PATTERN = re.compile(r"^profile-skill-application-[0-9a-f]{24}$")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _timestamp(value: Any, name: str) -> tuple[float, str, datetime]:
    normalized = _text(value, name)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}은 시간대가 포함되어야 함")
    return parsed.timestamp(), normalized, parsed


def _profile_skill_keys(
    profile: Mapping[str, Any],
) -> tuple[set[str], set[str]]:
    raw_skills = profile.get("skills")
    if not isinstance(raw_skills, list):
        raise ProfileDocumentError("profile.skills 배열이 필요함")
    skill_ids: set[str] = set()
    skill_names: set[str] = set()
    for position, raw_skill in enumerate(raw_skills):
        skill = _mapping(raw_skill, f"profile.skills[{position}]")
        skill_id = _text(skill.get("skill_id"), f"profile.skills[{position}].skill_id")
        name = _text(skill.get("name"), f"profile.skills[{position}].name")
        normalized_name = normalize_skill_name(name)
        if skill_id in skill_ids:
            raise ProfileDocumentError(f"중복 skill_id: {skill_id}")
        if normalized_name in skill_names:
            raise ProfileDocumentError(f"중복 기술명: {name}")
        skill_ids.add(skill_id)
        skill_names.add(normalized_name)
    return skill_ids, skill_names


def _latest_reviews(
    reviews: Iterable[Mapping[str, Any]],
    *,
    proposal_id: str,
    proposal_root: Mapping[str, Any],
    addition_items: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, tuple[tuple[float, str], dict[str, Any]]] = {}
    for position, raw_review in enumerate(reviews):
        review = _mapping(raw_review, f"reviews[{position}]")
        root = _mapping(
            review.get("profile_skill_addition_review"),
            f"reviews[{position}].profile_skill_addition_review",
        )
        source = _mapping(review.get("source"), f"reviews[{position}].source")
        metadata = _mapping(review.get("metadata"), f"reviews[{position}].metadata")
        if metadata.get("schema_version") != PROFILE_SKILL_ADDITION_REVIEW_SCHEMA_VERSION:
            raise ProfileDocumentError(f"reviews[{position}]의 스키마 버전이 올바르지 않음")
        if metadata.get("contains_proposed_skill") is not False:
            raise ProfileDocumentError(f"reviews[{position}]에 기술 내용 제외 표시가 없음")
        if metadata.get("git_tracking_allowed") is not False:
            raise ProfileDocumentError(f"reviews[{position}]에 Git 제외 표시가 없음")
        if metadata.get("profile_updated") is not False:
            raise ProfileDocumentError(f"reviews[{position}]가 프로필 갱신 상태임")
        if root.get("review_source") != "explicit_user_input":
            raise ProfileDocumentError(f"reviews[{position}]가 명시적 사용자 판단이 아님")
        decision = root.get("decision")
        if decision not in SKILL_ADDITION_REVIEW_DECISIONS:
            raise ProfileDocumentError(f"reviews[{position}]의 decision이 올바르지 않음")
        notes = root.get("notes")
        if notes is not None:
            if (
                not isinstance(notes, str)
                or not notes.strip()
                or notes != notes.strip()
                or len(notes) > MAX_SKILL_ADDITION_REVIEW_NOTES_CHARS
            ):
                raise ProfileDocumentError(f"reviews[{position}]의 notes가 올바르지 않음")
        reviewed_order = _timestamp(
            root.get("reviewed_at"),
            f"reviews[{position}].profile_skill_addition_review.reviewed_at",
        )
        review_id = _text(root.get("review_id"), f"reviews[{position}].review_id")
        review_proposal_id = _text(
            source.get("addition_proposal_id"),
            f"reviews[{position}].source.addition_proposal_id",
        )
        addition_item_id = _text(
            source.get("addition_item_id"),
            f"reviews[{position}].source.addition_item_id",
        )
        expected_review_id = "profile-skill-addition-review-" + sha256(
            f"{review_proposal_id}|{addition_item_id}|{reviewed_order[1]}".encode("utf-8")
        ).hexdigest()[:24]
        if review_id != expected_review_id:
            raise ProfileDocumentError(f"reviews[{position}]의 검토 ID가 원본 참조와 일치하지 않음")
        if review_proposal_id != proposal_id:
            continue
        item = addition_items.get(addition_item_id)
        if item is None:
            raise ProfileDocumentError(
                f"reviews[{position}]가 존재하지 않는 기술 추가 항목을 참조함: {addition_item_id}"
            )
        item_source = _mapping(item.get("source"), f"skill_addition[{addition_item_id}].source")
        if (
            source.get("base_profile_id") != proposal_root.get("base_profile_id")
            or source.get("base_profile_content_sha256")
            != proposal_root.get("base_profile_content_sha256")
            or source.get("source_mapping_id") != proposal_root.get("source_mapping_id")
            or source.get("confirmation_id") != item_source.get("confirmation_id")
        ):
            raise ProfileDocumentError(f"reviews[{position}]의 추가안 근거가 원본과 일치하지 않음")
        value = {
            "review_id": review_id,
            "reviewed_at": reviewed_order[1],
            "reviewed_datetime": reviewed_order[2],
            "decision": decision,
        }
        ordering = (reviewed_order[0], review_id)
        existing = latest.get(addition_item_id)
        if existing is None or ordering > existing[0]:
            latest[addition_item_id] = (ordering, value)
    return {item_id: value for item_id, (_, value) in latest.items()}


def build_profile_skill_application(
    profile_document: Mapping[str, Any],
    addition_proposal: Mapping[str, Any],
    reviews: Iterable[Mapping[str, Any]],
    *,
    applied_at: datetime,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Create an audit record and, when approved, a new profile version."""

    if applied_at.tzinfo is None or applied_at.utcoffset() is None:
        raise ProfileDocumentError("applied_at은 시간대가 포함되어야 함")
    profile = _mapping(profile_document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")
    existing_skill_ids, existing_skill_names = _profile_skill_keys(profile)
    proposal_root, addition_items = validated_profile_skill_addition_index(
        addition_proposal
    )
    proposal_id = _text(proposal_root.get("proposal_id"), "profile_skill_addition.proposal_id")
    base_profile_id = _text(
        proposal_root.get("base_profile_id"),
        "profile_skill_addition.base_profile_id",
    )
    base_profile_hash = _text(
        proposal_root.get("base_profile_content_sha256"),
        "profile_skill_addition.base_profile_content_sha256",
    )
    _text(proposal_root.get("source_mapping_id"), "profile_skill_addition.source_mapping_id")
    current_profile_hash = profile_content_sha256(profile_document)
    if base_profile_id != profile_id:
        raise ProfileDocumentError("기술 추가안의 기준 profile_id가 현재 프로필과 다름")
    if base_profile_hash != current_profile_hash:
        raise ProfileDocumentError("기술 추가안 생성 뒤 프로필 내용이 변경됨")

    latest = _latest_reviews(
        reviews,
        proposal_id=proposal_id,
        proposal_root=proposal_root,
        addition_items=addition_items,
    )
    approved_item_ids = [
        item_id
        for item_id in addition_items
        if latest.get(item_id, {}).get("decision") == "approve"
    ]
    rejected_count = sum(review["decision"] == "reject" for review in latest.values())

    updated_profile: dict[str, Any] | None = None
    applied_items: list[dict[str, str]] = []
    output_profile_hash: str | None = None
    if approved_item_ids:
        updated_profile = deepcopy(dict(profile_document))
        updated_profile_root = _mapping(updated_profile.get("profile"), "profile")
        updated_skills = updated_profile_root.get("skills")
        if not isinstance(updated_skills, list):
            raise ProfileDocumentError("profile.skills 배열이 필요함")
        latest_approved_date = max(
            latest[item_id]["reviewed_datetime"] for item_id in approved_item_ids
        ).date().isoformat()
        for item_id in approved_item_ids:
            item = addition_items[item_id]
            skill = _mapping(item.get("proposed_skill"), f"skill_addition[{item_id}].proposed_skill")
            skill_id = _text(skill.get("skill_id"), f"skill_addition[{item_id}].skill_id")
            skill_name = _text(skill.get("name"), f"skill_addition[{item_id}].name")
            normalized_name = normalize_skill_name(skill_name)
            if skill_id in existing_skill_ids:
                raise ProfileDocumentError(f"현재 프로필과 중복되는 skill_id: {skill_id}")
            if normalized_name in existing_skill_names:
                raise ProfileDocumentError(f"현재 프로필과 중복되는 기술명: {skill_name}")
            existing_skill_ids.add(skill_id)
            existing_skill_names.add(normalized_name)
            updated_skills.append(deepcopy(dict(skill)))
            applied_items.append(
                {
                    "addition_item_id": item_id,
                    "final_review_id": latest[item_id]["review_id"],
                    "skill_id": skill_id,
                }
            )
        updated_metadata = _mapping(updated_profile.get("metadata"), "metadata")
        if not isinstance(updated_metadata, dict):
            raise ProfileDocumentError("metadata는 수정 가능한 객체여야 함")
        updated_metadata["last_updated"] = latest_approved_date
        output_profile_hash = profile_content_sha256(updated_profile)

    application_key = "|".join(
        [base_profile_hash, proposal_id, PROFILE_SKILL_APPLICATION_RULES_VERSION]
        + [
            f"{item_id}:{latest[item_id]['review_id']}:{latest[item_id]['decision']}"
            for item_id in sorted(latest)
        ]
    )
    application_id = "profile-skill-application-" + sha256(
        application_key.encode("utf-8")
    ).hexdigest()[:24]
    status = "applied_to_new_version" if updated_profile is not None else "no_approved_skills"
    application = {
        "profile_skill_application": {
            "application_id": application_id,
            "applied_at": applied_at.isoformat(timespec="microseconds"),
            "status": status,
            "base_profile_id": profile_id,
            "base_profile_content_sha256": base_profile_hash,
            "source_addition_proposal_id": proposal_id,
            "output_profile_content_sha256": output_profile_hash,
            "rules_version": PROFILE_SKILL_APPLICATION_RULES_VERSION,
        },
        "summary": {
            "addition_count": len(addition_items),
            "reviewed_count": len(latest),
            "approved_count": len(approved_item_ids),
            "rejected_count": rejected_count,
            "unreviewed_count": len(addition_items) - len(latest),
            "applied_count": len(applied_items),
        },
        "applied_items": applied_items,
        "analysis_notes": {
            "facts": [
                "항목별 가장 최근 명시적 사용자 판단만 사용함",
                "최종 판단이 approve인 기술만 새 프로필 버전에 추가함",
                "기준 프로필 원본은 수정하지 않음",
            ],
            "unknowns": [] if updated_profile is not None else ["최종 승인된 새 기술이 없음"],
        },
        "metadata": {
            "schema_version": PROFILE_SKILL_APPLICATION_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_skill_content": False,
            "git_tracking_allowed": False,
            "profile_updated": updated_profile is not None,
        },
    }
    return application, updated_profile


def _read_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"{description}을 읽을 수 없음: {path}") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError(f"{description} 최상위 JSON은 객체여야 함")
    return value


def save_profile_skill_application(
    application: Mapping[str, Any],
    updated_profile: Mapping[str, Any] | None,
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save one application record and optional profile version."""

    root = _mapping(application.get("profile_skill_application"), "profile_skill_application")
    metadata = _mapping(application.get("metadata"), "metadata")
    application_id = _text(root.get("application_id"), "profile_skill_application.application_id")
    if _APPLICATION_ID_PATTERN.fullmatch(application_id) is None:
        raise ProfileDocumentError("application_id 형식이 올바르지 않음")
    if metadata.get("schema_version") != PROFILE_SKILL_APPLICATION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 기술 적용 기록이 아님")
    if metadata.get("contains_skill_content") is not False:
        raise ProfileDocumentError("적용 기록에 기술 내용 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("적용 기록에 Git 제외 표시가 없음")
    expected_profile = root.get("status") == "applied_to_new_version"
    if root.get("status") not in {"applied_to_new_version", "no_approved_skills"}:
        raise ProfileDocumentError("프로필 기술 적용 상태가 올바르지 않음")
    if metadata.get("profile_updated") is not expected_profile:
        raise ProfileDocumentError("프로필 갱신 표시가 적용 상태와 일치하지 않음")
    if (updated_profile is not None) is not expected_profile:
        raise ProfileDocumentError("새 프로필 파일 유무가 적용 상태와 일치하지 않음")
    expected_hash = root.get("output_profile_content_sha256")
    if updated_profile is not None:
        if expected_hash != profile_content_sha256(updated_profile):
            raise ProfileDocumentError("새 프로필 내용 지문이 적용 기록과 일치하지 않음")
    elif expected_hash is not None:
        raise ProfileDocumentError("미적용 기록에는 새 프로필 내용 지문이 없어야 함")

    output_directory = Path(directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    target_directory = output_directory / application_id
    target_application_path = target_directory / "application.json"
    target_profile_path = target_directory / "profile.json"
    if target_directory.exists():
        existing_application = _read_json(target_application_path, "기존 프로필 기술 적용 기록")
        existing_root = _mapping(
            existing_application.get("profile_skill_application"),
            "profile_skill_application",
        )
        current_root = dict(root)
        previous_root = dict(existing_root)
        current_root.pop("applied_at", None)
        previous_root.pop("applied_at", None)
        comparable_existing = dict(existing_application)
        comparable_current = dict(application)
        comparable_existing["profile_skill_application"] = previous_root
        comparable_current["profile_skill_application"] = current_root
        if comparable_existing != comparable_current:
            raise ProfileDocumentError("같은 적용 ID의 기존 내용이 일치하지 않음")
        if expected_profile:
            existing_profile = _read_json(target_profile_path, "기존 새 프로필")
            if existing_profile != updated_profile:
                raise ProfileDocumentError("같은 적용 ID의 기존 새 프로필이 일치하지 않음")
        elif target_profile_path.exists():
            raise ProfileDocumentError("미적용 기록에 새 프로필 파일이 존재함")
        return target_application_path, False

    temporary_directory = Path(
        tempfile.mkdtemp(prefix=f".{application_id}.", dir=output_directory)
    )
    try:
        (temporary_directory / "application.json").write_text(
            json.dumps(application, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        if updated_profile is not None:
            (temporary_directory / "profile.json").write_text(
                json.dumps(updated_profile, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        os.replace(temporary_directory, target_directory)
    except OSError as error:
        raise ProfileDocumentError(
            f"프로필 기술 적용 결과를 저장할 수 없음: {target_directory}"
        ) from error
    finally:
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
    return target_application_path, True
