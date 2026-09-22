"""Record an explicit user decision for one final profile update proposal."""

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

from .analysis_final_proposal import validate_profile_analysis_final_proposal
from .document_store import ProfileDocumentError


PROFILE_ANALYSIS_FINAL_REVIEW_SCHEMA_VERSION = "0.1"
PROFILE_ANALYSIS_FINAL_REVIEW_DECISIONS = frozenset({"approve", "reject"})
_REVIEW_ID_PATTERN = re.compile(r"^profile-analysis-final-review-[0-9a-f]{24}$")
_FINAL_ID_PATTERN = re.compile(r"^profile-analysis-final-proposal-[0-9a-f]{24}$")
_PROFILE_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_STORED_REVIEW_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 올바르지 않음")
    return value


def _validate(review: Mapping[str, Any]) -> tuple[str, datetime]:
    if set(review) != {"profile_analysis_final_review", "source", "metadata"}:
        raise ProfileDocumentError("최종 변경안 검토 기록 필드 구성이 올바르지 않음")
    root = _mapping(review.get("profile_analysis_final_review"), "review")
    source = _mapping(review.get("source"), "source")
    metadata = _mapping(review.get("metadata"), "metadata")
    if set(root) != {"review_id", "reviewed_at", "review_source", "decision"}:
        raise ProfileDocumentError("최종 변경안 검토 필드 구성이 올바르지 않음")
    if set(source) != {"final_proposal_id", "base_profile_id", "base_profile_content_sha256"}:
        raise ProfileDocumentError("최종 변경안 검토 출처 구성이 올바르지 않음")
    review_id = _text(root.get("review_id"), "review.review_id")
    if _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
        raise ProfileDocumentError("최종 변경안 검토 ID가 올바르지 않음")
    reviewed_at_text = _text(root.get("reviewed_at"), "review.reviewed_at")
    try:
        reviewed_at = datetime.fromisoformat(reviewed_at_text)
    except ValueError as error:
        raise ProfileDocumentError("최종 변경안 검토 시간이 올바르지 않음") from error
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ProfileDocumentError("최종 변경안 검토 시간에 시간대가 필요함")
    if root.get("review_source") != "explicit_user_input":
        raise ProfileDocumentError("최종 변경안 검토는 명시적 사용자 입력이어야 함")
    if root.get("decision") not in PROFILE_ANALYSIS_FINAL_REVIEW_DECISIONS:
        raise ProfileDocumentError("최종 변경안 검토 결정이 올바르지 않음")
    final_id = _text(source.get("final_proposal_id"), "source.final_proposal_id")
    if _FINAL_ID_PATTERN.fullmatch(final_id) is None:
        raise ProfileDocumentError("최종 변경안 ID가 올바르지 않음")
    _text(source.get("base_profile_id"), "source.base_profile_id")
    profile_hash = _text(source.get("base_profile_content_sha256"), "source.base_profile_content_sha256")
    if _PROFILE_HASH_PATTERN.fullmatch(profile_hash) is None:
        raise ProfileDocumentError("최종 변경안 검토의 프로필 지문이 올바르지 않음")
    identity = "|".join((final_id, reviewed_at_text, str(root["decision"])))
    expected_id = "profile-analysis-final-review-" + sha256(identity.encode("utf-8")).hexdigest()[:24]
    if review_id != expected_id:
        raise ProfileDocumentError("최종 변경안 검토 ID와 내용 지문이 일치하지 않음")
    if metadata != {
        "schema_version": PROFILE_ANALYSIS_FINAL_REVIEW_SCHEMA_VERSION,
        "contains_proposal_content": False,
        "contains_personal_data": True,
        "git_tracking_allowed": False,
        "profile_updated": False,
    }:
        raise ProfileDocumentError("최종 변경안 검토 메타데이터가 올바르지 않음")
    return review_id, reviewed_at


def validate_profile_analysis_final_review(review: Mapping[str, Any]) -> dict[str, Any]:
    _validate(review)
    return deepcopy(dict(review))


def build_profile_analysis_final_review(
    final_proposal: Mapping[str, Any],
    *,
    decision: str,
    reviewed_at: datetime,
) -> dict[str, Any]:
    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ProfileDocumentError("reviewed_at은 시간대가 포함되어야 함")
    if decision not in PROFILE_ANALYSIS_FINAL_REVIEW_DECISIONS:
        raise ProfileDocumentError("최종 변경안 검토 결정이 올바르지 않음")
    proposal = validate_profile_analysis_final_proposal(final_proposal)
    proposal_root = proposal["profile_analysis_final_proposal"]
    reviewed_at_text = reviewed_at.isoformat(timespec="microseconds")
    final_id = str(proposal_root["final_proposal_id"])
    review_id = "profile-analysis-final-review-" + sha256(
        "|".join((final_id, reviewed_at_text, decision)).encode("utf-8")
    ).hexdigest()[:24]
    review = {
        "profile_analysis_final_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_at_text,
            "review_source": "explicit_user_input",
            "decision": decision,
        },
        "source": {
            "final_proposal_id": final_id,
            "base_profile_id": proposal_root["base_profile_id"],
            "base_profile_content_sha256": proposal_root["base_profile_content_sha256"],
        },
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_FINAL_REVIEW_SCHEMA_VERSION,
            "contains_proposal_content": False,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }
    return validate_profile_analysis_final_review(review)


def save_profile_analysis_final_review(review: Mapping[str, Any], directory: str | Path) -> Path:
    validated = validate_profile_analysis_final_review(review)
    review_id = validated["profile_analysis_final_review"]["review_id"]
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{review_id}.json"
    if target_path.exists():
        raise ProfileDocumentError("최종 변경안 검토 파일이 이미 존재함")
    serialized = json.dumps(validated, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=target_directory, prefix=f".{review_id}.", suffix=".tmp", delete=False) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("최종 변경안 검토 기록을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def load_profile_analysis_final_review(review_id: str, directory: str | Path) -> dict[str, Any]:
    if not isinstance(review_id, str) or _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
        raise ProfileDocumentError("최종 변경안 검토 ID가 올바르지 않음")
    path = Path(directory) / f"{review_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("최종 변경안 검토 심볼릭 링크는 읽을 수 없음")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("최종 변경안 검토 기록을 읽을 수 없음") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError("최종 변경안 검토 최상위 JSON은 객체여야 함")
    validated = validate_profile_analysis_final_review(value)
    if validated["profile_analysis_final_review"]["review_id"] != review_id:
        raise ProfileDocumentError("최종 변경안 검토 ID가 요청과 일치하지 않음")
    return validated


def select_latest_profile_analysis_final_review(final_proposal_id: str, directory: str | Path) -> dict[str, Any] | None:
    if not isinstance(final_proposal_id, str) or _FINAL_ID_PATTERN.fullmatch(final_proposal_id) is None:
        raise ProfileDocumentError("최종 변경안 ID가 올바르지 않음")
    target_directory = Path(directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("최종 변경안 검토 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("profile-analysis-final-review-*.json"))
    if len(paths) > _MAX_STORED_REVIEW_FILES:
        raise ProfileDocumentError("최종 변경안 검토 파일이 허용 개수를 초과함")
    candidates: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        review = load_profile_analysis_final_review(path.stem, target_directory)
        if review["source"]["final_proposal_id"] == final_proposal_id:
            root = review["profile_analysis_final_review"]
            _, reviewed_at = _validate(review)
            candidates.append((reviewed_at, str(root["review_id"]), review))
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda value: (value[0], value[1]))[2])
