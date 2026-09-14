"""Record an explicit user decision for one extracted profile candidate."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .document_store import ProfileDocumentError
from .text_extraction import PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION


PROFILE_CANDIDATE_REVIEW_SCHEMA_VERSION = "0.1"
CANDIDATE_REVIEW_DECISIONS = frozenset({"approve", "reject"})


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _candidate(
    extraction: Mapping[str, Any], candidate_id: str
) -> tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]:
    root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    source = _mapping(extraction.get("source_document"), "source_document")
    metadata = _mapping(extraction.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 추출 결과가 아님")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 갱신 전 추출 결과만 검토할 수 있음")
    candidates = extraction.get("candidates")
    if not isinstance(candidates, list):
        raise ProfileDocumentError("candidates 배열이 필요함")
    normalized_id = _text(candidate_id, "candidate_id")
    matches = []
    for position, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{position}]")
        if candidate.get("candidate_id") == normalized_id:
            matches.append(candidate)
    if not matches:
        raise ProfileDocumentError(f"후보를 찾을 수 없음: {normalized_id}")
    if len(matches) > 1:
        raise ProfileDocumentError(f"중복 후보 ID를 검토할 수 없음: {normalized_id}")
    candidate = matches[0]
    if candidate.get("status") != "needs_review":
        raise ProfileDocumentError("needs_review 상태인 후보만 검토할 수 있음")
    return root, source, candidate


def build_profile_candidate_review(
    extraction: Mapping[str, Any],
    *,
    candidate_id: str,
    decision: str,
    reviewed_at: datetime,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one immutable user decision without copying candidate text."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise ProfileDocumentError("reviewed_at은 시간대가 포함되어야 함")
    if decision not in CANDIDATE_REVIEW_DECISIONS:
        allowed = ", ".join(sorted(CANDIDATE_REVIEW_DECISIONS))
        raise ProfileDocumentError(f"decision 허용값: {allowed}")
    normalized_notes = None
    if notes is not None:
        if not isinstance(notes, str):
            raise ProfileDocumentError("notes는 문자열이어야 함")
        normalized_notes = notes.strip() or None
        if normalized_notes is not None and len(normalized_notes) > 1000:
            raise ProfileDocumentError("notes는 1000자 이하여야 함")

    root, source, candidate = _candidate(extraction, candidate_id)
    extraction_id = _text(
        root.get("extraction_id"), "profile_extraction.extraction_id"
    )
    normalized_candidate_id = _text(
        candidate.get("candidate_id"), "candidate.candidate_id"
    )
    evidence = _mapping(candidate.get("source_evidence"), "candidate.source_evidence")
    reviewed_timestamp = reviewed_at.isoformat(timespec="microseconds")
    review_key = f"{extraction_id}|{normalized_candidate_id}|{reviewed_timestamp}"
    review_id = "profile-candidate-review-" + sha256(
        review_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "candidate_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_timestamp,
            "decision": decision,
            "notes": normalized_notes,
        },
        "source": {
            "extraction_id": extraction_id,
            "candidate_id": normalized_candidate_id,
            "profile_section": _text(
                candidate.get("profile_section"), "candidate.profile_section"
            ),
            "document_id": _text(source.get("document_id"), "source_document.document_id"),
            "line_start": evidence.get("line_start"),
            "line_end": evidence.get("line_end"),
        },
        "metadata": {
            "schema_version": PROFILE_CANDIDATE_REVIEW_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_candidate_review(
    review: Mapping[str, Any],
    directory: str | Path,
) -> Path:
    """Atomically save one immutable candidate review."""

    root = _mapping(review.get("candidate_review"), "candidate_review")
    metadata = _mapping(review.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_CANDIDATE_REVIEW_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 후보 검토 기록이 아님")
    if metadata.get("contains_candidate_text") is not False:
        raise ProfileDocumentError("후보 검토 기록에 후보 문장 제외 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("후보 검토 기록에 Git 제외 표시가 없음")
    review_id = _text(root.get("review_id"), "candidate_review.review_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{review_id}.json"
    if target_path.exists():
        raise ProfileDocumentError(f"후보 검토 파일이 이미 존재함: {target_path}")

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
            f"후보 검토 기록을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path
