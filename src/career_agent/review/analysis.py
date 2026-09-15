"""Select and persist one detailed analysis from a Greenhouse review queue."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

from career_agent.matching import MATCHING_RULES_VERSION
from career_agent.workflows import ANALYSIS_PIPELINE_VERSION, profile_content_sha256

from .queue import REVIEW_QUEUE_SCHEMA_VERSION, GreenhouseReviewQueueError


class NoGreenhouseReviewCandidateError(GreenhouseReviewQueueError):
    """Raised when a valid queue has no unanalyzed candidate without a mismatch."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GreenhouseReviewQueueError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseReviewQueueError(f"{name} 문자열이 필요함")
    return value.strip()


def select_next_greenhouse_review_candidate(
    queue: Mapping[str, Any],
    profile_document: dict[str, Any],
) -> dict[str, Any]:
    """Return the first current, unanalyzed candidate without a known mismatch."""

    metadata = _mapping(queue.get("metadata"), "metadata")
    if metadata.get("schema_version") != REVIEW_QUEUE_SCHEMA_VERSION:
        raise GreenhouseReviewQueueError(
            "현재 버전의 검토 큐가 아님. 검토 큐를 다시 생성해야 함"
        )
    if metadata.get("matching_rules_version") != MATCHING_RULES_VERSION:
        raise GreenhouseReviewQueueError(
            "매칭 규칙이 바뀌었음. 검토 큐를 다시 생성해야 함"
        )
    if metadata.get("analysis_pipeline_version") != ANALYSIS_PIPELINE_VERSION:
        raise GreenhouseReviewQueueError(
            "분석 파이프라인이 바뀌었음. 검토 큐를 다시 생성해야 함"
        )
    if metadata.get("profile_content_sha256") != profile_content_sha256(
        profile_document
    ):
        raise GreenhouseReviewQueueError(
            "프로필 내용이 바뀌었음. 검토 큐를 다시 생성해야 함"
        )

    items = queue.get("items")
    if not isinstance(items, list):
        raise GreenhouseReviewQueueError("items 배열이 필요함")
    for position, item in enumerate(items):
        candidate = _mapping(item, f"items[{position}]")
        if candidate.get("analysis_status") != "needs_analysis":
            continue
        if "mismatch" in {
            candidate.get("location_assessment"),
            candidate.get("employment_assessment"),
        }:
            continue
        _text(candidate.get("board_token"), f"items[{position}].board_token")
        _text(
            candidate.get("external_job_id"),
            f"items[{position}].external_job_id",
        )
        return dict(candidate)
    raise NoGreenhouseReviewCandidateError(
        "현재 검토 큐에 분석 가능한 needs_analysis 후보가 없음"
    )


def build_greenhouse_review_analysis_run(
    queue: Mapping[str, Any],
    candidate: Mapping[str, Any],
    analysis: Mapping[str, Any],
    *,
    queue_filename: str,
) -> dict[str, Any]:
    """Package one review analysis in the existing local run shape."""

    if Path(queue_filename).name != queue_filename:
        raise GreenhouseReviewQueueError("queue_filename은 파일명이어야 함")
    queue_root = _mapping(queue.get("review_queue"), "review_queue")
    posting = _mapping(analysis.get("job_posting"), "analysis.job_posting")
    posting_source = _mapping(posting.get("source"), "analysis.job_posting.source")
    match_result = _mapping(analysis.get("match_result"), "analysis.match_result")
    match_identity = _mapping(
        match_result.get("identity"), "analysis.match_result.identity"
    )
    board_token = _text(candidate.get("board_token"), "candidate.board_token")
    external_job_id = _text(
        candidate.get("external_job_id"), "candidate.external_job_id"
    )
    if (
        posting_source.get("board_token") != board_token
        or str(posting_source.get("external_job_id", "")) != external_job_id
    ):
        raise GreenhouseReviewQueueError(
            "상세 분석 결과가 선택한 검토 후보와 일치하지 않음"
        )
    analysis_id = _text(match_identity.get("analysis_id"), "analysis_id")
    return {
        "status": "analyzed",
        "workflow": "greenhouse_review_queue",
        "source_review_queue": {
            "queue_id": _text(queue_root.get("queue_id"), "review_queue.queue_id"),
            "queue_filename": queue_filename,
            "position": candidate.get("position"),
        },
        "selection": {
            "board_token": board_token,
            "external_job_id": external_job_id,
            "title": candidate.get("title"),
            "company": candidate.get("company"),
            "source_url": candidate.get("source_url"),
            "source_updated_at": candidate.get("source_updated_at"),
            "priority": candidate.get("priority"),
            "reason": candidate.get("ranking_reason"),
            "policy": "first_unanalyzed_non_mismatch_in_review_queue",
        },
        "analysis": dict(analysis),
        "reuse": None,
        "metadata": {
            "analysis_id": analysis_id,
            "human_review_status": "not_reviewed",
        },
    }


def save_greenhouse_review_analysis_run(
    run: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save one review analysis without overwriting an older run."""

    metadata = _mapping(run.get("metadata"), "metadata")
    analysis_id = _text(metadata.get("analysis_id"), "metadata.analysis_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{analysis_id}.json"
    if target_path.exists():
        raise GreenhouseReviewQueueError(
            f"상세 분석 파일이 이미 존재함: {target_path}"
        )

    serialized = json.dumps(run, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{analysis_id}.",
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
            f"상세 분석을 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path
