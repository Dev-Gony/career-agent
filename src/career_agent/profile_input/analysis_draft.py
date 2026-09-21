"""Validate grounded LLM profile analysis drafts before user review."""

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

from .document_store import ProfileDocumentError
from .text_extraction import PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION


PROFILE_ANALYSIS_DRAFT_SCHEMA_VERSION = "0.1"
PROFILE_ANALYSIS_CONTRACT_VERSION = "0.1"
PROFILE_ANALYSIS_CONFIDENCE_LEVELS = frozenset({"high", "medium", "low"})
PROFILE_ANALYSIS_DATA_BOUNDARIES = frozenset({"local", "external"})

_MAX_ITEMS_PER_CATEGORY = 50
_MAX_CANDIDATE_REFERENCES = 10
_MAX_EVIDENCE_TEXT_CHARS = 1000
_MAX_UNKNOWN_TEXT_CHARS = 500
_MAX_STORED_DRAFT_FILES = 1000
_DRAFT_ID_PATTERN = re.compile(r"^profile-analysis-draft-[0-9a-f]{24}$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")


def _evidence_field_schema() -> dict[str, Any]:
    return {
        "anyOf": [
            {"type": "string", "minLength": 1, "maxLength": 1000},
            {"type": "null"},
        ]
    }


def _candidate_ids_schema() -> dict[str, Any]:
    return {
        "type": "array",
        "items": {"type": "string", "pattern": r"^candidate-[0-9]{3,}$"},
        "minItems": 1,
        "maxItems": _MAX_CANDIDATE_REFERENCES,
        "uniqueItems": True,
    }


def _confidence_schema() -> dict[str, Any]:
    return {
        "type": "string",
        "enum": sorted(PROFILE_ANALYSIS_CONFIDENCE_LEVELS),
    }


_CAREER_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "role_or_context": _evidence_field_schema(),
        "period_expression": _evidence_field_schema(),
        "responsibility_evidence": _evidence_field_schema(),
        "candidate_ids": _candidate_ids_schema(),
        "confidence": _confidence_schema(),
    },
    "required": [
        "role_or_context",
        "period_expression",
        "responsibility_evidence",
        "candidate_ids",
        "confidence",
    ],
    "additionalProperties": False,
}

_ACHIEVEMENT_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "problem_evidence": _evidence_field_schema(),
        "action_evidence": _evidence_field_schema(),
        "result_evidence": _evidence_field_schema(),
        "candidate_ids": _candidate_ids_schema(),
        "confidence": _confidence_schema(),
    },
    "required": [
        "problem_evidence",
        "action_evidence",
        "result_evidence",
        "candidate_ids",
        "confidence",
    ],
    "additionalProperties": False,
}

_TECHNOLOGY_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "technology_name": {
            "type": "string",
            "minLength": 1,
            "maxLength": 200,
        },
        "usage_evidence": {
            "type": "string",
            "minLength": 1,
            "maxLength": 1000,
        },
        "proficiency_status": {"type": "string", "enum": ["unconfirmed"]},
        "candidate_ids": _candidate_ids_schema(),
        "confidence": _confidence_schema(),
    },
    "required": [
        "technology_name",
        "usage_evidence",
        "proficiency_status",
        "candidate_ids",
        "confidence",
    ],
    "additionalProperties": False,
}

_UNKNOWN_ITEM_SCHEMA = {
    "type": "object",
    "properties": {
        "question": {"type": "string", "minLength": 1, "maxLength": 500},
        "reason": {"type": "string", "minLength": 1, "maxLength": 500},
        "candidate_ids": _candidate_ids_schema(),
        "confidence": _confidence_schema(),
    },
    "required": ["question", "reason", "candidate_ids", "confidence"],
    "additionalProperties": False,
}

_PROFILE_ANALYSIS_RESPONSE_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "career_evidence": {
            "type": "array",
            "items": _CAREER_ITEM_SCHEMA,
            "maxItems": _MAX_ITEMS_PER_CATEGORY,
        },
        "achievement_evidence": {
            "type": "array",
            "items": _ACHIEVEMENT_ITEM_SCHEMA,
            "maxItems": _MAX_ITEMS_PER_CATEGORY,
        },
        "technology_evidence": {
            "type": "array",
            "items": _TECHNOLOGY_ITEM_SCHEMA,
            "maxItems": _MAX_ITEMS_PER_CATEGORY,
        },
        "unknowns": {
            "type": "array",
            "items": _UNKNOWN_ITEM_SCHEMA,
            "maxItems": _MAX_ITEMS_PER_CATEGORY,
        },
    },
    "required": [
        "career_evidence",
        "achievement_evidence",
        "technology_evidence",
        "unknowns",
    ],
    "additionalProperties": False,
}


