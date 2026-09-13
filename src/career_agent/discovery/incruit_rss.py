"""Normalize one Incruit-style RSS item into a discovery record."""

from __future__ import annotations

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from hashlib import sha256
from html import unescape
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urlsplit, urlunsplit
import xml.etree.ElementTree as ElementTree


PROVIDER = "incruit"
MAX_XML_CHARACTERS = 1_000_000
DEFAULT_UNKNOWNS = ["고용 형태", "주요 업무", "필수 조건", "우대 조건"]
DESCRIPTION_LABELS = {
    "company": "회사명",
    "experience_text": "경력",
    "education_text": "학력",
    "location_text": "지역",
    "deadline_text": "마감일",
}


class IncruitRssParseError(ValueError):
    """Raised when an RSS item cannot be safely normalized."""


def build_incruit_discovery_record(
    xml_text: str,
    search_plan: Mapping[str, Any],
    *,
    feed_url: str,
    discovered_at: datetime,
    policy_checked_at: date,
    is_example: bool = False,
) -> dict[str, Any]:
    """Build one complete discovery record from a one-item RSS document."""

    items = _read_items(xml_text)
    if len(items) != 1:
        raise IncruitRssParseError("단일 변환은 item이 정확히 1개인 RSS만 처리함")
    return _build_record_from_item(
        items[0],
        search_plan,
        feed_url=feed_url,
        discovered_at=discovered_at,
        policy_checked_at=policy_checked_at,
        is_example=is_example,
    )


