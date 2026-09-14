"""Build and persist explicit human feedback for one reviewed candidate."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from .queue import REVIEW_QUEUE_SCHEMA_VERSION, GreenhouseReviewQueueError


HUMAN_REVIEW_SCHEMA_VERSION = "0.1"
FIT_ASSESSMENTS = frozenset({"fit", "hold", "not_fit"})


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GreenhouseReviewQueueError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseReviewQueueError(f"{name} 문자열이 필요함")
    return value.strip()


def _review_candidate(queue: Mapping[str, Any], position: int) -> Mapping[str, Any]:
    metadata = _mapping(queue.get("metadata"), "metadata")
    if metadata.get("schema_version") != REVIEW_QUEUE_SCHEMA_VERSION:
        raise GreenhouseReviewQueueError(
            "현재 버전의 검토 큐가 아님. 검토 큐를 다시 생성해야 함"
        )
    if isinstance(position, bool) or not isinstance(position, int) or position < 1:
        raise GreenhouseReviewQueueError("position은 1 이상의 정수여야 함")
    items = queue.get("items")
    if not isinstance(items, list):
        raise GreenhouseReviewQueueError("items 배열이 필요함")
    for item_position, raw_item in enumerate(items):
        item = _mapping(raw_item, f"items[{item_position}]")
        if item.get("position") == position:
            if item.get("analysis_status") != "analyzed_current":
                raise GreenhouseReviewQueueError(
                    "상세 분석이 완료된 현재 공고만 사용자 검토를 기록할 수 있음"
                )
            _text(item.get("analysis_id"), "candidate.analysis_id")
            return item
    raise GreenhouseReviewQueueError(f"큐 위치 {position}의 공고를 찾을 수 없음")


def build_greenhouse_human_review(
    queue: Mapping[str, Any],
    *,
    position: int,
    fit_assessment: str,
    recommendation_useful: bool | None,
    reviewed_at: datetime,
    notes: str | None = None,
) -> dict[str, Any]:
    """Build one metadata-only human review without mutating its source queue."""

    if reviewed_at.tzinfo is None or reviewed_at.utcoffset() is None:
        raise GreenhouseReviewQueueError("reviewed_at은 시간대가 포함되어야 함")
    if fit_assessment not in FIT_ASSESSMENTS:
        allowed = ", ".join(sorted(FIT_ASSESSMENTS))
        raise GreenhouseReviewQueueError(f"fit_assessment 허용값: {allowed}")
    if recommendation_useful is not None and not isinstance(
        recommendation_useful, bool
    ):
        raise GreenhouseReviewQueueError(
            "recommendation_useful은 true, false 또는 null이어야 함"
        )
    normalized_notes = None
    if notes is not None:
        if not isinstance(notes, str):
            raise GreenhouseReviewQueueError("notes는 문자열이어야 함")
        normalized_notes = notes.strip() or None
        if normalized_notes is not None and len(normalized_notes) > 1000:
            raise GreenhouseReviewQueueError("notes는 1000자 이하여야 함")

    candidate = _review_candidate(queue, position)
    queue_root = _mapping(queue.get("review_queue"), "review_queue")
    reviewed_timestamp = reviewed_at.isoformat(timespec="microseconds")
    review_id = "greenhouse-human-review-" + reviewed_at.strftime(
        "%Y%m%dT%H%M%S%f%z"
    )
    return {
        "human_review": {
            "review_id": review_id,
            "reviewed_at": reviewed_timestamp,
            "status": "reviewed",
            "fit_assessment": fit_assessment,
            "recommendation_useful": recommendation_useful,
            "notes": normalized_notes,
        },
        "candidate": {
            "candidate_key": _text(
                candidate.get("candidate_key"), "candidate.candidate_key"
            ),
            "board_token": _text(
                candidate.get("board_token"), "candidate.board_token"
            ),
            "external_job_id": _text(
                candidate.get("external_job_id"), "candidate.external_job_id"
            ),
            "company": _text(candidate.get("company"), "candidate.company"),
            "title": _text(candidate.get("title"), "candidate.title"),
            "source_url": _text(
                candidate.get("source_url"), "candidate.source_url"
            ),
        },
        "source": {
            "queue_id": _text(queue_root.get("queue_id"), "review_queue.queue_id"),
            "analysis_id": _text(
                candidate.get("analysis_id"), "candidate.analysis_id"
            ),
            "position": position,
        },
        "metadata": {
            "schema_version": HUMAN_REVIEW_SCHEMA_VERSION,
            "contains_profile_content": False,
            "contains_job_description_content": False,
        },
    }


def save_greenhouse_human_review(
    review: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save one immutable human review record."""

    root = _mapping(review.get("human_review"), "human_review")
    review_id = _text(root.get("review_id"), "human_review.review_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{review_id}.json"
    if target_path.exists():
        raise GreenhouseReviewQueueError(
            f"사용자 검토 파일이 이미 존재함: {target_path}"
        )

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
        raise GreenhouseReviewQueueError(
            f"사용자 검토를 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path
