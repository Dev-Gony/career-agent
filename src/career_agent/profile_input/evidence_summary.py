"""Derive reviewable evidence signals without asserting profile facts."""

from __future__ import annotations

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
from .update_proposal import profile_content_sha256


PROFILE_EVIDENCE_SUMMARY_SCHEMA_VERSION = "0.1"
PROFILE_EVIDENCE_SUMMARY_RULES_VERSION = "0.1"

_DURATION_PATTERN = re.compile(
    r"(?:(?:19|20)\d{2}[./-]\d{1,2}|(?:19|20)\d{2}\s*년|"
    r"\d+\s*년(?:\s*\d+\s*개월)?|\d+\s*개월)"
)
_QUANTIFIED_PATTERN = re.compile(
    r"(?:\d+(?:\.\d+)?\s*%|\d+(?:\.\d+)?\s*(?:건|회|명|개|배|시간|분|초))"
)
_ACTION_PATTERN = re.compile(
    r"(?:자동화|개선|구축|개발|운영|검증|테스트|분석|설계|최적화|"
    r"관리|정리|작성|도입|제안|해결|절감)"
)
_TECHNOLOGY_ALIASES = {
    "AWS": ("aws",),
    "Confluence": ("confluence",),
    "Docker": ("docker",),
    "Gemini API": ("gemini api", "gemini"),
    "Git": ("git",),
    "GitHub Actions": ("github actions",),
    "Java": ("java",),
    "JavaScript": ("javascript",),
    "Jira": ("jira",),
    "LLM API": ("llm api",),
    "Postman": ("postman",),
    "Python": ("python",),
    "REST API": ("rest api",),
    "Salesforce": ("salesforce",),
    "Selenium": ("selenium",),
    "Slack": ("slack",),
    "SQL": ("sql",),
    "Tableau": ("tableau",),
    "TypeScript": ("typescript",),
}


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _contains_alias(text: str, alias: str) -> bool:
    return (
        re.search(
            rf"(?<![0-9A-Za-z]){re.escape(alias)}(?![0-9A-Za-z])",
            text.casefold(),
        )
        is not None
    )


def _technology_mentions(text: str) -> list[str]:
    return [
        canonical
        for canonical, aliases in _TECHNOLOGY_ALIASES.items()
        if any(_contains_alias(text, alias) for alias in aliases)
    ]


