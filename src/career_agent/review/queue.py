"""Build a metadata-only queue for reviewing actual Greenhouse candidates."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping

from career_agent.discovery.ranking import non_opening_title_signal
from career_agent.matching import MATCHING_RULES_VERSION
from career_agent.workflows import ANALYSIS_PIPELINE_VERSION, profile_content_sha256


REVIEW_QUEUE_SCHEMA_VERSION = "0.3"
HUMAN_REVIEW_SCHEMA_VERSION = "0.1"
FIT_ASSESSMENTS = frozenset({"fit", "hold", "not_fit"})
_PRIORITY_ORDER = {"high": 0, "medium": 1, "review": 2}
_ASSESSMENT_ORDER = {"match": 0, "unknown": 1, "mismatch": 2}
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[가-힣]+")
_TOKEN_STOPWORDS = {"and", "or", "the", "of"}


class GreenhouseReviewQueueError(ValueError):
    """Raised when a review queue cannot be built or saved safely."""


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GreenhouseReviewQueueError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseReviewQueueError(f"{name} 문자열이 필요함")
    return value.strip()


def _current_records(discovery: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    board_results = discovery.get("board_results")
    if not isinstance(board_results, list) or not board_results:
        raise GreenhouseReviewQueueError("discovery.board_results 배열이 필요함")
    records: list[Mapping[str, Any]] = []
    for board_position, board_result in enumerate(board_results):
        board = _mapping(board_result, f"board_results[{board_position}]")
        current = board.get("current_records")
        if not isinstance(current, list):
            raise GreenhouseReviewQueueError(
                f"board_results[{board_position}].current_records 배열이 필요함"
            )
        for record_position, record in enumerate(current):
            records.append(
                _mapping(
                    record,
                    f"board_results[{board_position}].current_records[{record_position}]",
                )
            )
    return records


def _candidate_key(record: Mapping[str, Any]) -> tuple[str, str]:
    identity = _mapping(record.get("identity"), "record.identity")
    source = _mapping(record.get("source"), "record.source")
    if identity.get("provider") != "greenhouse":
        raise GreenhouseReviewQueueError("Greenhouse 후보만 검토 큐에 넣을 수 있음")
    return (
        _text(source.get("board_token"), "record.source.board_token"),
        _text(identity.get("external_id"), "record.identity.external_id"),
    )


def _source_timestamp(record: Mapping[str, Any]) -> float:
    source = _mapping(record.get("source"), "record.source")
    for field in ("updated_at", "published_at"):
        value = source.get(field)
        if not isinstance(value, str) or not value.strip():
            continue
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is not None and parsed.utcoffset() is not None:
            return parsed.timestamp()
    return float("-inf")


def _priority(record: Mapping[str, Any]) -> str | None:
    summary = _mapping(record.get("summary"), "record.summary")
    title = summary.get("title")
    if isinstance(title, str) and non_opening_title_signal(title) is not None:
        return None
    relevance = _mapping(record.get("profile_relevance"), "profile_relevance")
    value = relevance.get("priority")
    return value if isinstance(value, str) and value in _PRIORITY_ORDER else None


def _assessment_rank(record: Mapping[str, Any], field: str) -> int:
    relevance = _mapping(record.get("profile_relevance"), "profile_relevance")
    value = relevance.get(field)
    return _ASSESSMENT_ORDER.get(value, _ASSESSMENT_ORDER["unknown"])


def _explicit_mismatch_rank(record: Mapping[str, Any]) -> int:
    return int(
        _assessment_rank(record, "location_assessment")
        == _ASSESSMENT_ORDER["mismatch"]
        or _assessment_rank(record, "employment_assessment")
        == _ASSESSMENT_ORDER["mismatch"]
    )


def _target_token_weights(search_plan: Mapping[str, Any]) -> dict[str, int]:
    plan = search_plan.get("job_search_plan", search_plan)
    plan = _mapping(plan, "job_search_plan")
    role_axes = plan.get("role_axes")
    if not isinstance(role_axes, list) or not role_axes:
        raise GreenhouseReviewQueueError("job_search_plan.role_axes 배열이 필요함")
    weights: dict[str, int] = {}
    for position, raw_axis in enumerate(role_axes):
        axis = _mapping(raw_axis, f"role_axes[{position}]")
        priority = axis.get("priority")
        weight = max(1, 6 - priority) if isinstance(priority, int) else 1
        discovery_terms = axis.get("discovery_terms")
        if not isinstance(discovery_terms, list):
            raise GreenhouseReviewQueueError(
                f"role_axes[{position}].discovery_terms 배열이 필요함"
            )
        phrases = [axis.get("canonical_role"), *discovery_terms]
        for phrase in phrases:
            if not isinstance(phrase, str):
                continue
            for token in _TOKEN_PATTERN.findall(phrase.casefold()):
                if len(token) < 2 or token in _TOKEN_STOPWORDS:
                    continue
                weights[token] = max(weights.get(token, 0), weight)
    return weights


def _broad_role_signals(
    record: Mapping[str, Any], token_weights: Mapping[str, int]
) -> list[str]:
    summary = _mapping(record.get("summary"), "record.summary")
    title = _text(summary.get("title"), "record.summary.title")
    title_tokens = set(_TOKEN_PATTERN.findall(title.casefold()))
    return sorted(
        (token for token in title_tokens if token in token_weights),
        key=lambda token: (-token_weights[token], token),
    )


def _broad_role_score(
    record: Mapping[str, Any], token_weights: Mapping[str, int]
) -> int:
    return sum(
        token_weights[token]
        for token in _broad_role_signals(record, token_weights)
    )


def _sorted_unique_candidates(
    records: list[Mapping[str, Any]],
    token_weights: Mapping[str, int],
) -> list[Mapping[str, Any]]:
    unique: dict[tuple[str, str], Mapping[str, Any]] = {}
    for record in records:
        priority = _priority(record)
        if priority is None:
            continue
        key = _candidate_key(record)
        existing = unique.get(key)
        if existing is None or _source_timestamp(record) > _source_timestamp(existing):
            unique[key] = record
    return sorted(
        unique.values(),
        key=lambda record: (
            _explicit_mismatch_rank(record),
            _PRIORITY_ORDER[_priority(record) or "review"],
            _assessment_rank(record, "location_assessment"),
            _assessment_rank(record, "employment_assessment"),
            -_broad_role_score(record, token_weights),
            -_source_timestamp(record),
            _candidate_key(record),
        ),
    )


def _current_analysis(
    previous_runs: Iterable[Mapping[str, Any]],
    *,
    record: Mapping[str, Any],
    profile_hash: str,
) -> tuple[str | None, str]:
    board_token, external_id = _candidate_key(record)
    source = _mapping(record.get("source"), "record.source")
    updated_at = source.get("updated_at")
    for run in previous_runs:
        if not isinstance(run, Mapping):
            continue
        selection = run.get("selection")
        analysis = run.get("analysis")
        if not isinstance(selection, Mapping) or not isinstance(analysis, Mapping):
            continue
        if (
            selection.get("board_token") != board_token
            or str(selection.get("external_job_id", "")) != external_id
        ):
            continue
        posting = analysis.get("job_posting")
        result = analysis.get("match_result")
        if not isinstance(posting, Mapping) or not isinstance(result, Mapping):
            continue
        posting_source = posting.get("source")
        inputs = result.get("inputs")
        metadata = result.get("metadata")
        identity = result.get("identity")
        if not all(
            isinstance(item, Mapping)
            for item in (posting_source, inputs, metadata, identity)
        ):
            continue
        if (
            posting_source.get("updated_at") == updated_at
            and inputs.get("profile_content_sha256") == profile_hash
            and metadata.get("matching_rules_version") == MATCHING_RULES_VERSION
            and metadata.get("analysis_pipeline_version")
            == ANALYSIS_PIPELINE_VERSION
        ):
            analysis_id = identity.get("analysis_id")
            if isinstance(analysis_id, str) and analysis_id.strip():
                review_status = metadata.get("human_review_status")
                return analysis_id.strip(), (
                    review_status
                    if isinstance(review_status, str) and review_status.strip()
                    else "not_reviewed"
                )
    return None, "not_reviewed"


def _review_timestamp(value: Any, name: str) -> tuple[float, str]:
    text = _text(value, name)
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as error:
        raise GreenhouseReviewQueueError(f"{name} 날짜 형식이 올바르지 않음") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise GreenhouseReviewQueueError(f"{name}은 시간대가 포함되어야 함")
    return parsed.timestamp(), text


def _human_review_index(
    human_reviews: Iterable[Mapping[str, Any]],
) -> dict[tuple[str, str], dict[str, Any]]:
    latest: dict[tuple[str, str], tuple[tuple[float, str], dict[str, Any]]] = {}
    for position, raw_review in enumerate(human_reviews):
        review = _mapping(raw_review, f"human_reviews[{position}]")
        root = _mapping(
            review.get("human_review"), f"human_reviews[{position}].human_review"
        )
        candidate = _mapping(
            review.get("candidate"), f"human_reviews[{position}].candidate"
        )
        source = _mapping(review.get("source"), f"human_reviews[{position}].source")
        metadata = _mapping(
            review.get("metadata"), f"human_reviews[{position}].metadata"
        )
        if metadata.get("schema_version") != HUMAN_REVIEW_SCHEMA_VERSION:
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}]의 스키마 버전이 올바르지 않음"
            )
        if metadata.get("contains_profile_content") is not False:
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}]에 프로필 내용 제외 표시가 없음"
            )
        if metadata.get("contains_job_description_content") is not False:
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}]에 공고 본문 제외 표시가 없음"
            )

        review_id = _text(
            root.get("review_id"),
            f"human_reviews[{position}].human_review.review_id",
        )
        reviewed_order = _review_timestamp(
            root.get("reviewed_at"),
            f"human_reviews[{position}].human_review.reviewed_at",
        )
        if root.get("status") != "reviewed":
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}].human_review.status는 reviewed여야 함"
            )
        fit_assessment = root.get("fit_assessment")
        if fit_assessment not in FIT_ASSESSMENTS:
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}].human_review.fit_assessment가 올바르지 않음"
            )
        recommendation_useful = root.get("recommendation_useful")
        if recommendation_useful is not None and not isinstance(
            recommendation_useful, bool
        ):
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}].human_review.recommendation_useful이 올바르지 않음"
            )
        notes = root.get("notes")
        if notes is not None and (
            not isinstance(notes, str) or not notes.strip() or len(notes) > 1000
        ):
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}].human_review.notes가 올바르지 않음"
            )

        board_token = _text(
            candidate.get("board_token"),
            f"human_reviews[{position}].candidate.board_token",
        )
        external_job_id = _text(
            candidate.get("external_job_id"),
            f"human_reviews[{position}].candidate.external_job_id",
        )
        candidate_key = _text(
            candidate.get("candidate_key"),
            f"human_reviews[{position}].candidate.candidate_key",
        )
        expected_key = f"greenhouse:{board_token}:{external_job_id}"
        if candidate_key != expected_key:
            raise GreenhouseReviewQueueError(
                f"human_reviews[{position}]의 공고 식별자가 서로 일치하지 않음"
            )
        analysis_id = _text(
            source.get("analysis_id"),
            f"human_reviews[{position}].source.analysis_id",
        )
        key = (candidate_key, analysis_id)
        review_value = {
            "status": "reviewed",
            "fit_assessment": fit_assessment,
            "recommendation_useful": recommendation_useful,
            "notes": notes,
            "review_id": review_id,
            "reviewed_at": reviewed_order[1],
        }
        existing = latest.get(key)
        ordering = (reviewed_order[0], review_id)
        if existing is None or ordering > existing[0]:
            latest[key] = (ordering, review_value)
    return {key: value for key, (_, value) in latest.items()}


def _queue_item(
    record: Mapping[str, Any],
    *,
    position: int,
    analysis_id: str | None,
    review_status: str,
    human_review: Mapping[str, Any] | None,
    token_weights: Mapping[str, int],
) -> dict[str, Any]:
    board_token, external_id = _candidate_key(record)
    source = _mapping(record.get("source"), "record.source")
    summary = _mapping(record.get("summary"), "record.summary")
    relevance = _mapping(record.get("profile_relevance"), "profile_relevance")
    return {
        "position": position,
        "candidate_key": f"greenhouse:{board_token}:{external_id}",
        "board_token": board_token,
        "external_job_id": external_id,
        "company": _text(summary.get("company"), "record.summary.company"),
        "title": _text(summary.get("title"), "record.summary.title"),
        "location": summary.get("location_text"),
        "priority": _text(relevance.get("priority"), "profile_relevance.priority"),
        "ranking_reason": _text(relevance.get("reason"), "profile_relevance.reason"),
        "location_assessment": relevance.get("location_assessment", "unknown"),
        "employment_assessment": relevance.get("employment_assessment", "unknown"),
        "broad_role_signals": _broad_role_signals(record, token_weights),
        "source_url": _text(source.get("source_url"), "record.source.source_url"),
        "source_updated_at": source.get("updated_at"),
        "analysis_status": "analyzed_current" if analysis_id else "needs_analysis",
        "analysis_id": analysis_id,
        "human_review": dict(human_review)
        if human_review is not None
        else {
            "status": review_status,
            "fit_assessment": None,
            "recommendation_useful": None,
            "notes": None,
            "review_id": None,
            "reviewed_at": None,
        },
    }


def build_greenhouse_review_queue(
    discovery: Mapping[str, Any],
    previous_runs: Iterable[Mapping[str, Any]],
    profile_document: dict[str, Any],
    search_plan: Mapping[str, Any],
    *,
    created_at: datetime,
    source_run_filename: str,
    limit: int = 10,
    human_reviews: Iterable[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    """Build a ranked snapshot without fetching any additional job content."""

    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise GreenhouseReviewQueueError("created_at은 시간대가 포함되어야 함")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
        raise GreenhouseReviewQueueError("limit은 1 이상 50 이하 정수여야 함")
    if not isinstance(profile_document, dict):
        raise GreenhouseReviewQueueError("프로필은 JSON 객체여야 함")
    if Path(source_run_filename).name != source_run_filename:
        raise GreenhouseReviewQueueError("source_run_filename은 파일명이어야 함")
    _text(source_run_filename, "source_run_filename")

    token_weights = _target_token_weights(search_plan)
    candidates = _sorted_unique_candidates(_current_records(discovery), token_weights)
    selected = candidates[:limit]
    profile_hash = profile_content_sha256(profile_document)
    runs = list(previous_runs)
    review_index = _human_review_index(human_reviews)
    items: list[dict[str, Any]] = []
    for position, record in enumerate(selected, start=1):
        analysis_id, review_status = _current_analysis(
            runs,
            record=record,
            profile_hash=profile_hash,
        )
        board_token, external_id = _candidate_key(record)
        candidate_key = f"greenhouse:{board_token}:{external_id}"
        current_human_review = (
            review_index.get((candidate_key, analysis_id)) if analysis_id else None
        )
        items.append(
            _queue_item(
                record,
                position=position,
                analysis_id=analysis_id,
                review_status=review_status,
                human_review=current_human_review,
                token_weights=token_weights,
            )
        )

    priorities = Counter(item["priority"] for item in items)
    statuses = Counter(item["analysis_status"] for item in items)
    review_statuses = Counter(item["human_review"]["status"] for item in items)
    queue_id = "greenhouse-review-queue-" + created_at.strftime(
        "%Y%m%dT%H%M%S%f%z"
    )
    return {
        "review_queue": {
            "queue_id": queue_id,
            "created_at": created_at.isoformat(timespec="microseconds"),
            "source_discovery_executed_at": discovery.get("executed_at"),
            "source_run_filename": source_run_filename,
            "limit": limit,
        },
        "summary": {
            "eligible_current_candidates": len(candidates),
            "selected_candidates": len(items),
            "priorities": dict(priorities),
            "analysis_statuses": dict(statuses),
            "human_review_statuses": dict(review_statuses),
        },
        "items": items,
        "metadata": {
            "schema_version": REVIEW_QUEUE_SCHEMA_VERSION,
            "matching_rules_version": MATCHING_RULES_VERSION,
            "analysis_pipeline_version": ANALYSIS_PIPELINE_VERSION,
            "profile_content_sha256": profile_hash,
            "contains_profile_content": False,
            "contains_job_description_content": False,
        },
    }


def save_greenhouse_review_queue(
    queue: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save one immutable review queue snapshot."""

    root = _mapping(queue.get("review_queue"), "review_queue")
    queue_id = _text(root.get("queue_id"), "review_queue.queue_id")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{queue_id}.json"
    if target_path.exists():
        raise GreenhouseReviewQueueError(f"검토 큐 파일이 이미 존재함: {target_path}")

    serialized = json.dumps(queue, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{queue_id}.",
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
            f"검토 큐를 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path