def build_incruit_discovery_records(
    xml_text: str,
    search_plan: Mapping[str, Any],
    *,
    feed_url: str,
    discovered_at: datetime,
    policy_checked_at: date,
    is_example: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    """Build records for every valid item and report item-level errors."""

    items = _read_items(xml_text)
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for item_number, item in enumerate(items, start=1):
        try:
            record = _build_record_from_item(
                item,
                search_plan,
                feed_url=feed_url,
                discovered_at=discovered_at,
                policy_checked_at=policy_checked_at,
                is_example=is_example,
            )
        except IncruitRssParseError as error:
            errors.append({"item_number": item_number, "error": str(error)})
            continue
        records.append(record)
    return {"records": records, "errors": errors}


def _build_record_from_item(
    item: ElementTree.Element,
    search_plan: Mapping[str, Any],
    *,
    feed_url: str,
    discovered_at: datetime,
    policy_checked_at: date,
    is_example: bool,
) -> dict[str, Any]:
    title = _required_child_text(item, "title")
    source_url = _required_child_text(item, "link")
    description = _optional_child_text(item, "description") or ""
    author = _optional_child_text(item, "author")
    published_text = _optional_child_text(item, "pubDate")

    _validate_http_url(source_url, "item/link")
    _validate_http_url(feed_url, "feed_url")
    _require_timezone(discovered_at)

    description_fields = _parse_description(description)
    company = author or description_fields["company"]
    warnings: list[str] = []
    unknowns = list(DEFAULT_UNKNOWNS)

    if company is None:
        warnings.append("회사명을 author와 description에서 확인할 수 없음")
        unknowns.append("회사명")

    normalized_title = _normalize_title(title, company)
    published_at = _parse_published_at(published_text, warnings)
    identity, deduplication = _build_identity(source_url)

    summary = {
        "title": normalized_title,
        "company": company,
        "experience_text": description_fields["experience_text"],
        "education_text": description_fields["education_text"],
        "location_text": description_fields["location_text"],
        "deadline_text": description_fields["deadline_text"],
    }
    for output_name, label in DESCRIPTION_LABELS.items():
        if output_name == "company":
            continue
        if summary[output_name] is None:
            unknowns.append(label)

    record: dict[str, Any] = {
        "identity": identity,
        "source": {
            "source_kind": "rss",
            "feed_url": feed_url,
            "source_url": source_url,
            "published_at": published_at,
            "discovered_at": discovered_at.isoformat(timespec="seconds"),
            "policy_checked_at": policy_checked_at.isoformat(),
        },
        "summary": summary,
        "availability": {
            "content_scope": "metadata_only",
            "detail_status": "unavailable",
            "match_ready": False,
            "reason": "RSS에 주요 업무와 자격 요건 전문이 없음",
        },
        "profile_relevance": _build_profile_relevance(summary, search_plan),
        "deduplication": deduplication,
        "parse_notes": {
            "warnings": warnings,
            "unknowns": _unique_preserving_order(unknowns),
        },
        "metadata": {
            "schema_version": "1.0",
            "is_example": is_example,
            "contains_real_posting_content": not is_example,
        },
    }
    return record


def _read_items(xml_text: str) -> list[ElementTree.Element]:
    if not isinstance(xml_text, str) or not xml_text.strip():
        raise IncruitRssParseError("RSS XML이 비어 있음")
    if len(xml_text) > MAX_XML_CHARACTERS:
        raise IncruitRssParseError("RSS XML이 허용 크기를 초과함")

    upper_text = xml_text.upper()
    if "<!DOCTYPE" in upper_text or "<!ENTITY" in upper_text:
        raise IncruitRssParseError("DOCTYPE 또는 ENTITY가 포함된 XML은 처리하지 않음")

    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as error:
        raise IncruitRssParseError(f"RSS XML 파싱 실패: {error}") from error

    if root.tag != "rss":
        raise IncruitRssParseError("최상위 rss 요소가 없음")

    items = root.findall("./channel/item")
    if not items:
        raise IncruitRssParseError("rss/channel/item이 없음")
    return items


def _required_child_text(item: ElementTree.Element, tag: str) -> str:
    value = _optional_child_text(item, tag)
    if value is None:
        raise IncruitRssParseError(f"필수 RSS 필드가 없음: item/{tag}")
    return value


def _optional_child_text(item: ElementTree.Element, tag: str) -> str | None:
    node = item.find(tag)
    if node is None or node.text is None:
        return None
    value = node.text.strip()
    return value or None


def _validate_http_url(value: str, field_name: str) -> None:
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise IncruitRssParseError(f"유효한 HTTP URL이 아님: {field_name}")


def _require_timezone(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise IncruitRssParseError("discovered_at은 시간대가 포함되어야 함")


def _parse_description(description: str) -> dict[str, str | None]:
    text = re.sub(r"(?i)<br\s*/?>", "\n", description)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unescape(text)

    fields: dict[str, str | None] = {}
    for output_name, label in DESCRIPTION_LABELS.items():
        match = re.search(
            rf"(?m)▨\s*{re.escape(label)}\s*:\s*([^\r\n]+)",
            text,
        )
        fields[output_name] = match.group(1).strip() if match else None
    fields["location_text"] = _normalize_location(fields["location_text"])
    return fields


def _normalize_location(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.lstrip("|").strip()
    normalized = re.sub(r"\s*>\s*", " > ", normalized)
    return normalized or None


def _normalize_title(title: str, company: str | None) -> str:
    title = unescape(title)
    if company:
        title = re.sub(
            rf"^\[\s*{re.escape(company)}\s*\]\s*",
            "",
            title,
            count=1,
        )
    normalized = title.strip()
    if not normalized:
        raise IncruitRssParseError("회사명 접두사 제거 후 공고 제목이 비어 있음")
    return normalized


def _parse_published_at(value: str | None, warnings: list[str]) -> str | None:
    if value is None:
        warnings.append("pubDate가 없어 게시 시점을 확인할 수 없음")
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        warnings.append("pubDate를 해석할 수 없어 게시 시점을 null로 유지함")
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        warnings.append("pubDate에 시간대가 없어 게시 시점을 null로 유지함")
        return None
    return parsed.isoformat(timespec="seconds")


def _build_identity(source_url: str) -> tuple[dict[str, str], dict[str, str]]:
    parts = urlsplit(source_url)
    external_id = parse_qs(parts.query).get("job", [None])[0]
    if external_id:
        return (
            {
                "discovery_id": f"{PROVIDER}-{external_id}",
                "provider": PROVIDER,
                "external_id": external_id,
            },
            {
                "key": f"{PROVIDER}:{external_id}",
                "strategy": "provider_external_id",
            },
        )

    canonical_url = urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, "")
    )
    url_hash = sha256(canonical_url.encode("utf-8")).hexdigest()
    short_hash = url_hash[:16]
    return (
        {
            "discovery_id": f"{PROVIDER}-url-{short_hash}",
            "provider": PROVIDER,
            "external_id": f"url-{short_hash}",
        },
        {
            "key": f"{PROVIDER}:url:{url_hash}",
            "strategy": "canonical_url_hash",
        },
    )


def _build_profile_relevance(
    summary: Mapping[str, str | None], search_plan: Mapping[str, Any]
) -> dict[str, Any]:
    plan = search_plan.get("job_search_plan", search_plan)
    title = (summary.get("title") or "").casefold()
    related_role_ids: list[str] = []
    matched_terms: list[str] = []
    matched_priorities: list[int | str] = []

    for axis in plan.get("role_axes", []):
        term = next(
            (
                candidate
                for candidate in axis.get("discovery_terms", [])
                if candidate.casefold() in title
            ),
            None,
        )
        if term is None:
            continue
        related_role_ids.append(axis["target_role_id"])
        matched_terms.append(term)
        matched_priorities.append(axis.get("priority", "conditional"))

    location_assessment = _assess_location(summary.get("location_text"), plan)
    employment_assessment = "unknown"
    priority = _discovery_priority(matched_priorities, location_assessment)
    confidence = "medium" if matched_terms else "low"

    positive_signals = [
        f"제목에 검색 확장어 '{term}'가 포함됨" for term in matched_terms
    ]
    if priority == "high" and location_assessment == "match":
        reason = "최우선 목표 직무 표현이 제목에 직접 나타나고 선호 지역과 일치함"
    elif matched_terms:
        reason = "목표 직무 표현이 제목에 있으나 상세 업무와 자격 요건 확인이 필요함"
    else:
        reason = "제목만으로 목표 직무 축과의 직접 관련성을 확인할 수 없음"

    return {
        "profile_id": plan["identity"]["profile_id"],
        "related_target_role_ids": related_role_ids,
        "positive_signals": positive_signals,
        "low_preference_signals": [],
        "location_assessment": location_assessment,
        "employment_assessment": employment_assessment,
        "priority": priority,
        "confidence": confidence,
        "reason": reason,
    }


def _assess_location(location_text: str | None, plan: Mapping[str, Any]) -> str:
    if not location_text:
        return "unknown"
    normalized_values = (
        plan.get("objective_preferences", {})
        .get("locations", {})
        .get("normalized_values", [])
    )
    return "match" if any(value in location_text for value in normalized_values) else "mismatch"


def _discovery_priority(
    matched_priorities: list[int | str], location_assessment: str
) -> str:
    numeric_priorities = [value for value in matched_priorities if isinstance(value, int)]
    if not matched_priorities:
        return "review"
    if numeric_priorities and min(numeric_priorities) == 1:
        priority = "high"
    elif numeric_priorities and min(numeric_priorities) <= 3:
        priority = "medium"
    else:
        priority = "review"

    if location_assessment == "mismatch":
        return {"high": "medium", "medium": "low", "review": "low"}[priority]
    return priority


def _unique_preserving_order(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))