def build_profile_evidence_summary(
    extraction: Mapping[str, Any],
    profile_document: Mapping[str, Any],
    *,
    analyzed_at: datetime,
) -> dict[str, Any]:
    """Build non-final signals tied to source candidates without copying text."""

    if analyzed_at.tzinfo is None or analyzed_at.utcoffset() is None:
        raise ProfileDocumentError("analyzed_at은 시간대가 포함되어야 함")
    extraction_root = _mapping(
        extraction.get("profile_extraction"),
        "profile_extraction",
    )
    source = _mapping(extraction.get("source_document"), "source_document")
    metadata = _mapping(extraction.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 추출 결과가 아님")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 적용 전 추출 결과만 분석할 수 있음")
    extraction_id = _text(
        extraction_root.get("extraction_id"),
        "profile_extraction.extraction_id",
    )
    document_id = _text(source.get("document_id"), "source_document.document_id")
    candidates = extraction.get("candidates")
    if not isinstance(candidates, list):
        raise ProfileDocumentError("candidates 배열이 필요함")
    _mapping(profile_document.get("profile"), "profile")
    profile_hash = profile_content_sha256(profile_document)

    signals: list[dict[str, Any]] = []
    duration_count = 0
    quantified_count = 0
    action_count = 0
    mentioned_technologies: set[str] = set()
    candidate_ids: set[str] = set()
    for position, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{position}]")
        candidate_id = _text(
            candidate.get("candidate_id"),
            f"candidates[{position}].candidate_id",
        )
        if candidate_id in candidate_ids:
            raise ProfileDocumentError(f"중복 candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        if candidate.get("status") != "needs_review":
            raise ProfileDocumentError("needs_review 후보만 근거 신호를 만들 수 있음")
        candidate_text = _text(
            candidate.get("text"),
            f"candidates[{position}].text",
        )
        evidence = _mapping(
            candidate.get("source_evidence"),
            f"candidates[{position}].source_evidence",
        )
        if evidence.get("document_id") != document_id:
            raise ProfileDocumentError("후보 문서 근거가 원본 문서와 일치하지 않음")

        signal_types: list[str] = []
        if _DURATION_PATTERN.search(candidate_text):
            signal_types.append("duration_expression")
            duration_count += 1
        if _QUANTIFIED_PATTERN.search(candidate_text):
            signal_types.append("quantified_expression")
            quantified_count += 1
        if _ACTION_PATTERN.search(candidate_text):
            signal_types.append("action_expression")
            action_count += 1
        technologies = _technology_mentions(candidate_text)
        if technologies:
            signal_types.append("technology_mention")
            mentioned_technologies.update(technologies)
        signals.append(
            {
                "candidate_id": candidate_id,
                "profile_section": _text(
                    candidate.get("profile_section"),
                    f"candidates[{position}].profile_section",
                ),
                "signal_types": signal_types,
                "technology_mentions": technologies,
                "source_evidence": {
                    "document_id": document_id,
                    "line_start": evidence.get("line_start"),
                    "line_end": evidence.get("line_end"),
                },
            }
        )

    summary_key = "|".join(
        [extraction_id, profile_hash, PROFILE_EVIDENCE_SUMMARY_RULES_VERSION]
    )
    summary_id = "profile-evidence-summary-" + sha256(
        summary_key.encode("utf-8")
    ).hexdigest()[:24]
    return {
        "profile_evidence_summary": {
            "summary_id": summary_id,
            "analyzed_at": analyzed_at.isoformat(timespec="microseconds"),
            "source_extraction_id": extraction_id,
            "base_profile_content_sha256": profile_hash,
            "rules_version": PROFILE_EVIDENCE_SUMMARY_RULES_VERSION,
            "status": "needs_review",
        },
        "summary": {
            "candidate_count": len(candidates),
            "duration_expression_count": duration_count,
            "quantified_expression_count": quantified_count,
            "action_expression_count": action_count,
            "technology_mention_candidate_count": sum(
                bool(item["technology_mentions"]) for item in signals
            ),
            "technology_names": sorted(mentioned_technologies),
        },
        "candidate_signals": signals,
        "analysis_notes": {
            "facts": [
                "기간, 수치, 실행 동사와 통제된 기술명 표현만 자동 탐지함",
                "후보 문장 원문을 이 요약에 복제하지 않음",
            ],
            "unknowns": [
                "탐지된 표현이 실제 경력 사실인지 사용자 확인 필요",
                "기술명 언급만으로 보유 여부와 숙련도를 판단하지 않음",
            ],
        },
        "metadata": {
            "schema_version": PROFILE_EVIDENCE_SUMMARY_SCHEMA_VERSION,
            "contains_personal_data": True,
            "contains_candidate_text": False,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_evidence_summary(
    summary: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse one evidence summary."""

    root = _mapping(
        summary.get("profile_evidence_summary"),
        "profile_evidence_summary",
    )
    metadata = _mapping(summary.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_EVIDENCE_SUMMARY_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 근거 요약이 아님")
    if metadata.get("contains_candidate_text") is not False:
        raise ProfileDocumentError("프로필 근거 요약에 후보 문장이 포함됨")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 근거 요약에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("프로필 근거 요약은 프로필 갱신 상태일 수 없음")
    summary_id = _text(root.get("summary_id"), "profile_evidence_summary.summary_id")
    if re.fullmatch(r"profile-evidence-summary-[0-9a-f]{24}", summary_id) is None:
        raise ProfileDocumentError("프로필 근거 요약 ID 형식이 올바르지 않음")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{summary_id}.json"
    serialized = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError("기존 프로필 근거 요약을 읽을 수 없음") from error
        if not isinstance(existing, Mapping):
            raise ProfileDocumentError("기존 프로필 근거 요약 형식이 올바르지 않음")
        existing_root = _mapping(
            existing.get("profile_evidence_summary"),
            "profile_evidence_summary",
        )
        for field in (
            "summary_id",
            "source_extraction_id",
            "base_profile_content_sha256",
            "rules_version",
            "status",
        ):
            if existing_root.get(field) != root.get(field):
                raise ProfileDocumentError(
                    f"같은 프로필 근거 요약 ID의 메타데이터가 일치하지 않음: {field}"
                )
        for field in (
            "summary",
            "candidate_signals",
            "analysis_notes",
            "metadata",
        ):
            if existing.get(field) != summary.get(field):
                raise ProfileDocumentError(
                    f"같은 프로필 근거 요약 ID의 내용이 일치하지 않음: {field}"
                )
        return target_path, False

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{summary_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError("프로필 근거 요약을 저장할 수 없음") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True