def profile_analysis_response_json_schema() -> dict[str, Any]:
    """Return a copy of the strict provider response JSON Schema."""

    return deepcopy(_PROFILE_ANALYSIS_RESPONSE_JSON_SCHEMA)


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], name: str) -> None:
    actual = set(value)
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        raise ProfileDocumentError(f"{name} 필수 필드 누락: {', '.join(missing)}")
    if extra:
        raise ProfileDocumentError(f"{name} 허용되지 않은 필드: {', '.join(extra)}")


def _text(value: Any, name: str, *, max_chars: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    normalized = value.strip()
    if len(normalized) > max_chars:
        raise ProfileDocumentError(f"{name}은 {max_chars}자 이하여야 함")
    return normalized


def _candidate_index(extraction: Mapping[str, Any]) -> tuple[str, dict[str, str]]:
    root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    metadata = _mapping(extraction.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 추출 결과가 아님")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 적용 전 추출 결과만 분석할 수 있음")
    extraction_id = _text(
        root.get("extraction_id"),
        "profile_extraction.extraction_id",
        max_chars=200,
    )
    candidates = extraction.get("candidates")
    if not isinstance(candidates, list):
        raise ProfileDocumentError("candidates 배열이 필요함")
    index: dict[str, str] = {}
    for position, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{position}]")
        candidate_id = _text(
            candidate.get("candidate_id"),
            f"candidates[{position}].candidate_id",
            max_chars=100,
        )
        if candidate_id in index:
            raise ProfileDocumentError(f"중복 candidate_id: {candidate_id}")
        if candidate.get("status") != "needs_review":
            raise ProfileDocumentError("needs_review 후보만 분석할 수 있음")
        index[candidate_id] = _text(
            candidate.get("text"),
            f"candidates[{position}].text",
            max_chars=_MAX_EVIDENCE_TEXT_CHARS,
        )
    return extraction_id, index


