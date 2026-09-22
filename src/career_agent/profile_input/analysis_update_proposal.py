"""Build a non-mutating profile proposal from approved analysis items."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from .analysis_draft import validate_profile_analysis_draft
from .analysis_review import validate_profile_analysis_review
from .document_store import ProfileDocumentError
from .update_proposal import profile_content_sha256


PROFILE_ANALYSIS_UPDATE_PROPOSAL_SCHEMA_VERSION = "0.1"
_PROPOSAL_ID_PATTERN = re.compile(
    r"^profile-analysis-update-proposal-[0-9a-f]{24}$"
)
_DRAFT_ID_PATTERN = re.compile(r"^profile-analysis-draft-[0-9a-f]{24}$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_REVIEW_ID_PATTERN = re.compile(r"^profile-analysis-review-[0-9a-f]{24}$")
_PROFILE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_ITEM_TYPES = (
    "career_evidence",
    "achievement_evidence",
    "technology_evidence",
    "unknowns",
)
_PROFILE_FACT_ITEM_TYPES = frozenset(_ITEM_TYPES[:3])
_PROPOSAL_STATUSES = frozenset(
    {
        "no_approved_profile_facts",
        "no_changes",
        "needs_mapping",
        "ready_for_final_review",
    }
)
_MAPPING_STATUSES = frozenset(
    {
        "needs_career_selection",
        "needs_skill_level_confirmation",
        "ready_for_final_review",
    }
)
_MAX_STORED_PROPOSAL_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str, *, max_chars: int = 1000) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > max_chars
    ):
        raise ProfileDocumentError(f"{name} 문자열이 올바르지 않음")
    return value


def _optional_text(value: Any, name: str) -> str | None:
    if value is None:
        return None
    return _text(value, name)


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    if actual != expected:
        raise ProfileDocumentError(f"{name} 필드 구성이 올바르지 않음")


def _timestamp(value: Any, name: str) -> tuple[str, datetime]:
    normalized = _text(value, name, max_chars=100)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}에 시간대가 필요함")
    return normalized, parsed


def _nonnegative_integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ProfileDocumentError(f"{name}은 0 이상의 정수여야 함")
    return value


def _latest_reviews(
    reviews: Iterable[Mapping[str, Any]],
    *,
    draft_id: str,
    extraction_id: str,
) -> dict[tuple[str, int], dict[str, Any]]:
    selected: dict[tuple[str, int], tuple[datetime, str, dict[str, Any]]] = {}
    for position, raw_review in enumerate(reviews):
        try:
            review = validate_profile_analysis_review(raw_review)
        except ProfileDocumentError as error:
            raise ProfileDocumentError(
                f"reviews[{position}] 프로필 분석 검토 기록이 올바르지 않음"
            ) from error
        root = _mapping(review.get("profile_analysis_review"), "review")
        source = _mapping(review.get("source"), "review.source")
        if source.get("draft_id") != draft_id:
            continue
        if source.get("extraction_id") != extraction_id:
            raise ProfileDocumentError("검토 기록의 추출 ID가 분석 초안과 다름")
        reviewed_at_text, reviewed_at = _timestamp(
            root.get("reviewed_at"),
            "profile_analysis_review.reviewed_at",
        )
        review_id = _text(
            root.get("review_id"),
            "profile_analysis_review.review_id",
            max_chars=200,
        )
        key = (str(source["item_type"]), int(source["item_position"]))
        normalized = {
            "review_id": review_id,
            "reviewed_at": reviewed_at_text,
            "decision": root["decision"],
        }
        candidate = (reviewed_at, review_id, normalized)
        current = selected.get(key)
        if current is None or candidate[:2] > current[:2]:
            selected[key] = candidate
    return {key: value[2] for key, value in selected.items()}


def _profile_context(
    profile_document: Mapping[str, Any],
) -> tuple[str, dict[str, tuple[str, frozenset[str]]]]:
    profile = _mapping(profile_document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")
    if not isinstance(profile.get("career_history"), list):
        raise ProfileDocumentError("profile.career_history 배열이 필요함")
    skills = profile.get("skills")
    if not isinstance(skills, list):
        raise ProfileDocumentError("profile.skills 배열이 필요함")
    skill_index: dict[str, tuple[str, frozenset[str]]] = {}
    for position, raw_skill in enumerate(skills):
        skill = _mapping(raw_skill, f"profile.skills[{position}]")
        skill_id = _text(skill.get("skill_id"), f"profile.skills[{position}].skill_id")
        name = _text(skill.get("name"), f"profile.skills[{position}].name")
        evidence = skill.get("evidence")
        if not isinstance(evidence, list) or any(
            not isinstance(item, str) or not item.strip() for item in evidence
        ):
            raise ProfileDocumentError(
                f"profile.skills[{position}].evidence 배열이 올바르지 않음"
            )
        normalized_name = " ".join(name.casefold().split())
        if normalized_name in skill_index:
            raise ProfileDocumentError("profile.skills에 중복 기술명이 있음")
        skill_index[normalized_name] = (
            skill_id,
            frozenset(" ".join(item.casefold().split()) for item in evidence),
        )
    return profile_id, skill_index


def _proposal_identity(proposal: Mapping[str, Any]) -> str:
    root = _mapping(proposal.get("profile_analysis_update_proposal"), "proposal")
    identity = {
        "base_profile_content_sha256": root.get("base_profile_content_sha256"),
        "source_draft_id": root.get("source_draft_id"),
        "source_extraction_id": root.get("source_extraction_id"),
        "review_snapshot": proposal.get("review_snapshot"),
        "proposed_changes": proposal.get("proposed_changes"),
        "excluded": proposal.get("excluded"),
    }
    serialized = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "profile-analysis-update-proposal-" + sha256(
        serialized.encode("utf-8")
    ).hexdigest()[:24]


def _validated_proposal(
    proposal: Mapping[str, Any],
) -> tuple[str, datetime]:
    _exact_keys(
        proposal,
        {
            "profile_analysis_update_proposal",
            "summary",
            "review_snapshot",
            "proposed_changes",
            "excluded",
            "metadata",
        },
        "profile_analysis_update_proposal_document",
    )
    root = _mapping(proposal.get("profile_analysis_update_proposal"), "proposal")
    summary = _mapping(proposal.get("summary"), "summary")
    excluded = _mapping(proposal.get("excluded"), "excluded")
    metadata = _mapping(proposal.get("metadata"), "metadata")
    _exact_keys(
        root,
        {
            "proposal_id",
            "created_at",
            "status",
            "base_profile_id",
            "base_profile_content_sha256",
            "source_draft_id",
            "source_extraction_id",
        },
        "profile_analysis_update_proposal",
    )
    _exact_keys(
        summary,
        {
            "analyzed_item_count",
            "reviewed_count",
            "approved_count",
            "rejected_count",
            "unreviewed_count",
            "approved_profile_fact_count",
            "proposed_change_count",
        },
        "summary",
    )
    _exact_keys(
        excluded,
        {"approved_unknown_count", "duplicate_skill_evidence_count"},
        "excluded",
    )
    _exact_keys(
        metadata,
        {
            "schema_version",
            "contains_personal_data",
            "contains_analysis_text",
            "contains_candidate_text",
            "git_tracking_allowed",
            "profile_updated",
        },
        "metadata",
    )

    proposal_id = _text(root.get("proposal_id"), "proposal.proposal_id", max_chars=200)
    if _PROPOSAL_ID_PATTERN.fullmatch(proposal_id) is None:
        raise ProfileDocumentError("프로필 분석 갱신안 ID가 올바르지 않음")
    _, created_at = _timestamp(root.get("created_at"), "proposal.created_at")
    status = root.get("status")
    if status not in _PROPOSAL_STATUSES:
        raise ProfileDocumentError("프로필 분석 갱신안 상태가 올바르지 않음")
    _text(root.get("base_profile_id"), "proposal.base_profile_id")
    profile_hash = _text(
        root.get("base_profile_content_sha256"),
        "proposal.base_profile_content_sha256",
        max_chars=64,
    )
    if _PROFILE_HASH_PATTERN.fullmatch(profile_hash) is None:
        raise ProfileDocumentError("기준 프로필 지문이 올바르지 않음")
    draft_id = _text(root.get("source_draft_id"), "proposal.source_draft_id")
    if _DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ProfileDocumentError("출처 분석 초안 ID가 올바르지 않음")
    extraction_id = _text(
        root.get("source_extraction_id"),
        "proposal.source_extraction_id",
    )
    if _EXTRACTION_ID_PATTERN.fullmatch(extraction_id) is None:
        raise ProfileDocumentError("출처 추출 ID가 올바르지 않음")

    review_snapshot = proposal.get("review_snapshot")
    changes = proposal.get("proposed_changes")
    if not isinstance(review_snapshot, list) or not isinstance(changes, list):
        raise ProfileDocumentError("검토 스냅샷과 변경 제안은 배열이어야 함")
    snapshot_index: dict[tuple[str, int], Mapping[str, Any]] = {}
    for position, raw_entry in enumerate(review_snapshot):
        entry = _mapping(raw_entry, f"review_snapshot[{position}]")
        _exact_keys(
            entry,
            {"item_type", "item_position", "review_id", "reviewed_at", "decision"},
            f"review_snapshot[{position}]",
        )
        item_type = entry.get("item_type")
        item_position = entry.get("item_position")
        if item_type not in _ITEM_TYPES:
            raise ProfileDocumentError("검토 스냅샷 항목 종류가 올바르지 않음")
        if (
            isinstance(item_position, bool)
            or not isinstance(item_position, int)
            or item_position < 1
        ):
            raise ProfileDocumentError("검토 스냅샷 항목 순번이 올바르지 않음")
        review_id = _text(entry.get("review_id"), "review_snapshot.review_id")
        if _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
            raise ProfileDocumentError("검토 스냅샷 ID가 올바르지 않음")
        _timestamp(entry.get("reviewed_at"), "review_snapshot.reviewed_at")
        if entry.get("decision") not in {"approve", "reject"}:
            raise ProfileDocumentError("검토 스냅샷 결정이 올바르지 않음")
        key = (str(item_type), int(item_position))
        if key in snapshot_index:
            raise ProfileDocumentError("검토 스냅샷에 중복 항목이 있음")
        snapshot_index[key] = entry

    for position, raw_change in enumerate(changes, start=1):
        change = _mapping(raw_change, f"proposed_changes[{position - 1}]")
        _exact_keys(
            change,
            {"change_id", "source", "target", "proposed_value"},
            f"proposed_changes[{position - 1}]",
        )
        if change.get("change_id") != f"analysis-change-{position:03d}":
            raise ProfileDocumentError("프로필 변경 제안 순번이 올바르지 않음")
        source = _mapping(change.get("source"), "change.source")
        target = _mapping(change.get("target"), "change.target")
        value = _mapping(change.get("proposed_value"), "change.proposed_value")
        _exact_keys(source, {"item_type", "item_position", "review_id"}, "change.source")
        _exact_keys(
            target,
            {"profile_section", "record_id", "operation", "mapping_status"},
            "change.target",
        )
        key = (str(source.get("item_type")), source.get("item_position"))
        snapshot = snapshot_index.get(key)
        if (
            key[0] not in _PROFILE_FACT_ITEM_TYPES
            or snapshot is None
            or snapshot.get("decision") != "approve"
            or snapshot.get("review_id") != source.get("review_id")
        ):
            raise ProfileDocumentError("변경 제안의 승인 출처가 올바르지 않음")
        if target.get("mapping_status") not in _MAPPING_STATUSES:
            raise ProfileDocumentError("변경 제안 매핑 상태가 올바르지 않음")
        if key[0] == "career_evidence":
            expected_target = ("career_history", "append_responsibility_evidence")
            expected_fields = {"role_or_context", "period_expression", "responsibility_evidence"}
            if (
                target.get("record_id") is not None
                or target.get("mapping_status") != "needs_career_selection"
            ):
                raise ProfileDocumentError("경력 근거는 기존 경력 선택이 필요함")
        elif key[0] == "achievement_evidence":
            expected_target = ("career_history", "append_achievement_evidence")
            expected_fields = {"problem_evidence", "action_evidence", "result_evidence"}
            if (
                target.get("record_id") is not None
                or target.get("mapping_status") != "needs_career_selection"
            ):
                raise ProfileDocumentError("성과 근거는 기존 경력 선택이 필요함")
        else:
            operation = (
                "append_skill_evidence"
                if target.get("record_id")
                else "add_skill_with_evidence"
            )
            expected_target = ("skills", operation)
            expected_fields = {"technology_name", "usage_evidence", "proposed_level"}
            if target.get("record_id") is None:
                if target.get("mapping_status") != "needs_skill_level_confirmation":
                    raise ProfileDocumentError("새 기술은 숙련도 확인이 필요함")
            else:
                _text(target.get("record_id"), "change.target.record_id")
                if target.get("mapping_status") != "ready_for_final_review":
                    raise ProfileDocumentError("기존 기술 근거의 매핑 상태가 올바르지 않음")
        if (target.get("profile_section"), target.get("operation")) != expected_target:
            raise ProfileDocumentError("변경 제안 대상 또는 동작이 올바르지 않음")
        _exact_keys(value, expected_fields, "change.proposed_value")
        for field, field_value in value.items():
            if field == "proposed_level":
                if field_value is not None:
                    raise ProfileDocumentError("기술 숙련도는 아직 확정할 수 없음")
            else:
                _optional_text(field_value, f"change.proposed_value.{field}")

    counts = {
        field: _nonnegative_integer(summary.get(field), f"summary.{field}")
        for field in summary
    }
    approved_unknown_count = _nonnegative_integer(
        excluded.get("approved_unknown_count"),
        "excluded.approved_unknown_count",
    )
    duplicate_count = _nonnegative_integer(
        excluded.get("duplicate_skill_evidence_count"),
        "excluded.duplicate_skill_evidence_count",
    )
    approved_count = sum(
        entry.get("decision") == "approve" for entry in review_snapshot
    )
    rejected_count = len(review_snapshot) - approved_count
    approved_profile_fact_count = approved_count - approved_unknown_count
    expected_counts = {
        "reviewed_count": len(review_snapshot),
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "approved_profile_fact_count": approved_profile_fact_count,
        "proposed_change_count": len(changes),
    }
    for field, expected in expected_counts.items():
        if counts[field] != expected:
            raise ProfileDocumentError(f"summary.{field} 합계가 일치하지 않음")
    if counts["analyzed_item_count"] != counts["reviewed_count"] + counts["unreviewed_count"]:
        raise ProfileDocumentError("분석 항목 합계가 일치하지 않음")
    if counts["proposed_change_count"] + duplicate_count != approved_profile_fact_count:
        raise ProfileDocumentError("승인된 프로필 근거와 변경 제안 합계가 일치하지 않음")
    expected_status = (
        "no_approved_profile_facts"
        if approved_profile_fact_count == 0
        else "no_changes"
        if not changes
        else "needs_mapping"
        if any(str(change["target"]["mapping_status"]).startswith("needs_") for change in changes)
        else "ready_for_final_review"
    )
    if status != expected_status:
        raise ProfileDocumentError("프로필 분석 갱신안 상태와 변경 항목이 일치하지 않음")

    if metadata.get("schema_version") != PROFILE_ANALYSIS_UPDATE_PROPOSAL_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 분석 갱신안이 아님")
    if metadata.get("contains_personal_data") is not True:
        raise ProfileDocumentError("프로필 분석 갱신안 개인정보 표시가 없음")
    if metadata.get("contains_analysis_text") is not bool(changes):
        raise ProfileDocumentError("프로필 분석 갱신안 분석 문장 표시가 올바르지 않음")
    if metadata.get("contains_candidate_text") is not False:
        raise ProfileDocumentError("프로필 분석 갱신안에 후보 원문 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 분석 갱신안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 분석 갱신안은 프로필 갱신 상태일 수 없음")
    if proposal_id != _proposal_identity(proposal):
        raise ProfileDocumentError("프로필 분석 갱신안 ID와 내용 지문이 일치하지 않음")
    return proposal_id, created_at


def build_profile_analysis_update_proposal(
    profile_document: Mapping[str, Any],
    draft: Mapping[str, Any],
    reviews: Iterable[Mapping[str, Any]],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    """Build a review-only proposal from each item's latest user decision."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProfileDocumentError("created_at은 시간대가 포함되어야 함")
    profile_id, skill_index = _profile_context(profile_document)
    validated_draft = validate_profile_analysis_draft(draft)
    draft_root = _mapping(
        validated_draft.get("profile_analysis_draft"),
        "profile_analysis_draft",
    )
    draft_id = str(draft_root["draft_id"])
    extraction_id = str(draft_root["source_extraction_id"])
    latest = _latest_reviews(
        reviews,
        draft_id=draft_id,
        extraction_id=extraction_id,
    )
    analysis = _mapping(validated_draft.get("analysis"), "analysis")
    flattened: list[tuple[str, int, Mapping[str, Any]]] = []
    for item_type in _ITEM_TYPES:
        items = analysis.get(item_type)
        if not isinstance(items, list):
            raise ProfileDocumentError(f"analysis.{item_type} 배열이 필요함")
        for item_position, raw_item in enumerate(items, start=1):
            flattened.append(
                (
                    item_type,
                    item_position,
                    _mapping(raw_item, f"analysis.{item_type}[{item_position - 1}]"),
                )
            )
    item_keys = {(item_type, item_position) for item_type, item_position, _ in flattened}
    unknown_review_keys = set(latest) - item_keys
    if unknown_review_keys:
        raise ProfileDocumentError("검토 기록이 분석 초안에 없는 항목을 참조함")

    review_snapshot: list[dict[str, Any]] = []
    changes: list[dict[str, Any]] = []
    approved_unknown_count = 0
    duplicate_skill_evidence_count = 0
    for item_type, item_position, item in flattened:
        review = latest.get((item_type, item_position))
        if review is None:
            continue
        review_snapshot.append(
            {
                "item_type": item_type,
                "item_position": item_position,
                **review,
            }
        )
        if review["decision"] != "approve":
            continue
        if item_type == "unknowns":
            approved_unknown_count += 1
            continue

        record_id: str | None = None
        if item_type == "career_evidence":
            profile_section = "career_history"
            operation = "append_responsibility_evidence"
            mapping_status = "needs_career_selection"
            proposed_value = {
                "role_or_context": item.get("role_or_context"),
                "period_expression": item.get("period_expression"),
                "responsibility_evidence": item.get("responsibility_evidence"),
            }
        elif item_type == "achievement_evidence":
            profile_section = "career_history"
            operation = "append_achievement_evidence"
            mapping_status = "needs_career_selection"
            proposed_value = {
                "problem_evidence": item.get("problem_evidence"),
                "action_evidence": item.get("action_evidence"),
                "result_evidence": item.get("result_evidence"),
            }
        else:
            profile_section = "skills"
            technology_name = str(item["technology_name"])
            usage_evidence = str(item["usage_evidence"])
            existing = skill_index.get(" ".join(technology_name.casefold().split()))
            if existing is not None and " ".join(usage_evidence.casefold().split()) in existing[1]:
                duplicate_skill_evidence_count += 1
                continue
            record_id = existing[0] if existing is not None else None
            operation = "append_skill_evidence" if record_id else "add_skill_with_evidence"
            mapping_status = (
                "ready_for_final_review"
                if record_id
                else "needs_skill_level_confirmation"
            )
            proposed_value = {
                "technology_name": technology_name,
                "usage_evidence": usage_evidence,
                "proposed_level": None,
            }
        changes.append(
            {
                "change_id": f"analysis-change-{len(changes) + 1:03d}",
                "source": {
                    "item_type": item_type,
                    "item_position": item_position,
                    "review_id": review["review_id"],
                },
                "target": {
                    "profile_section": profile_section,
                    "record_id": record_id,
                    "operation": operation,
                    "mapping_status": mapping_status,
                },
                "proposed_value": proposed_value,
            }
        )

    reviewed_count = len(review_snapshot)
    approved_count = sum(
        entry["decision"] == "approve" for entry in review_snapshot
    )
    rejected_count = reviewed_count - approved_count
    approved_profile_fact_count = approved_count - approved_unknown_count
    status = (
        "no_approved_profile_facts"
        if approved_profile_fact_count == 0
        else "no_changes"
        if not changes
        else "needs_mapping"
        if any(change["target"]["mapping_status"].startswith("needs_") for change in changes)
        else "ready_for_final_review"
    )
    proposal: dict[str, Any] = {
        "profile_analysis_update_proposal": {
            "proposal_id": "pending",
            "created_at": created_at.isoformat(timespec="microseconds"),
            "status": status,
            "base_profile_id": profile_id,
            "base_profile_content_sha256": profile_content_sha256(profile_document),
            "source_draft_id": draft_id,
            "source_extraction_id": extraction_id,
        },
        "summary": {
            "analyzed_item_count": len(flattened),
            "reviewed_count": reviewed_count,
            "approved_count": approved_count,
            "rejected_count": rejected_count,
            "unreviewed_count": len(flattened) - reviewed_count,
            "approved_profile_fact_count": approved_profile_fact_count,
            "proposed_change_count": len(changes),
        },
        "review_snapshot": review_snapshot,
        "proposed_changes": changes,
        "excluded": {
            "approved_unknown_count": approved_unknown_count,
            "duplicate_skill_evidence_count": duplicate_skill_evidence_count,
        },
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_UPDATE_PROPOSAL_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_analysis_text": bool(changes),
            "contains_candidate_text": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    proposal["profile_analysis_update_proposal"]["proposal_id"] = _proposal_identity(
        proposal
    )
    _validated_proposal(proposal)
    return proposal


def save_profile_analysis_update_proposal(
    proposal: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse one immutable private analysis proposal."""

    proposal_id, _ = _validated_proposal(proposal)
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{proposal_id}.json"
    if target_path.exists():
        existing = load_profile_analysis_update_proposal(
            proposal_id,
            target_directory,
        )
        comparable_existing = deepcopy(existing)
        comparable_proposal = deepcopy(dict(proposal))
        comparable_existing["profile_analysis_update_proposal"].pop("created_at")
        comparable_proposal["profile_analysis_update_proposal"].pop("created_at")
        if comparable_existing != comparable_proposal:
            raise ProfileDocumentError("같은 프로필 분석 갱신안 ID의 내용이 일치하지 않음")
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
        raise ProfileDocumentError("프로필 분석 갱신안을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def validate_profile_analysis_update_proposal(
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one stored-shape proposal and return an isolated copy."""

    _validated_proposal(proposal)
    return deepcopy(dict(proposal))


def load_profile_analysis_update_proposal(
    proposal_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load and verify one immutable private profile analysis proposal."""

    normalized_id = _text(proposal_id, "proposal_id", max_chars=200)
    if _PROPOSAL_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("프로필 분석 갱신안 ID가 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("프로필 분석 갱신안 심볼릭 링크는 읽을 수 없음")
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("프로필 분석 갱신안을 읽을 수 없음") from error
    if not isinstance(proposal, dict):
        raise ProfileDocumentError("프로필 분석 갱신안 최상위 JSON은 객체여야 함")
    stored_id, _ = _validated_proposal(proposal)
    if stored_id != normalized_id:
        raise ProfileDocumentError("프로필 분석 갱신안 ID가 요청과 일치하지 않음")
    return deepcopy(proposal)


def select_latest_profile_analysis_update_proposal(
    profile_document: Mapping[str, Any],
    directory: str | Path,
) -> dict[str, Any] | None:
    """Select the newest verified proposal for the current profile content."""

    expected_hash = profile_content_sha256(profile_document)
    target_directory = Path(directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("프로필 분석 갱신안 경로가 안전한 디렉터리가 아님")
    paths = sorted(
        target_directory.glob("profile-analysis-update-proposal-*.json")
    )
    if len(paths) > _MAX_STORED_PROPOSAL_FILES:
        raise ProfileDocumentError("프로필 분석 갱신안 파일이 허용 개수를 초과함")

    matches: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        proposal = load_profile_analysis_update_proposal(
            path.stem,
            target_directory,
        )
        proposal_id, created_at = _validated_proposal(proposal)
        root = _mapping(
            proposal.get("profile_analysis_update_proposal"),
            "profile_analysis_update_proposal",
        )
        if root.get("base_profile_content_sha256") == expected_hash:
            matches.append((created_at, proposal_id, proposal))
    if not matches:
        return None
    return deepcopy(max(matches, key=lambda value: (value[0], value[1]))[2])
