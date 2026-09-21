"""Record explicit user decisions for profile analysis draft items."""

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


PROFILE_ANALYSIS_REVIEW_SCHEMA_VERSION = "0.1"
PROFILE_ANALYSIS_REVIEW_DECISIONS = frozenset({"approve", "reject"})
PROFILE_ANALYSIS_ITEM_TYPES = frozenset(
    {
        "career_evidence",
        "achievement_evidence",
        "technology_evidence",
        "unknowns",
    }
)
MAX_PROFILE_ANALYSIS_REVIEW_NOTES_CHARS = 1000
_REVIEW_ID_PATTERN = re.compile(r"^profile-analysis-review-[0-9a-f]{24}$")
_DRAFT_ID_PATTERN = re.compile(r"^profile-analysis-draft-[0-9a-f]{24}$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_MAX_STORED_REVIEW_FILES = 1000


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise ProfileDocumentError(f"{name} 필수 필드 누락: {', '.join(missing)}")
    if extra:
        raise ProfileDocumentError(f"{name} 허용되지 않은 필드: {', '.join(extra)}")


def _reviewed_datetime(value: Any) -> tuple[str, datetime]:
    normalized = _text(value, "profile_analysis_review.reviewed_at")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as error:
        raise ProfileDocumentError("프로필 분석 검토 시간이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError("프로필 분석 검토 시간에 시간대가 필요함")
    return normalized, parsed


def _validated_review(review: Mapping[str, Any]) -> tuple[str, datetime]:
    _exact_keys(
        review,
        {"profile_analysis_review", "source", "metadata"},
        "profile_analysis_review_document",
    )
    root = _mapping(review.get("profile_analysis_review"), "profile_analysis_review")
    source = _mapping(review.get("source"), "source")
    metadata = _mapping(review.get("metadata"), "metadata")
    _exact_keys(
        root,
        {"review_id", "reviewed_at", "decision", "notes"},
        "profile_analysis_review",
    )
    _exact_keys(
        source,
        {"draft_id", "extraction_id", "item_type", "item_position"},
        "source",
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
    if metadata.get("schema_version") != PROFILE_ANALYSIS_REVIEW_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 분석 검토 기록이 아님")
    if metadata.get("contains_personal_data") is not True:
        raise ProfileDocumentError("프로필 분석 검토 기록의 개인정보 표시가 없음")
    if metadata.get("contains_analysis_text") is not False:
        raise ProfileDocumentError("분석 검토 기록에 분석 문장 제외 표시가 없음")
    if metadata.get("contains_candidate_text") is not False:
        raise ProfileDocumentError("분석 검토 기록에 후보 문장 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("분석 검토 기록에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("분석 검토 기록은 프로필 갱신 상태일 수 없음")

    review_id = _text(root.get("review_id"), "profile_analysis_review.review_id")
    if _REVIEW_ID_PATTERN.fullmatch(review_id) is None:
        raise ProfileDocumentError("프로필 분석 검토 ID가 올바르지 않음")
    reviewed_timestamp, reviewed_at = _reviewed_datetime(root.get("reviewed_at"))
    decision = root.get("decision")
    if decision not in PROFILE_ANALYSIS_REVIEW_DECISIONS:
        raise ProfileDocumentError("프로필 분석 검토 결정이 올바르지 않음")
    notes = root.get("notes")
    if notes is not None and (
        not isinstance(notes, str)
        or not notes.strip()
        or notes != notes.strip()
        or len(notes) > MAX_PROFILE_ANALYSIS_REVIEW_NOTES_CHARS
    ):
        raise ProfileDocumentError("프로필 분석 검토 메모가 올바르지 않음")

    draft_id = _text(source.get("draft_id"), "source.draft_id")
    if _DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ProfileDocumentError("프로필 분석 검토 초안 ID가 올바르지 않음")
    extraction_id = _text(source.get("extraction_id"), "source.extraction_id")
    if _EXTRACTION_ID_PATTERN.fullmatch(extraction_id) is None:
        raise ProfileDocumentError("프로필 분석 검토 추출 ID가 올바르지 않음")
    item_type = source.get("item_type")
    if item_type not in PROFILE_ANALYSIS_ITEM_TYPES:
        raise ProfileDocumentError("프로필 분석 검토 항목 종류가 올바르지 않음")
    item_position = source.get("item_position")
    if (
        isinstance(item_position, bool)
        or not isinstance(item_position, int)
        or item_position < 1
    ):
        raise ProfileDocumentError("프로필 분석 검토 항목 순번이 올바르지 않음")

    review_key = (
        f"{draft_id}|{item_type}|{item_position}|{reviewed_timestamp}|{decision}|"
        f"{json.dumps(notes, ensure_ascii=False, separators=(',', ':'))}"
    )
    expected_id = "profile-analysis-review-" + sha256(
        review_key.encode("utf-8")
    ).hexdigest()[:24]
    if review_id != expected_id:
        raise ProfileDocumentError("프로필 분석 검토 ID와 내용 지문이 일치하지 않음")
    return review_id, reviewed_at


def build_profile_analysis_review(
    draft: Mapping[str, Any],
    *,
    item_type: str,
    item_position: int,
    decision: str,
    reviewed_at: datetime,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one immutable decision without copying analysis or candidate text."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ProfileDocumentError("reviewed_at은 시간대가 포함되어야 함")
    if item_type not in PROFILE_ANALYSIS_ITEM_TYPES:
        allowed = ", ".join(sorted(PROFILE_ANALYSIS_ITEM_TYPES))
        raise ProfileDocumentError(f"item_type 허용값: {allowed}")
    if (
        isinstance(item_position, bool)
        or not isinstance(item_position, int)
        or item_position < 1
    ):
        raise ProfileDocumentError("item_position은 1 이상의 정수여야 함")
    if decision not in PROFILE_ANALYSIS_REVIEW_DECISIONS:
        allowed = ", ".join(sorted(PROFILE_ANALYSIS_REVIEW_DECISIONS))
        raise ProfileDocumentError(f"decision 허용값: {allowed}")
    normalized_notes = None
    if notes is not None:
        if not isinstance(notes, str):
            raise ProfileDocumentError("notes는 문자열이어야 함")
        normalized_notes = notes.strip() or None
        if (
            normalized_notes is not None
            and len(normalized_notes) > MAX_PROFILE_ANALYSIS_REVIEW_NOTES_CHARS
        ):
            raise ProfileDocumentError(
                f"notes는 {MAX_PROFILE_ANALYSIS_REVIEW_NOTES_CHARS}자 이하여야 함"
            )

    validated = validate_profile_analysis_draft(draft)
    root = _mapping(
        validated.get("profile_analysis_draft"),
        "profile_analysis_draft",
    )
    analysis = _mapping(validated.get("analysis"), "analysis")
    items = analysis.get(item_type)
    if not isinstance(items, list):
        raise ProfileDocumentError(f"analysis.{item_type} 배열이 필요함")
    if item_position > len(items):
        raise ProfileDocumentError(
            f"analysis.{item_type}에 {item_position}번 항목이 없음"
        )

    draft_id = _text(root.get("draft_id"), "profile_analysis_draft.draft_id")
    extraction_id = _text(
        root.get("source_extraction_id"),
        "profile_analysis_draft.source_extraction_id",
    )
    reviewed_timestamp = reviewed_at.isoformat(timespec="microseconds")
    review_key = (
        f"{draft_id}|{item_type}|{item_position}|{reviewed_timestamp}|{decision}|"
        f"{json.dumps(normalized_notes, ensure_ascii=False, separators=(',', ':'))}"
    )
    review_id = "profile-analysis-review-" + sha256(
        review_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "profile_analysis_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_timestamp,
            "decision": decision,
            "notes": normalized_notes,
        },
        "source": {
            "draft_id": draft_id,
            "extraction_id": extraction_id,
            "item_type": item_type,
            "item_position": item_position,
        },
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_REVIEW_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_analysis_text": False,
            "contains_candidate_text": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_analysis_review(
    review: Mapping[str, Any],
    directory: str | Path,
) -> Path:
    """Atomically save one immutable profile analysis review."""

    review_id, _ = _validated_review(review)
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{review_id}.json"
    if target_path.exists():
        raise ProfileDocumentError(f"프로필 분석 검토 파일이 이미 존재함: {target_path}")

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
        raise ProfileDocumentError("프로필 분석 검토 기록을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def validate_profile_analysis_review(
    review: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate one stored-shape review and return an isolated copy."""

    _validated_review(review)
    return deepcopy(dict(review))


def load_profile_analysis_review(
    review_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load and verify one immutable private profile analysis review."""

    normalized_id = _text(review_id, "review_id")
    if _REVIEW_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("프로필 분석 검토 ID가 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("프로필 분석 검토 심볼릭 링크는 읽을 수 없음")
    try:
        review = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"프로필 분석 검토 기록을 읽을 수 없음: {path}") from error
    if not isinstance(review, dict):
        raise ProfileDocumentError("프로필 분석 검토 최상위 JSON은 객체여야 함")
    stored_id, _ = _validated_review(review)
    if stored_id != normalized_id:
        raise ProfileDocumentError("프로필 분석 검토 ID가 요청과 일치하지 않음")
    return deepcopy(review)


def select_latest_profile_analysis_reviews(
    draft_id: str,
    directory: str | Path,
) -> dict[tuple[str, int], dict[str, Any]]:
    """Return the newest verified decision for every item in one draft."""

    normalized_draft_id = _text(draft_id, "draft_id")
    if _DRAFT_ID_PATTERN.fullmatch(normalized_draft_id) is None:
        raise ProfileDocumentError("프로필 분석 초안 ID가 올바르지 않음")
    target_directory = Path(directory)
    if not target_directory.exists():
        return {}
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("프로필 분석 검토 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("profile-analysis-review-*.json"))
    if len(paths) > _MAX_STORED_REVIEW_FILES:
        raise ProfileDocumentError("프로필 분석 검토 파일이 허용 개수를 초과함")

    selected: dict[
        tuple[str, int], tuple[datetime, str, dict[str, Any]]
    ] = {}
    for path in paths:
        review = load_profile_analysis_review(path.stem, target_directory)
        _, reviewed_at = _validated_review(review)
        source = _mapping(review.get("source"), "source")
        if source.get("draft_id") != normalized_draft_id:
            continue
        key = (str(source["item_type"]), int(source["item_position"]))
        candidate = (reviewed_at, path.stem, review)
        current = selected.get(key)
        if current is None or candidate[:2] > current[:2]:
            selected[key] = candidate
    return {key: deepcopy(value[2]) for key, value in selected.items()}