def build_profile_analysis_request(
    extraction: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the minimal candidate payload accepted by an analysis provider."""

    _, candidate_index = _candidate_index(extraction)
    candidates = extraction.get("candidates")
    if not isinstance(candidates, list):
        raise ProfileDocumentError("candidates 배열이 필요함")
    request_candidates: list[dict[str, str]] = []
    for position, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{position}]")
        candidate_id = _text(
            candidate.get("candidate_id"),
            f"candidates[{position}].candidate_id",
            max_chars=100,
        )
        request_candidates.append(
            {
                "candidate_id": candidate_id,
                "profile_section": _text(
                    candidate.get("profile_section"),
                    f"candidates[{position}].profile_section",
                    max_chars=100,
                ),
                "text": candidate_index[candidate_id],
            }
        )
    return {
        "contract_version": PROFILE_ANALYSIS_CONTRACT_VERSION,
        "candidates": request_candidates,
    }


def _candidate_ids(
    value: Any,
    name: str,
    candidate_index: Mapping[str, str],
) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ProfileDocumentError(f"{name}에는 후보 ID가 1개 이상 필요함")
    if len(value) > _MAX_CANDIDATE_REFERENCES:
        raise ProfileDocumentError(
            f"{name}은 {_MAX_CANDIDATE_REFERENCES}개 이하여야 함"
        )
    normalized: list[str] = []
    for position, raw_candidate_id in enumerate(value):
        candidate_id = _text(
            raw_candidate_id,
            f"{name}[{position}]",
            max_chars=100,
        )
        if candidate_id not in candidate_index:
            raise ProfileDocumentError(f"존재하지 않는 후보 참조: {candidate_id}")
        if candidate_id in normalized:
            raise ProfileDocumentError(f"중복 후보 참조: {candidate_id}")
        normalized.append(candidate_id)
    return normalized


def _confidence(value: Any, name: str) -> str:
    normalized = _text(value, name, max_chars=20)
    if normalized not in PROFILE_ANALYSIS_CONFIDENCE_LEVELS:
        allowed = ", ".join(sorted(PROFILE_ANALYSIS_CONFIDENCE_LEVELS))
        raise ProfileDocumentError(f"{name} 허용값: {allowed}")
    return normalized


def _grounded_text(
    value: Any,
    name: str,
    candidate_ids: list[str],
    candidate_index: Mapping[str, str],
    *,
    nullable: bool,
    max_chars: int = _MAX_EVIDENCE_TEXT_CHARS,
) -> str | None:
    if value is None and nullable:
        return None
    normalized = _text(value, name, max_chars=max_chars)
    if not any(normalized in candidate_index[candidate_id] for candidate_id in candidate_ids):
        raise ProfileDocumentError(f"{name}은 참조 후보의 원문 구간이어야 함")
    return normalized


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ProfileDocumentError(f"{name} 배열이 필요함")
    if len(value) > _MAX_ITEMS_PER_CATEGORY:
        raise ProfileDocumentError(
            f"{name}은 {_MAX_ITEMS_PER_CATEGORY}개 이하여야 함"
        )
    return value


def validate_profile_analysis_response(
    extraction: Mapping[str, Any],
    response: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate and normalize one provider response against source candidates."""

    _, candidate_index = _candidate_index(extraction)
    raw_response = _mapping(response, "response")
    root_fields = {
        "career_evidence",
        "achievement_evidence",
        "technology_evidence",
        "unknowns",
    }
    _exact_keys(raw_response, root_fields, "response")
    normalized: dict[str, list[dict[str, Any]]] = {
        field: [] for field in root_fields
    }

    career_fields = {
        "role_or_context",
        "period_expression",
        "responsibility_evidence",
        "candidate_ids",
        "confidence",
    }
    for position, raw_item in enumerate(
        _array(raw_response["career_evidence"], "career_evidence")
    ):
        name = f"career_evidence[{position}]"
        item = _mapping(raw_item, name)
        _exact_keys(item, career_fields, name)
        candidate_ids = _candidate_ids(
            item["candidate_ids"], f"{name}.candidate_ids", candidate_index
        )
        values = {
            field: _grounded_text(
                item[field],
                f"{name}.{field}",
                candidate_ids,
                candidate_index,
                nullable=True,
            )
            for field in (
                "role_or_context",
                "period_expression",
                "responsibility_evidence",
            )
        }
        if all(value is None for value in values.values()):
            raise ProfileDocumentError(f"{name}에는 근거 구간이 1개 이상 필요함")
        normalized["career_evidence"].append(
            {
                **values,
                "candidate_ids": candidate_ids,
                "confidence": _confidence(item["confidence"], f"{name}.confidence"),
            }
        )

    achievement_fields = {
        "problem_evidence",
        "action_evidence",
        "result_evidence",
        "candidate_ids",
        "confidence",
    }
    for position, raw_item in enumerate(
        _array(raw_response["achievement_evidence"], "achievement_evidence")
    ):
        name = f"achievement_evidence[{position}]"
        item = _mapping(raw_item, name)
        _exact_keys(item, achievement_fields, name)
        candidate_ids = _candidate_ids(
            item["candidate_ids"], f"{name}.candidate_ids", candidate_index
        )
        values = {
            field: _grounded_text(
                item[field],
                f"{name}.{field}",
                candidate_ids,
                candidate_index,
                nullable=True,
            )
            for field in (
                "problem_evidence",
                "action_evidence",
                "result_evidence",
            )
        }
        if all(value is None for value in values.values()):
            raise ProfileDocumentError(f"{name}에는 근거 구간이 1개 이상 필요함")
        normalized["achievement_evidence"].append(
            {
                **values,
                "candidate_ids": candidate_ids,
                "confidence": _confidence(item["confidence"], f"{name}.confidence"),
            }
        )

    technology_fields = {
        "technology_name",
        "usage_evidence",
        "proficiency_status",
        "candidate_ids",
        "confidence",
    }
    for position, raw_item in enumerate(
        _array(raw_response["technology_evidence"], "technology_evidence")
    ):
        name = f"technology_evidence[{position}]"
        item = _mapping(raw_item, name)
        _exact_keys(item, technology_fields, name)
        candidate_ids = _candidate_ids(
            item["candidate_ids"], f"{name}.candidate_ids", candidate_index
        )
        if item["proficiency_status"] != "unconfirmed":
            raise ProfileDocumentError(
                f"{name}.proficiency_status는 unconfirmed여야 함"
            )
        normalized["technology_evidence"].append(
            {
                "technology_name": _grounded_text(
                    item["technology_name"],
                    f"{name}.technology_name",
                    candidate_ids,
                    candidate_index,
                    nullable=False,
                    max_chars=200,
                ),
                "usage_evidence": _grounded_text(
                    item["usage_evidence"],
                    f"{name}.usage_evidence",
                    candidate_ids,
                    candidate_index,
                    nullable=False,
                ),
                "proficiency_status": "unconfirmed",
                "candidate_ids": candidate_ids,
                "confidence": _confidence(item["confidence"], f"{name}.confidence"),
            }
        )

    unknown_fields = {"question", "reason", "candidate_ids", "confidence"}
    for position, raw_item in enumerate(_array(raw_response["unknowns"], "unknowns")):
        name = f"unknowns[{position}]"
        item = _mapping(raw_item, name)
        _exact_keys(item, unknown_fields, name)
        normalized["unknowns"].append(
            {
                "question": _text(
                    item["question"],
                    f"{name}.question",
                    max_chars=_MAX_UNKNOWN_TEXT_CHARS,
                ),
                "reason": _text(
                    item["reason"],
                    f"{name}.reason",
                    max_chars=_MAX_UNKNOWN_TEXT_CHARS,
                ),
                "candidate_ids": _candidate_ids(
                    item["candidate_ids"], f"{name}.candidate_ids", candidate_index
                ),
                "confidence": _confidence(item["confidence"], f"{name}.confidence"),
            }
        )
    return normalized


def _profile_analysis_draft_id(
    extraction_id: str,
    analysis: Mapping[str, Any],
    *,
    provider_name: str,
    model_name: str,
    data_boundary: str,
) -> str:
    canonical_analysis = json.dumps(
        analysis,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    draft_key = "|".join(
        [
            extraction_id,
            PROFILE_ANALYSIS_CONTRACT_VERSION,
            provider_name,
            model_name,
            data_boundary,
            canonical_analysis,
        ]
    )
    return "profile-analysis-draft-" + sha256(
        draft_key.encode("utf-8")
    ).hexdigest()[:24]


def _stored_draft(
    draft: Mapping[str, Any],
    *,
    expected_draft_id: str | None = None,
) -> tuple[Mapping[str, Any], datetime]:
    _exact_keys(
        draft,
        {
            "profile_analysis_draft",
            "analysis",
            "analysis_source",
            "summary",
            "metadata",
        },
        "profile_analysis_draft_document",
    )
    root = _mapping(draft.get("profile_analysis_draft"), "profile_analysis_draft")
    _exact_keys(
        root,
        {
            "draft_id",
            "analyzed_at",
            "source_extraction_id",
            "contract_version",
            "status",
        },
        "profile_analysis_draft",
    )
    draft_id = _text(root.get("draft_id"), "profile_analysis_draft.draft_id", max_chars=200)
    if _DRAFT_ID_PATTERN.fullmatch(draft_id) is None:
        raise ProfileDocumentError("프로필 분석 초안 ID 형식이 올바르지 않음")
    if expected_draft_id is not None and draft_id != expected_draft_id:
        raise ProfileDocumentError("프로필 분석 초안 ID가 요청과 일치하지 않음")
    extraction_id = _text(
        root.get("source_extraction_id"),
        "profile_analysis_draft.source_extraction_id",
        max_chars=200,
    )
    if _EXTRACTION_ID_PATTERN.fullmatch(extraction_id) is None:
        raise ProfileDocumentError("프로필 추출 ID 형식이 올바르지 않음")
    if root.get("contract_version") != PROFILE_ANALYSIS_CONTRACT_VERSION:
        raise ProfileDocumentError("현재 계약 버전의 프로필 분석 초안이 아님")
    if root.get("status") != "needs_review":
        raise ProfileDocumentError("검토 대기 상태인 프로필 분석 초안이 아님")
    analyzed_at_text = _text(
        root.get("analyzed_at"),
        "profile_analysis_draft.analyzed_at",
        max_chars=100,
    )
    try:
        analyzed_at = datetime.fromisoformat(analyzed_at_text)
    except ValueError as error:
        raise ProfileDocumentError("프로필 분석 초안 시간이 올바르지 않음") from error
    if analyzed_at.tzinfo is None or analyzed_at.utcoffset() is None:
        raise ProfileDocumentError("프로필 분석 초안 시간에 시간대가 필요함")

    source = _mapping(draft.get("analysis_source"), "analysis_source")
    _exact_keys(source, {"provider", "model", "data_boundary"}, "analysis_source")
    provider_name = _text(source.get("provider"), "analysis_source.provider", max_chars=100)
    model_name = _text(source.get("model"), "analysis_source.model", max_chars=200)
    data_boundary = source.get("data_boundary")
    if data_boundary not in PROFILE_ANALYSIS_DATA_BOUNDARIES:
        raise ProfileDocumentError("프로필 분석 초안 데이터 경계가 올바르지 않음")

    analysis = _mapping(draft.get("analysis"), "analysis")
    analysis_fields = {
        "career_evidence",
        "achievement_evidence",
        "technology_evidence",
        "unknowns",
    }
    _exact_keys(analysis, analysis_fields, "analysis")
    summary = _mapping(draft.get("summary"), "summary")
    summary_fields = {
        "career_evidence_count": "career_evidence",
        "achievement_evidence_count": "achievement_evidence",
        "technology_evidence_count": "technology_evidence",
        "unknown_count": "unknowns",
    }
    _exact_keys(summary, set(summary_fields), "summary")
    for summary_field, analysis_field in summary_fields.items():
        items = analysis.get(analysis_field)
        count = summary.get(summary_field)
        if not isinstance(items, list) or len(items) > _MAX_ITEMS_PER_CATEGORY:
            raise ProfileDocumentError(f"analysis.{analysis_field} 배열이 올바르지 않음")
        if isinstance(count, bool) or not isinstance(count, int) or count != len(items):
            raise ProfileDocumentError(f"summary.{summary_field} 합계가 일치하지 않음")

    metadata = _mapping(draft.get("metadata"), "metadata")
    _exact_keys(
        metadata,
        {
            "schema_version",
            "contains_personal_data",
            "contains_candidate_text",
            "git_tracking_allowed",
            "provider_output_validated",
            "profile_updated",
        },
        "metadata",
    )
    if metadata.get("schema_version") != PROFILE_ANALYSIS_DRAFT_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 분석 초안이 아님")
    if metadata.get("contains_personal_data") is not True:
        raise ProfileDocumentError("프로필 분석 초안의 개인정보 표시가 없음")
    if metadata.get("contains_candidate_text") is not True:
        raise ProfileDocumentError("프로필 분석 초안의 후보 문장 표시가 없음")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 분석 초안에 Git 제외 표시가 없음")
    if metadata.get("provider_output_validated") is not True:
        raise ProfileDocumentError("공급자 출력 검증이 완료되지 않음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 분석 초안은 프로필 갱신 상태일 수 없음")

    expected_identity = _profile_analysis_draft_id(
        extraction_id,
        analysis,
        provider_name=provider_name,
        model_name=model_name,
        data_boundary=data_boundary,
    )
    if draft_id != expected_identity:
        raise ProfileDocumentError("프로필 분석 초안 ID와 내용 지문이 일치하지 않음")
    return root, analyzed_at


def build_profile_analysis_draft(
    extraction: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    analyzed_at: datetime,
    provider_name: str,
    model_name: str,
    data_boundary: str,
) -> dict[str, Any]:
    """Build a private, review-only draft from a validated provider response."""

    if analyzed_at.tzinfo is None or analyzed_at.utcoffset() is None:
        raise ProfileDocumentError("analyzed_at은 시간대가 포함되어야 함")
    normalized_provider = _text(provider_name, "provider_name", max_chars=100)
    normalized_model = _text(model_name, "model_name", max_chars=200)
    if data_boundary not in PROFILE_ANALYSIS_DATA_BOUNDARIES:
        allowed = ", ".join(sorted(PROFILE_ANALYSIS_DATA_BOUNDARIES))
        raise ProfileDocumentError(f"data_boundary 허용값: {allowed}")
    extraction_id, _ = _candidate_index(extraction)
    analysis = validate_profile_analysis_response(extraction, response)
    draft_id = _profile_analysis_draft_id(
        extraction_id,
        analysis,
        provider_name=normalized_provider,
        model_name=normalized_model,
        data_boundary=data_boundary,
    )
    return {
        "profile_analysis_draft": {
            "draft_id": draft_id,
            "analyzed_at": analyzed_at.isoformat(timespec="microseconds"),
            "source_extraction_id": extraction_id,
            "contract_version": PROFILE_ANALYSIS_CONTRACT_VERSION,
            "status": "needs_review",
        },
        "analysis": analysis,
        "analysis_source": {
            "provider": normalized_provider,
            "model": normalized_model,
            "data_boundary": data_boundary,
        },
        "summary": {
            "career_evidence_count": len(analysis["career_evidence"]),
            "achievement_evidence_count": len(analysis["achievement_evidence"]),
            "technology_evidence_count": len(analysis["technology_evidence"]),
            "unknown_count": len(analysis["unknowns"]),
        },
        "metadata": {
            "schema_version": PROFILE_ANALYSIS_DRAFT_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": True,
            "git_tracking_allowed": False,
            "provider_output_validated": True,
            "profile_updated": False,
        },
    }


def save_profile_analysis_draft(
    draft: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse one immutable private analysis draft."""

    root, _ = _stored_draft(draft)
    draft_id = str(root["draft_id"])

    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{draft_id}.json"
    serialized = json.dumps(draft, ensure_ascii=False, indent=2) + "\n"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError("기존 프로필 분석 초안을 읽을 수 없음") from error
        existing_root = _mapping(
            existing.get("profile_analysis_draft"), "profile_analysis_draft"
        )
        _stored_draft(existing, expected_draft_id=draft_id)
        for field in (
            "draft_id",
            "source_extraction_id",
            "contract_version",
            "status",
        ):
            if existing_root.get(field) != root.get(field):
                raise ProfileDocumentError(
                    f"같은 프로필 분석 초안 ID의 메타데이터가 일치하지 않음: {field}"
                )
        for field in ("analysis", "analysis_source", "summary", "metadata"):
            if existing.get(field) != draft.get(field):
                raise ProfileDocumentError(
                    f"같은 프로필 분석 초안 ID의 내용이 일치하지 않음: {field}"
                )
        return target_path, False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{draft_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("프로필 분석 초안을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def load_profile_analysis_draft(
    draft_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load and verify one immutable private profile analysis draft."""

    normalized_id = _text(draft_id, "draft_id", max_chars=200)
    if _DRAFT_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("프로필 분석 초안 ID 형식이 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("프로필 분석 초안 심볼릭 링크는 읽을 수 없음")
    try:
        draft = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"프로필 분석 초안을 읽을 수 없음: {path}") from error
    if not isinstance(draft, dict):
        raise ProfileDocumentError("프로필 분석 초안 최상위 JSON은 객체여야 함")
    _stored_draft(draft, expected_draft_id=normalized_id)
    return draft


def select_latest_profile_analysis_draft(
    extraction_id: str,
    directory: str | Path,
) -> dict[str, Any] | None:
    """Select the newest verified review draft for one profile extraction."""

    normalized_extraction_id = _text(
        extraction_id,
        "extraction_id",
        max_chars=200,
    )
    if _EXTRACTION_ID_PATTERN.fullmatch(normalized_extraction_id) is None:
        raise ProfileDocumentError("프로필 추출 ID 형식이 올바르지 않음")
    target_directory = Path(directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("프로필 분석 초안 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("profile-analysis-draft-*.json"))
    if len(paths) > _MAX_STORED_DRAFT_FILES:
        raise ProfileDocumentError("프로필 분석 초안 파일이 허용 개수를 초과함")

    matches: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        draft = load_profile_analysis_draft(path.stem, target_directory)
        root, analyzed_at = _stored_draft(draft, expected_draft_id=path.stem)
        if root.get("source_extraction_id") == normalized_extraction_id:
            matches.append((analyzed_at, path.stem, draft))
    if not matches:
        return None
    return max(matches, key=lambda item: (item[0], item[1]))[2]
