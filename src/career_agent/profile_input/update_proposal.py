"""Build a non-mutating profile update proposal from approved candidates."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterable, Mapping

from .candidate_review import (
    CANDIDATE_REVIEW_DECISIONS,
    PROFILE_CANDIDATE_REVIEW_SCHEMA_VERSION,
)
from .document_store import ProfileDocumentError
from .text_extraction import PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION


PROFILE_UPDATE_PROPOSAL_SCHEMA_VERSION = "0.1"
_PROPOSAL_ID_PATTERN = re.compile(r"^profile-update-proposal-[0-9a-f]{24}$")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _timestamp(value: Any, name: str) -> tuple[float, str]:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise ProfileDocumentError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ProfileDocumentError(f"{name}은 시간대가 포함되어야 함")
    return parsed.timestamp(), text


def profile_content_sha256(profile_document: Mapping[str, Any]) -> str:
    """Return a stable content fingerprint for one profile document."""

    try:
        serialized = json.dumps(
            profile_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as error:
        raise ProfileDocumentError("프로필을 비교용 지문으로 변환할 수 없음") from error
    return sha256(serialized.encode("utf-8")).hexdigest()


def _candidate_index(
    extraction: Mapping[str, Any],
) -> tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Mapping[str, Any]]]:
    root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    source = _mapping(extraction.get("source_document"), "source_document")
    metadata = _mapping(extraction.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 추출 결과가 아님")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 갱신 전 추출 결과만 사용할 수 있음")
    document_id = _text(source.get("document_id"), "source_document.document_id")
    candidates = extraction.get("candidates")
    if not isinstance(candidates, list):
        raise ProfileDocumentError("candidates 배열이 필요함")
    index: dict[str, Mapping[str, Any]] = {}
    for position, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{position}]")
        candidate_id = _text(
            candidate.get("candidate_id"), f"candidates[{position}].candidate_id"
        )
        if candidate_id in index:
            raise ProfileDocumentError(f"중복 candidate_id: {candidate_id}")
        if candidate.get("status") != "needs_review":
            raise ProfileDocumentError(
                f"candidates[{position}].status는 needs_review여야 함"
            )
        evidence = _mapping(
            candidate.get("source_evidence"),
            f"candidates[{position}].source_evidence",
        )
        if evidence.get("document_id") != document_id:
            raise ProfileDocumentError(
                f"candidates[{position}]의 문서 근거가 source_document와 다름"
            )
        index[candidate_id] = candidate
    return root, source, index


def _latest_reviews(
    reviews: Iterable[Mapping[str, Any]],
    *,
    extraction_id: str,
    document_id: str,
    candidates: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, tuple[tuple[float, str], dict[str, Any]]] = {}
    for position, raw_review in enumerate(reviews):
        review = _mapping(raw_review, f"reviews[{position}]")
        root = _mapping(review.get("candidate_review"), f"reviews[{position}].candidate_review")
        source = _mapping(review.get("source"), f"reviews[{position}].source")
        metadata = _mapping(review.get("metadata"), f"reviews[{position}].metadata")
        if metadata.get("schema_version") != PROFILE_CANDIDATE_REVIEW_SCHEMA_VERSION:
            raise ProfileDocumentError(
                f"reviews[{position}]의 스키마 버전이 올바르지 않음"
            )
        if metadata.get("contains_candidate_text") is not False:
            raise ProfileDocumentError(
                f"reviews[{position}]에 후보 문장 제외 표시가 없음"
            )
        if metadata.get("git_tracking_allowed") is not False:
            raise ProfileDocumentError(
                f"reviews[{position}]에 Git 제외 표시가 없음"
            )
        reviewed_order = _timestamp(
            root.get("reviewed_at"),
            f"reviews[{position}].candidate_review.reviewed_at",
        )
        review_id = _text(
            root.get("review_id"), f"reviews[{position}].candidate_review.review_id"
        )
        decision = root.get("decision")
        if decision not in CANDIDATE_REVIEW_DECISIONS:
            raise ProfileDocumentError(
                f"reviews[{position}].candidate_review.decision이 올바르지 않음"
            )
        review_extraction_id = _text(
            source.get("extraction_id"), f"reviews[{position}].source.extraction_id"
        )
        candidate_id = _text(
            source.get("candidate_id"), f"reviews[{position}].source.candidate_id"
        )
        expected_review_id = "profile-candidate-review-" + sha256(
            f"{review_extraction_id}|{candidate_id}|{reviewed_order[1]}".encode("utf-8")
        ).hexdigest()[:24]
        if review_id != expected_review_id:
            raise ProfileDocumentError(
                f"reviews[{position}]의 검토 ID가 원본 참조와 일치하지 않음"
            )
        if review_extraction_id != extraction_id:
            continue
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ProfileDocumentError(
                f"reviews[{position}]가 존재하지 않는 후보를 참조함: {candidate_id}"
            )
        evidence = _mapping(
            candidate.get("source_evidence"), f"candidate[{candidate_id}].source_evidence"
        )
        if (
            source.get("profile_section") != candidate.get("profile_section")
            or source.get("document_id") != document_id
            or source.get("line_start") != evidence.get("line_start")
            or source.get("line_end") != evidence.get("line_end")
        ):
            raise ProfileDocumentError(
                f"reviews[{position}]의 후보 근거가 추출 결과와 일치하지 않음"
            )
        value = {
            "review_id": review_id,
            "reviewed_at": reviewed_order[1],
            "decision": decision,
        }
        ordering = (reviewed_order[0], review_id)
        existing = latest.get(candidate_id)
        if existing is None or ordering > existing[0]:
            latest[candidate_id] = (ordering, value)
    return {candidate_id: value for candidate_id, (_, value) in latest.items()}


def build_profile_update_proposal(
    profile_document: Mapping[str, Any],
    extraction: Mapping[str, Any],
    reviews: Iterable[Mapping[str, Any]],
    *,
    created_at: datetime,
) -> dict[str, Any]:
    """Create a reviewable proposal containing only finally approved candidates."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ProfileDocumentError("created_at은 시간대가 포함되어야 함")
    profile = _mapping(profile_document.get("profile"), "profile")
    basic = _mapping(profile.get("basic"), "profile.basic")
    profile_id = _text(basic.get("profile_id"), "profile.basic.profile_id")
    extraction_root, source_document, candidates = _candidate_index(extraction)
    extraction_id = _text(
        extraction_root.get("extraction_id"), "profile_extraction.extraction_id"
    )
    document_id = _text(
        source_document.get("document_id"), "source_document.document_id"
    )
    latest = _latest_reviews(
        reviews,
        extraction_id=extraction_id,
        document_id=document_id,
        candidates=candidates,
    )
    approved_ids = [
        candidate_id
        for candidate_id in candidates
        if latest.get(candidate_id, {}).get("decision") == "approve"
    ]
    rejected_count = sum(
        review["decision"] == "reject" for review in latest.values()
    )
    profile_hash = profile_content_sha256(profile_document)
    proposal_key = "|".join(
        [profile_hash, extraction_id]
        + [
            f"{latest[candidate_id]['review_id']}:{latest[candidate_id]['decision']}"
            for candidate_id in sorted(latest)
        ]
    )
    proposal_id = "profile-update-proposal-" + sha256(
        proposal_key.encode("utf-8")
    ).hexdigest()[:24]
    additions = []
    for position, candidate_id in enumerate(approved_ids, start=1):
        candidate = candidates[candidate_id]
        evidence = _mapping(
            candidate.get("source_evidence"), f"candidate[{candidate_id}].source_evidence"
        )
        review = latest[candidate_id]
        additions.append(
            {
                "proposal_item_id": f"proposal-item-{position:03d}",
                "profile_section": _text(
                    candidate.get("profile_section"),
                    f"candidate[{candidate_id}].profile_section",
                ),
                "candidate_text": _text(
                    candidate.get("text"), f"candidate[{candidate_id}].text"
                ),
                "mapping_status": "needs_mapping",
                "source_evidence": {
                    "extraction_id": extraction_id,
                    "candidate_id": candidate_id,
                    "document_id": document_id,
                    "line_start": evidence.get("line_start"),
                    "line_end": evidence.get("line_end"),
                },
                "approval": review,
            }
        )
    return {
        "profile_update_proposal": {
            "proposal_id": proposal_id,
            "created_at": created_at.isoformat(timespec="microseconds"),
            "status": "needs_mapping" if additions else "no_approved_candidates",
            "base_profile_id": profile_id,
            "base_profile_content_sha256": profile_hash,
            "source_extraction_id": extraction_id,
        },
        "summary": {
            "candidate_count": len(candidates),
            "reviewed_count": len(latest),
            "approved_count": len(additions),
            "rejected_count": rejected_count,
            "unreviewed_count": len(candidates) - len(latest),
        },
        "proposed_additions": additions,
        "analysis_notes": {
            "facts": [
                "후보별 가장 최근 사용자 결정만 사용함",
                "최종 결정이 approve인 후보만 갱신안에 포함함",
            ],
            "unknowns": [
                "승인 문장을 USER_PROFILE_SCHEMA 세부 객체로 변환하지 않음"
            ],
        },
        "metadata": {
            "schema_version": PROFILE_UPDATE_PROPOSAL_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": bool(additions),
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_update_proposal(
    proposal: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse an identical profile update proposal."""

    root = _mapping(proposal.get("profile_update_proposal"), "profile_update_proposal")
    metadata = _mapping(proposal.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_UPDATE_PROPOSAL_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 갱신안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 갱신안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("갱신안은 프로필 갱신 상태일 수 없음")
    proposal_id = _text(root.get("proposal_id"), "profile_update_proposal.proposal_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{proposal_id}.json"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError(
                f"기존 프로필 갱신안을 읽을 수 없음: {target_path}"
            ) from error
        for field in (
            "summary",
            "proposed_additions",
            "analysis_notes",
            "metadata",
        ):
            if existing.get(field) != proposal.get(field):
                raise ProfileDocumentError(
                    f"같은 갱신안 ID의 기존 내용이 일치하지 않음: {field}"
                )
        existing_root = _mapping(
            existing.get("profile_update_proposal"), "profile_update_proposal"
        )
        for field in (
            "proposal_id",
            "status",
            "base_profile_id",
            "base_profile_content_sha256",
            "source_extraction_id",
        ):
            if existing_root.get(field) != root.get(field):
                raise ProfileDocumentError(
                    f"같은 갱신안 ID의 기존 메타데이터가 일치하지 않음: {field}"
                )
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
        raise ProfileDocumentError(
            f"프로필 갱신안을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def load_profile_update_proposal(
    proposal_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load one private update proposal without allowing path traversal."""

    normalized_id = _text(proposal_id, "proposal_id")
    if _PROPOSAL_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("proposal_id 형식이 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    try:
        proposal = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(
            f"프로필 갱신안을 읽을 수 없음: {path}"
        ) from error
    if not isinstance(proposal, dict):
        raise ProfileDocumentError("프로필 갱신안 최상위 JSON은 객체여야 함")
    root = _mapping(proposal.get("profile_update_proposal"), "profile_update_proposal")
    metadata = _mapping(proposal.get("metadata"), "metadata")
    if root.get("proposal_id") != normalized_id:
        raise ProfileDocumentError("갱신안의 proposal_id가 요청과 일치하지 않음")
    if metadata.get("schema_version") != PROFILE_UPDATE_PROPOSAL_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 갱신안이 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 갱신안에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("갱신안은 프로필 갱신 상태일 수 없음")
    return proposal
