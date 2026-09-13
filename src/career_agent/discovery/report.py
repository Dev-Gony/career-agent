"""Human-readable local reports for discovered job candidates."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from html import unescape
import re
from typing import Any


PRIORITY_ORDER = {"high": 0, "medium": 1, "review": 2, "low": 3}


def format_discovery_records(
    records: Iterable[Mapping[str, Any]],
    *,
    limit: int = 20,
    priority: str | None = None,
) -> str:
    """Format discovery records without treating priority as final job fit."""

    if limit <= 0:
        raise ValueError("limit은 0보다 커야 함")
    if priority is not None and priority not in PRIORITY_ORDER:
        raise ValueError("지원하지 않는 발견 우선순위")

    candidates = list(records)
    if priority is not None:
        candidates = [
            record
            for record in candidates
            if record.get("profile_relevance", {}).get("priority") == priority
        ]
    candidates.sort(
        key=lambda record: record.get("source", {}).get("published_at") or "",
        reverse=True,
    )
    candidates.sort(key=_priority_sort_key)
    selected = candidates[:limit]

    lines = [
        f"저장된 발견 후보: {len(candidates)}건, 표시: {len(selected)}건",
        "주의: 발견 우선순위이며 최종 적합도나 지원 추천이 아닙니다.",
    ]
    if not selected:
        lines.append("표시할 후보가 없습니다.")
        return "\n".join(lines)

    for index, record in enumerate(selected, start=1):
        summary = record.get("summary", {})
        source = record.get("source", {})
        relevance = record.get("profile_relevance", {})
        lines.extend(
            [
                "",
                f"{index}. [{str(relevance.get('priority', 'review')).upper()}] "
                f"{_display(summary.get('title'), '제목 확인 필요')}",
                f"   회사: {_display(summary.get('company'))}",
                f"   지역: {_display_location(summary.get('location_text'))}",
                f"   게시 시점: {source.get('published_at') or '확인 필요'}",
                f"   발견 이유: {relevance.get('reason') or '확인 필요'}",
                f"   원문: {source.get('source_url') or '확인 필요'}",
            ]
        )
    return "\n".join(lines)


def _priority_sort_key(record: Mapping[str, Any]) -> int:
    relevance = record.get("profile_relevance", {})
    priority = relevance.get("priority", "review")
    return PRIORITY_ORDER.get(priority, PRIORITY_ORDER["review"])


def _display(value: object, fallback: str = "확인 필요") -> str:
    return unescape(str(value)) if value else fallback


def _display_location(value: object) -> str:
    if not value:
        return "확인 필요"
    normalized = re.sub(r"\s*>\s*", " > ", str(value).lstrip("|").strip())
    return unescape(normalized)
