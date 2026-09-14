"""Record a final user decision for one complete skill addition."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .document_store import ProfileDocumentError
from .skill_addition import (
    PROFILE_SKILL_ADDITION_RULES_VERSION,
    PROFILE_SKILL_ADDITION_SCHEMA_VERSION,
)
from .skill_confirmation import (
    MAX_SKILL_CONFIRMATION_NOTES_CHARS,
    MAX_SKILL_EVIDENCE_CHARS,
    MAX_SKILL_EVIDENCE_ITEMS,
    SKILL_LEVELS,
)


PROFILE_SKILL_ADDITION_REVIEW_SCHEMA_VERSION = "0.1"
SKILL_ADDITION_REVIEW_DECISIONS = frozenset({"approve", "reject"})
MAX_SKILL_ADDITION_REVIEW_NOTES_CHARS = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _validate_skill(item: Mapping[str, Any], position: int) -> None:
    skill = _mapping(
        item.get("proposed_skill"),
        f"skill_additions[{position}].proposed_skill",
    )
    _text(skill.get("skill_id"), f"skill_additions[{position}].proposed_skill.skill_id")
    _text(skill.get("name"), f"skill_additions[{position}].proposed_skill.name")
    if skill.get("level") not in SKILL_LEVELS:
        raise ProfileDocumentError(
            f"skill_additions[{position}].proposed_skill.level이 올바르지 않음"
        )
    evidence = skill.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise ProfileDocumentError(
            f"skill_additions[{position}].proposed_skill.evidence 배열이 필요함"
        )
    if len(evidence) > MAX_SKILL_EVIDENCE_ITEMS:
        raise ProfileDocumentError(
            f"skill_additions[{position}].proposed_skill.evidence가 너무 많음"
        )
    evidence_keys: set[str] = set()
    for evidence_position, raw_evidence in enumerate(evidence):
        normalized = _text(
            raw_evidence,
            f"skill_additions[{position}].proposed_skill.evidence[{evidence_position}]",
        )
        if normalized != raw_evidence or len(normalized) > MAX_SKILL_EVIDENCE_CHARS:
            raise ProfileDocumentError(
                f"skill_additions[{position}].proposed_skill.evidence[{evidence_position}]가 올바르지 않음"
            )
        key = normalized.casefold()
        if key in evidence_keys:
            raise ProfileDocumentError(
                f"skill_additions[{position}].proposed_skill.evidence가 중복됨"
            )
        evidence_keys.add(key)
    notes = skill.get("notes")
    if notes is not None:
        normalized_notes = _text(
            notes,
            f"skill_additions[{position}].proposed_skill.notes",
        )
        if (
            normalized_notes != notes
            or len(normalized_notes) > MAX_SKILL_CONFIRMATION_NOTES_CHARS
        ):
            raise ProfileDocumentError(
                f"skill_additions[{position}].proposed_skill.notes가 올바르지 않음"
            )


def validated_profile_skill_addition_index(
    proposal: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    """Validate one addition proposal and index all reviewable items."""

    root = _mapping(proposal.get("profile_skill_addition"), "profile_skill_addition")
    metadata = _mapping(proposal.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_SKILL_ADDITION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 추가안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("기술 추가안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("반영되지 않은 기술 추가안만 검토할 수 있음")
    if root.get("rules_version") != PROFILE_SKILL_ADDITION_RULES_VERSION:
        raise ProfileDocumentError("현재 규칙 버전의 기술 추가안이 아님")
    raw_items = proposal.get("skill_additions")
    if not isinstance(raw_items, list):
        raise ProfileDocumentError("skill_additions 배열이 필요함")
    if metadata.get("contains_candidate_text") is not bool(raw_items):
        raise ProfileDocumentError("기술 추가안의 후보 문장 포함 표시가 내용과 다름")
    summary = _mapping(proposal.get("summary"), "summary")
    confirmed_skill_count = summary.get("confirmed_skill_count")
    if (
        isinstance(confirmed_skill_count, bool)
        or not isinstance(confirmed_skill_count, int)
        or confirmed_skill_count != len(raw_items)
    ):
        raise ProfileDocumentError("완성 기술 수와 skill_additions가 일치하지 않음")

    item_ids: set[str] = set()
    index: dict[str, Mapping[str, Any]] = {}
    skill_ids: set[str] = set()
    for position, raw_item in enumerate(raw_items):
        item = _mapping(raw_item, f"skill_additions[{position}]")
        item_id = _text(
            item.get("addition_item_id"),
            f"skill_additions[{position}].addition_item_id",
        )
        if item_id in item_ids:
            raise ProfileDocumentError(f"중복 기술 추가 항목 ID: {item_id}")
        item_ids.add(item_id)
        index[item_id] = item
        if item.get("application_status") != "needs_final_review":
            raise ProfileDocumentError(
                f"skill_additions[{position}]가 최종 검토 전 상태가 아님"
            )
        _validate_skill(item, position)
        skill = _mapping(item.get("proposed_skill"), "proposed_skill")
        skill_id = skill["skill_id"].strip()
        if skill_id in skill_ids:
            raise ProfileDocumentError(f"중복 제안 skill_id: {skill_id}")
        skill_ids.add(skill_id)
        source = _mapping(item.get("source"), f"skill_additions[{position}].source")
        for field in (
            "mapping_item_id",
            "proposal_item_id",
            "candidate_id",
            "extraction_id",
            "document_id",
            "review_id",
            "confirmation_id",
        ):
            _text(source.get(field), f"skill_additions[{position}].source.{field}")
        for field in ("line_start", "line_end"):
            value = source.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProfileDocumentError(
                    f"skill_additions[{position}].source.{field}가 올바르지 않음"
                )
        if source["line_end"] < source["line_start"]:
            raise ProfileDocumentError(
                f"skill_additions[{position}]의 원문 줄 범위가 올바르지 않음"
            )
    expected_status = "needs_final_review" if raw_items else "no_confirmed_skills"
    if root.get("status") != expected_status:
        raise ProfileDocumentError("기술 추가안 상태가 완성 기술 수와 일치하지 않음")
    return root, index


def _addition_item(
    proposal: Mapping[str, Any],
    addition_item_id: str,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    preliminary_root = _mapping(
        proposal.get("profile_skill_addition"),
        "profile_skill_addition",
    )
    if preliminary_root.get("status") != "needs_final_review":
        raise ProfileDocumentError("최종 검토할 기술이 있는 추가안이 아님")
    root, index = validated_profile_skill_addition_index(proposal)
    normalized_item_id = _text(addition_item_id, "addition_item_id")
    item = index.get(normalized_item_id)
    if item is None:
        raise ProfileDocumentError(f"기술 추가 항목을 찾을 수 없음: {normalized_item_id}")
    return root, item


def build_profile_skill_addition_review(
    addition_proposal: Mapping[str, Any],
    *,
    addition_item_id: str,
    decision: str,
    reviewed_at: datetime,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one immutable final decision without copying proposed skill data."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ProfileDocumentError("reviewed_at은 시간대가 포함되어야 함")
    if decision not in SKILL_ADDITION_REVIEW_DECISIONS:
        allowed = ", ".join(sorted(SKILL_ADDITION_REVIEW_DECISIONS))
        raise ProfileDocumentError(f"decision 허용값: {allowed}")
    normalized_notes = None
    if notes is not None:
        if not isinstance(notes, str):
            raise ProfileDocumentError("notes는 문자열이어야 함")
        normalized_notes = notes.strip() or None
        if (
            normalized_notes is not None
            and len(normalized_notes) > MAX_SKILL_ADDITION_REVIEW_NOTES_CHARS
        ):
            raise ProfileDocumentError(
                f"notes는 {MAX_SKILL_ADDITION_REVIEW_NOTES_CHARS}자 이하여야 함"
            )

    proposal_root, item = _addition_item(addition_proposal, addition_item_id)
    proposal_id = _text(
        proposal_root.get("proposal_id"),
        "profile_skill_addition.proposal_id",
    )
    normalized_item_id = _text(item.get("addition_item_id"), "addition_item_id")
    item_source = _mapping(item.get("source"), "skill_addition.source")
    reviewed_timestamp = reviewed_at.isoformat(timespec="microseconds")
    review_key = f"{proposal_id}|{normalized_item_id}|{reviewed_timestamp}"
    review_id = "profile-skill-addition-review-" + sha256(
        review_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "profile_skill_addition_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_timestamp,
            "review_source": "explicit_user_input",
            "decision": decision,
            "notes": normalized_notes,
        },
        "source": {
            "addition_proposal_id": proposal_id,
            "addition_item_id": normalized_item_id,
            "base_profile_id": _text(
                proposal_root.get("base_profile_id"),
                "profile_skill_addition.base_profile_id",
            ),
            "base_profile_content_sha256": _text(
                proposal_root.get("base_profile_content_sha256"),
                "profile_skill_addition.base_profile_content_sha256",
            ),
            "source_mapping_id": _text(
                proposal_root.get("source_mapping_id"),
                "profile_skill_addition.source_mapping_id",
            ),
            "confirmation_id": _text(
                item_source.get("confirmation_id"),
                "skill_addition.source.confirmation_id",
            ),
        },
        "metadata": {
            "schema_version": PROFILE_SKILL_ADDITION_REVIEW_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_proposed_skill": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_skill_addition_review(
    review: Mapping[str, Any],
    directory: str | Path,
) -> Path:
    """Atomically save one immutable final skill addition review."""

    root = _mapping(
        review.get("profile_skill_addition_review"),
        "profile_skill_addition_review",
    )
    metadata = _mapping(review.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_SKILL_ADDITION_REVIEW_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 기술 추가 최종 검토 기록이 아님")
    if metadata.get("contains_proposed_skill") is not False:
        raise ProfileDocumentError("최종 검토 기록에 기술 내용 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("최종 검토 기록에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("최종 검토 기록은 프로필 갱신 상태일 수 없음")
    review_id = _text(root.get("review_id"), "profile_skill_addition_review.review_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{review_id}.json"
    if target_path.exists():
        raise ProfileDocumentError(f"기술 추가 최종 검토 파일이 이미 존재함: {target_path}")

    serialized = json.dumps(review, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{review_id}.",
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
            f"기술 추가 최종 검토 기록을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path
