"""Record a user's mapping choice for one approved profile-analysis change."""

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

from .analysis_update_proposal import validate_profile_analysis_update_proposal
from .document_store import ProfileDocumentError
from .skill_confirmation import SKILL_LEVELS
from .update_proposal import profile_content_sha256


PROFILE_ANALYSIS_MAPPING_REVIEW_SCHEMA_VERSION = "0.1"
_REVIEW_ID_PATTERN = re.compile(r"^profile-analysis-mapping-review-[0-9a-f]{24}$")
_PROPOSAL_ID_PATTERN = re.compile(r"^profile-analysis-update-proposal-[0-9a-f]{24}$")
_CHANGE_ID_PATTERN = re.compile(r"^analysis-change-[0-9]{3}$")
_CAREER_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_DECISION_TYPES = {
    "needs_career_selection": "career_selection",
    "needs_skill_level_confirmation": "skill_level_confirmation",
}
_MAX_STORED_REVIEW_FILES = 2000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str, *, max_chars: int = 200) -> str:
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
    normalized = _text(value, name)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}에 시간대가 필요함")
    return normalized, parsed


def _identity(
    *,
    reviewed_at: str,
    decision_type: str,
    selected_value: str,
    proposal_id: str,
    change_id: str,
    mapping_status: str,
) -> str:
    serialized = json.dumps(
        {
            "reviewed_at": reviewed_at,
            "decision_type": decision_type,
            "selected_value": selected_value,
            "proposal_id": proposal_id,
            "change_id": change_id,
            "mapping_status": mapping_status,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "profile-analysis-mapping-review-" + sha256(
        serialized.encode("utf-8")
    ).hexdigest()[:24]


def validate_profile_analysis_mapping_review(
    review: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one immutable mapping decision without needing source text."""

    _exact_keys(
        review,
        {"profile_analysis_mapping_review", "source", "metadata"},
        "profile_analysis_mapping_review_document",
    )
    root = _mapping(review.get("profile_analysis_mapping_review"), "review")
    source = _mapping(review.get("source"), "source")
    metadata = _mapping(review.get("metadata"), "metadata")
    _exact_keys(
        root,
        {"review_id", "reviewed_at", "decision_type", "selected_value"},
        "profile_analysis_mapping_review",
    )
    _exact_keys(source, {"proposal_id", "change_id", "mapping_status"}, "source")
    _exact_keys(
        metadata,
        {
            "schema_version",
            "contains_analysis_text",
            "contains_candidate_text",
            "contains_personal_data",
            "git_tracking_allowed",
            "profile_updated",
        },
        "metadata",
    )

    review_id = _text(root.get("review_id"), "review.review_id")
    if _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
        raise ProfileDocumentError("프로필 변경 매핑 검토 ID가 올바르지 않음")
    reviewed_at_text, _ = _timestamp(root.get("reviewed_at"), "review.reviewed_at")
    proposal_id = _text(source.get("proposal_id"), "source.proposal_id")
    if _PROPOSAL_ID_PATTERN.fullmatch(proposal_id) is None:
        raise ProfileDocumentError("프로필 변경 제안 ID가 올바르지 않음")
    change_id = _text(source.get("change_id"), "source.change_id")
    if _CHANGE_ID_PATTERN.fullmatch(change_id) is None:
        raise ProfileDocumentError("프로필 변경 항목 ID가 올바르지 않음")
    mapping_status = source.get("mapping_status")
    expected_decision_type = _DECISION_TYPES.get(mapping_status)
    if expected_decision_type is None:
        raise ProfileDocumentError("프로필 변경 매핑 상태가 올바르지 않음")
    decision_type = root.get("decision_type")
    if decision_type != expected_decision_type:
        raise ProfileDocumentError("프로필 변경 매핑 결정 종류가 상태와 일치하지 않음")
    selected_value = _text(root.get("selected_value"), "review.selected_value")
    if decision_type == "career_selection":
        if _CAREER_ID_PATTERN.fullmatch(selected_value) is None:
            raise ProfileDocumentError("선택한 경력 ID 형식이 올바르지 않음")
    elif selected_value not in SKILL_LEVELS:
        raise ProfileDocumentError("선택한 기술 숙련도가 올바르지 않음")

    if metadata.get("schema_version") != PROFILE_ANALYSIS_MAPPING_REVIEW_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 변경 매핑 검토가 아님")
    for field in (
        "contains_analysis_text",
        "contains_candidate_text",
        "git_tracking_allowed",
        "profile_updated",
    ):
        if metadata.get(field) is not False:
            raise ProfileDocumentError(f"프로필 변경 매핑 검토 {field} 표시가 올바르지 않음")
    if metadata.get("contains_personal_data") is not True:
        raise ProfileDocumentError("프로필 변경 매핑 검토 개인정보 표시가 없음")
    expected_id = _identity(
        reviewed_at=reviewed_at_text,
        decision_type=decision_type,
        selected_value=selected_value,
        proposal_id=proposal_id,
        change_id=change_id,
        mapping_status=str(mapping_status),
    )
    if review_id != expected_id:
        raise ProfileDocumentError("프로필 변경 매핑 검토 ID와 내용 지문이 일치하지 않음")
    return deepcopy(dict(review))


def build_profile_analysis_mapping_review(
    profile_document: Mapping[str, Any],
    proposal: Mapping[str, Any],
    *,
    change_id: str,
    selected_value: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    """Build a choice only when it is allowed by the current profile and proposal."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ProfileDocumentError("reviewed_at은 시간대가 포함되어야 함")
    validated = validate_profile_analysis_update_proposal(proposal)
    proposal_root = _mapping(
        validated.get("profile_analysis_update_proposal"), "proposal"
    )
    if proposal_root.get("base_profile_content_sha256") != profile_content_sha256(
        profile_document
    ):
        raise ProfileDocumentError("프로필 변경 제안의 기준 프로필이 현재 프로필과 다름")
    matches = [
        change
        for change in validated.get("proposed_changes", [])
        if isinstance(change, Mapping) and change.get("change_id") == change_id
    ]
    if len(matches) != 1:
        raise ProfileDocumentError("선택할 프로필 변경 항목을 하나로 확인할 수 없음")
    target = _mapping(matches[0].get("target"), "change.target")
    mapping_status = str(target.get("mapping_status"))
    decision_type = _DECISION_TYPES.get(mapping_status)
    if decision_type is None:
        raise ProfileDocumentError("이 프로필 변경 항목은 사용자 매핑이 필요하지 않음")
    selected_value = _text(selected_value, "selected_value")
    if decision_type == "career_selection":
        profile = _mapping(profile_document.get("profile"), "profile")
        careers = profile.get("career_history")
        if not isinstance(careers, list):
            raise ProfileDocumentError("profile.career_history 배열이 필요함")
        allowed = {
            str(_mapping(career, "career_history item").get("career_id"))
            for career in careers
        }
        if selected_value not in allowed:
            raise ProfileDocumentError("선택한 경력 ID가 현재 프로필에 없음")
    elif selected_value not in SKILL_LEVELS:
        raise ProfileDocumentError("선택한 기술 숙련도가 허용 범위가 아님")

    reviewed_at_text = reviewed_at.isoformat(timespec="microseconds")
    proposal_id = str(proposal_root["proposal_id"])
    review_id = _identity(
        reviewed_at=reviewed_at_text,
        decision_type=decision_type,
        selected_value=selected_value,
        proposal_id=proposal_id,
        change_id=change_id,
        mapping_status=mapping_status,
    )
    review = {
        "profile_analysis_mapping_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_at_text,
            "decision_type": decision_type,
            "selected_value": selected_value,
        },
        "source": {
            "proposal_id": proposal_id,
            "change_id": change_id,
            "mapping_status": mapping_status,
        },
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_MAPPING_REVIEW_SCHEMA_VERSION,
            "contains_analysis_text": False,
            "contains_candidate_text": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    return validate_profile_analysis_mapping_review(review)


def save_profile_analysis_mapping_review(
    review: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save an immutable private mapping decision."""

    validated = validate_profile_analysis_mapping_review(review)
    review_id = validated["profile_analysis_mapping_review"]["review_id"]
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{review_id}.json"
    if target_path.exists():
        raise ProfileDocumentError("프로필 변경 매핑 검토 파일이 이미 존재함")
    serialized = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
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
        raise ProfileDocumentError("프로필 변경 매핑 검토를 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_profile_analysis_mapping_review(
    review_id: str, directory: str | Path
) -> dict[str, Any]:
    """Load and verify one immutable mapping decision."""

    review_id = _text(review_id, "review_id")
    if _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
        raise ProfileDocumentError("프로필 변경 매핑 검토 ID가 올바르지 않음")
    path = Path(directory) / f"{review_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("프로필 변경 매핑 검토 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("프로필 변경 매핑 검토를 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError("프로필 변경 매핑 검토 최상위 JSON은 객체여야 함")
    validated = validate_profile_analysis_mapping_review(value)
    if validated["profile_analysis_mapping_review"]["review_id"] != review_id:
        raise ProfileDocumentError("프로필 변경 매핑 검토 ID가 요청과 일치하지 않음")
    return validated


def select_latest_profile_analysis_mapping_reviews(
    proposal_id: str, directory: str | Path
) -> dict[str, dict[str, Any]]:
    """Return the latest valid decision for each change in one proposal."""

    proposal_id = _text(proposal_id, "proposal_id")
    if _PROPOSAL_ID_PATTERN.fullmatch(proposal_id) is None:
        raise ProfileDocumentError("프로필 변경 제안 ID가 올바르지 않음")
    target_directory = Path(directory)
    if not target_directory.exists():
        return {}
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("프로필 변경 매핑 검토 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("profile-analysis-mapping-review-*.json"))
    if len(paths) > _MAX_STORED_REVIEW_FILES:
        raise ProfileDocumentError("프로필 변경 매핑 검토 파일이 허용 개수를 초과함")
    selected: dict[str, tuple[datetime, str, dict[str, Any]]] = {}
    for path in paths:
        review = load_profile_analysis_mapping_review(path.stem, target_directory)
        if review["source"]["proposal_id"] != proposal_id:
            continue
        root = review["profile_analysis_mapping_review"]
        _, reviewed_at = _timestamp(root["reviewed_at"], "review.reviewed_at")
        candidate = (reviewed_at, str(root["review_id"]), review)
        change_id = str(review["source"]["change_id"])
        current = selected.get(change_id)
        if current is None or candidate[:2] > current[:2]:
            selected[change_id] = candidate
    return {change_id: deepcopy(value[2]) for change_id, value in selected.items()}
