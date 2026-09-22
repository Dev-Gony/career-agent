"""Resolve every approved analysis change into one final review proposal."""

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

from .analysis_mapping_review import validate_profile_analysis_mapping_review
from .analysis_update_proposal import validate_profile_analysis_update_proposal
from .document_store import ProfileDocumentError
from .update_proposal import profile_content_sha256


PROFILE_ANALYSIS_FINAL_PROPOSAL_SCHEMA_VERSION = "0.1"
_FINAL_ID_PATTERN = re.compile(r"^profile-analysis-final-proposal-[0-9a-f]{24}$")
_PROPOSAL_ID_PATTERN = re.compile(r"^profile-analysis-update-proposal-[0-9a-f]{24}$")
_PROFILE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_REVIEW_ID_PATTERN = re.compile(r"^profile-analysis-mapping-review-[0-9a-f]{24}$")
_MAX_STORED_FINAL_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str, *, max_chars: int = 1000) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > max_chars
    ):
        raise ProfileDocumentError(f"{name} 문자열이 올바르지 않음")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
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


def _identity(proposal: Mapping[str, Any]) -> str:
    root = _mapping(proposal.get("profile_analysis_final_proposal"), "proposal")
    serialized = json.dumps(
        {
            "base_profile_content_sha256": root.get("base_profile_content_sha256"),
            "source_proposal_id": root.get("source_proposal_id"),
            "mapping_review_snapshot": proposal.get("mapping_review_snapshot"),
            "resolved_changes": proposal.get("resolved_changes"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "profile-analysis-final-proposal-" + sha256(
        serialized.encode("utf-8")
    ).hexdigest()[:24]


def validate_profile_analysis_final_proposal(
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the self-contained final proposal and its content identity."""

    _exact_keys(
        proposal,
        {
            "profile_analysis_final_proposal",
            "summary",
            "mapping_review_snapshot",
            "resolved_changes",
            "metadata",
        },
        "profile_analysis_final_proposal_document",
    )
    root = _mapping(proposal.get("profile_analysis_final_proposal"), "proposal")
    summary = _mapping(proposal.get("summary"), "summary")
    metadata = _mapping(proposal.get("metadata"), "metadata")
    _exact_keys(
        root,
        {
            "final_proposal_id",
            "created_at",
            "status",
            "base_profile_id",
            "base_profile_content_sha256",
            "source_proposal_id",
        },
        "profile_analysis_final_proposal",
    )
    summary_fields = {
        "change_count",
        "career_evidence_count",
        "achievement_evidence_count",
        "existing_skill_evidence_count",
        "new_skill_count",
    }
    _exact_keys(summary, summary_fields, "summary")
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
    final_id = _text(root.get("final_proposal_id"), "proposal.final_proposal_id")
    if _FINAL_ID_PATTERN.fullmatch(final_id) is None:
        raise ProfileDocumentError("최종 프로필 변경안 ID가 올바르지 않음")
    _timestamp(root.get("created_at"), "proposal.created_at")
    if root.get("status") != "ready_for_final_review":
        raise ProfileDocumentError("최종 프로필 변경안 상태가 올바르지 않음")
    _text(root.get("base_profile_id"), "proposal.base_profile_id")
    profile_hash = _text(
        root.get("base_profile_content_sha256"),
        "proposal.base_profile_content_sha256",
        max_chars=64,
    )
    if _PROFILE_HASH_PATTERN.fullmatch(profile_hash) is None:
        raise ProfileDocumentError("최종 프로필 변경안의 기준 프로필 지문이 올바르지 않음")
    source_proposal_id = _text(root.get("source_proposal_id"), "proposal.source_proposal_id")
    if _PROPOSAL_ID_PATTERN.fullmatch(source_proposal_id) is None:
        raise ProfileDocumentError("최종 프로필 변경안의 출처 제안 ID가 올바르지 않음")

    snapshot = proposal.get("mapping_review_snapshot")
    changes = proposal.get("resolved_changes")
    if not isinstance(snapshot, list) or not isinstance(changes, list) or not changes:
        raise ProfileDocumentError("최종 프로필 변경안의 기록과 변경 배열이 올바르지 않음")
    snapshot_by_change: dict[str, Mapping[str, Any]] = {}
    for position, raw_item in enumerate(snapshot):
        item = _mapping(raw_item, f"mapping_review_snapshot[{position}]")
        _exact_keys(
            item,
            {"change_id", "review_id", "reviewed_at", "selected_value"},
            f"mapping_review_snapshot[{position}]",
        )
        change_id = _text(item.get("change_id"), "snapshot.change_id")
        review_id = _text(item.get("review_id"), "snapshot.review_id")
        if _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
            raise ProfileDocumentError("최종 프로필 변경안의 매핑 검토 ID가 올바르지 않음")
        _timestamp(item.get("reviewed_at"), "snapshot.reviewed_at")
        _text(item.get("selected_value"), "snapshot.selected_value")
        if change_id in snapshot_by_change:
            raise ProfileDocumentError("최종 프로필 변경안에 중복 매핑 기록이 있음")
        snapshot_by_change[change_id] = item

    counted = {field: 0 for field in summary_fields}
    change_ids: set[str] = set()
    mapped_change_ids: set[str] = set()
    for position, raw_change in enumerate(changes, start=1):
        change = _mapping(raw_change, f"resolved_changes[{position - 1}]")
        _exact_keys(
            change,
            {"change_id", "source", "target", "proposed_value"},
            f"resolved_changes[{position - 1}]",
        )
        change_id = _text(change.get("change_id"), "change.change_id")
        if change_id in change_ids:
            raise ProfileDocumentError("최종 프로필 변경안에 중복 변경 ID가 있음")
        change_ids.add(change_id)
        source = _mapping(change.get("source"), "change.source")
        target = _mapping(change.get("target"), "change.target")
        value = _mapping(change.get("proposed_value"), "change.proposed_value")
        _exact_keys(source, {"item_type", "review_id"}, "change.source")
        _exact_keys(
            target,
            {"profile_section", "record_id", "operation"},
            "change.target",
        )
        item_type = source.get("item_type")
        operation = target.get("operation")
        if item_type == "career_evidence":
            expected = ("career_history", "append_responsibility_evidence")
            expected_fields = {"role_or_context", "period_expression", "responsibility_evidence"}
            counted["career_evidence_count"] += 1
            mapped_change_ids.add(change_id)
        elif item_type == "achievement_evidence":
            expected = ("career_history", "append_achievement_evidence")
            expected_fields = {"problem_evidence", "action_evidence", "result_evidence"}
            counted["achievement_evidence_count"] += 1
            mapped_change_ids.add(change_id)
        elif item_type == "technology_evidence" and operation == "append_skill_evidence":
            expected = ("skills", "append_skill_evidence")
            expected_fields = {"technology_name", "usage_evidence", "proposed_level"}
            counted["existing_skill_evidence_count"] += 1
        elif item_type == "technology_evidence" and operation == "add_skill_with_evidence":
            expected = ("skills", "add_skill_with_evidence")
            expected_fields = {"technology_name", "usage_evidence", "proposed_level"}
            counted["new_skill_count"] += 1
            mapped_change_ids.add(change_id)
        else:
            raise ProfileDocumentError("최종 프로필 변경안의 항목 종류 또는 동작이 올바르지 않음")
        if (target.get("profile_section"), operation) != expected:
            raise ProfileDocumentError("최종 프로필 변경안의 대상이 올바르지 않음")
        _text(target.get("record_id"), "change.target.record_id")
        _exact_keys(value, expected_fields, "change.proposed_value")
        for field, raw_value in value.items():
            if raw_value is not None:
                _text(raw_value, f"change.proposed_value.{field}")
        if operation == "add_skill_with_evidence" and value.get("proposed_level") is None:
            raise ProfileDocumentError("새 기술의 확인된 숙련도가 없음")
        if operation == "append_skill_evidence" and value.get("proposed_level") is not None:
            raise ProfileDocumentError("기존 기술 근거 추가는 숙련도를 변경할 수 없음")

    if set(snapshot_by_change) != mapped_change_ids:
        raise ProfileDocumentError("최종 프로필 변경안의 매핑 기록과 변경 항목이 일치하지 않음")
    counted["change_count"] = len(changes)
    for field in summary_fields:
        value = summary.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value != counted[field]:
            raise ProfileDocumentError(f"summary.{field} 합계가 일치하지 않음")
    if metadata.get("schema_version") != PROFILE_ANALYSIS_FINAL_PROPOSAL_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 최종 프로필 변경안이 아님")
    if metadata.get("contains_personal_data") is not True:
        raise ProfileDocumentError("최종 프로필 변경안 개인정보 표시가 없음")
    if metadata.get("contains_analysis_text") is not True:
        raise ProfileDocumentError("최종 프로필 변경안 분석 문장 표시가 없음")
    for field in ("contains_candidate_text", "git_tracking_allowed", "profile_updated"):
        if metadata.get(field) is not False:
            raise ProfileDocumentError(f"최종 프로필 변경안 {field} 표시가 올바르지 않음")
    if final_id != _identity(proposal):
        raise ProfileDocumentError("최종 프로필 변경안 ID와 내용 지문이 일치하지 않음")
    return deepcopy(dict(proposal))


def build_profile_analysis_final_proposal(
    profile_document: Mapping[str, Any],
    source_proposal: Mapping[str, Any],
    mapping_reviews: Mapping[str, Mapping[str, Any]],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    """Resolve all required mappings and create one final-review snapshot."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProfileDocumentError("created_at은 시간대가 포함되어야 함")
    source = validate_profile_analysis_update_proposal(source_proposal)
    source_root = _mapping(source.get("profile_analysis_update_proposal"), "source_proposal")
    if source_root.get("base_profile_content_sha256") != profile_content_sha256(profile_document):
        raise ProfileDocumentError("프로필 변경 제안의 기준 프로필이 현재 프로필과 다름")
    profile = _mapping(profile_document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    careers = profile.get("career_history")
    if not isinstance(careers, list):
        raise ProfileDocumentError("profile.career_history 배열이 필요함")
    career_ids = {
        _text(_mapping(item, "career_history item").get("career_id"), "career_id")
        for item in careers
    }
    skills = profile.get("skills")
    if not isinstance(skills, list):
        raise ProfileDocumentError("profile.skills 배열이 필요함")
    reserved_skill_ids = {
        _text(_mapping(item, "skills item").get("skill_id"), "skill_id")
        for item in skills
    }

    proposal_id = str(source_root["proposal_id"])
    validated_reviews: dict[str, dict[str, Any]] = {}
    for key, raw_review in mapping_reviews.items():
        review = validate_profile_analysis_mapping_review(raw_review)
        review_source = _mapping(review.get("source"), "mapping_review.source")
        if (
            key != review_source.get("change_id")
            or review_source.get("proposal_id") != proposal_id
        ):
            raise ProfileDocumentError("매핑 검토 기록이 현재 변경 제안과 일치하지 않음")
        validated_reviews[key] = review

    resolved_changes: list[dict[str, Any]] = []
    snapshot: list[dict[str, Any]] = []
    source_change_ids: set[str] = set()
    for raw_change in source.get("proposed_changes", []):
        change = deepcopy(dict(_mapping(raw_change, "proposed_changes item")))
        change_id = str(change["change_id"])
        source_change_ids.add(change_id)
        target = dict(_mapping(change.get("target"), "change.target"))
        value = dict(_mapping(change.get("proposed_value"), "change.proposed_value"))
        mapping_status = target.pop("mapping_status")
        review = validated_reviews.get(change_id)
        if mapping_status == "needs_career_selection":
            if review is None:
                raise ProfileDocumentError("모든 경력 매핑을 완료해야 최종 변경안을 만들 수 있음")
            selected = str(review["profile_analysis_mapping_review"]["selected_value"])
            if selected not in career_ids:
                raise ProfileDocumentError("선택한 경력 ID가 현재 프로필에 없음")
            target["record_id"] = selected
        elif mapping_status == "needs_skill_level_confirmation":
            if review is None:
                raise ProfileDocumentError("모든 기술 숙련도를 확인해야 최종 변경안을 만들 수 있음")
            selected = str(review["profile_analysis_mapping_review"]["selected_value"])
            value["proposed_level"] = selected
            technology_name = _text(value.get("technology_name"), "technology_name")
            slug = re.sub(r"[^a-z0-9]+", "-", technology_name.casefold()).strip("-")
            if not slug:
                slug = sha256(technology_name.encode("utf-8")).hexdigest()[:12]
            generated_skill_id = f"skill-{slug[:60]}"
            if generated_skill_id in reserved_skill_ids:
                raise ProfileDocumentError("새 기술 ID가 현재 프로필 또는 변경안에서 중복됨")
            reserved_skill_ids.add(generated_skill_id)
            target["record_id"] = generated_skill_id
        elif mapping_status == "ready_for_final_review":
            if review is not None:
                raise ProfileDocumentError("매핑이 필요 없는 변경에 선택 기록이 있음")
            selected = None
        else:
            raise ProfileDocumentError("프로필 변경 항목의 매핑 상태가 올바르지 않음")
        if review is not None:
            review_root = review["profile_analysis_mapping_review"]
            snapshot.append(
                {
                    "change_id": change_id,
                    "review_id": review_root["review_id"],
                    "reviewed_at": review_root["reviewed_at"],
                    "selected_value": selected,
                }
            )
        change_source = _mapping(change.get("source"), "change.source")
        resolved_changes.append(
            {
                "change_id": change_id,
                "source": {
                    "item_type": change_source["item_type"],
                    "review_id": change_source["review_id"],
                },
                "target": target,
                "proposed_value": value,
            }
        )
    if set(validated_reviews) - source_change_ids:
        raise ProfileDocumentError("현재 변경 제안에 없는 매핑 검토 기록이 있음")
    if not resolved_changes:
        raise ProfileDocumentError("최종 검토할 프로필 변경이 없음")

    counts = {
        "change_count": len(resolved_changes),
        "career_evidence_count": sum(
            item["source"]["item_type"] == "career_evidence" for item in resolved_changes
        ),
        "achievement_evidence_count": sum(
            item["source"]["item_type"] == "achievement_evidence" for item in resolved_changes
        ),
        "existing_skill_evidence_count": sum(
            item["target"]["operation"] == "append_skill_evidence" for item in resolved_changes
        ),
        "new_skill_count": sum(
            item["target"]["operation"] == "add_skill_with_evidence" for item in resolved_changes
        ),
    }
    created_at_text = created_at.isoformat(timespec="microseconds")
    result: dict[str, Any] = {
        "profile_analysis_final_proposal": {
            "final_proposal_id": "",
            "created_at": created_at_text,
            "status": "ready_for_final_review",
            "base_profile_id": source_root["base_profile_id"],
            "base_profile_content_sha256": source_root["base_profile_content_sha256"],
            "source_proposal_id": proposal_id,
        },
        "summary": counts,
        "mapping_review_snapshot": snapshot,
        "resolved_changes": resolved_changes,
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_FINAL_PROPOSAL_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_analysis_text": True,
            "contains_candidate_text": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    result["profile_analysis_final_proposal"]["final_proposal_id"] = _identity(result)
    return validate_profile_analysis_final_proposal(result)


def save_profile_analysis_final_proposal(
    proposal: Mapping[str, Any], directory: str | Path
) -> tuple[Path, bool]:
    validated = validate_profile_analysis_final_proposal(proposal)
    final_id = validated["profile_analysis_final_proposal"]["final_proposal_id"]
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{final_id}.json"
    if target_path.exists():
        existing = load_profile_analysis_final_proposal(final_id, target_directory)
        if existing != validated:
            raise ProfileDocumentError("같은 최종 변경안 ID의 기존 내용이 일치하지 않음")
        return target_path, False
    serialized = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target_directory,
            prefix=f".{final_id}.", suffix=".tmp", delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("최종 프로필 변경안을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def load_profile_analysis_final_proposal(
    final_proposal_id: str, directory: str | Path
) -> dict[str, Any]:
    final_proposal_id = _text(final_proposal_id, "final_proposal_id")
    if _FINAL_ID_PATTERN.fullmatch(final_proposal_id) is None:
        raise ProfileDocumentError("최종 프로필 변경안 ID가 올바르지 않음")
    path = Path(directory) / f"{final_proposal_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("최종 프로필 변경안 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("최종 프로필 변경안을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError("최종 프로필 변경안 최상위 JSON은 객체여야 함")
    validated = validate_profile_analysis_final_proposal(value)
    if validated["profile_analysis_final_proposal"]["final_proposal_id"] != final_proposal_id:
        raise ProfileDocumentError("최종 프로필 변경안 ID가 요청과 일치하지 않음")
    return validated
