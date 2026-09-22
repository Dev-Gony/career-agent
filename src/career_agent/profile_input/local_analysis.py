"""Build a conservative local profile analysis response without external transfer."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .analysis_draft import PROFILE_ANALYSIS_CONTRACT_VERSION
from .document_store import ProfileDocumentError


LOCAL_EVIDENCE_PROFILE_ANALYSIS_MODEL = "grounded-rules-v1"
_MAX_ITEMS = 50
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
_OUTCOME_PATTERN = re.compile(
    r"(?:단축|절감|향상|개선|증가|감소|달성|제거|축소|최적화|해결)"
)
_UNCERTAIN_PATTERN = re.compile(
    r"(?:없음|없습니다|미경험|사용하지|담당하지|학습|공부|입문|"
    r"관심|예정|희망)"
)
_TECHNOLOGY_ALIASES = (
    "GitHub Actions",
    "Gemini API",
    "REST API",
    "LLM API",
    "JavaScript",
    "TypeScript",
    "Salesforce",
    "Confluence",
    "Selenium",
    "Postman",
    "Tableau",
    "Python",
    "Docker",
    "Slack",
    "AWS",
    "Java",
    "Jira",
    "SQL",
    "Git",
    "Gemini",
)
_CAREER_SECTIONS = frozenset({"career_history", "projects"})


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    normalized = value.strip()
    if len(normalized) > 1000:
        raise ProfileDocumentError(f"{name}은 1000자 이하여야 함")
    return normalized


def _append(items: list[dict[str, Any]], item: dict[str, Any], name: str) -> None:
    if len(items) >= _MAX_ITEMS:
        raise ProfileDocumentError(f"{name}은 {_MAX_ITEMS}개 이하여야 함")
    items.append(item)


def _technology_matches(text: str) -> list[str]:
    matches: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []
    for alias in _TECHNOLOGY_ALIASES:
        pattern = re.compile(
            rf"(?<![0-9A-Za-z]){re.escape(alias)}(?![0-9A-Za-z])",
            re.IGNORECASE,
        )
        for match in pattern.finditer(text):
            span = match.span()
            if any(span[0] < end and start < span[1] for start, end in occupied):
                continue
            occupied.append(span)
            matches.append((span[0], match.group(0)))
    return [value for _, value in sorted(matches, key=lambda item: item[0])]


class LocalEvidenceProfileAnalysisProvider:
    """Convert explicit local expressions into review-only evidence candidates."""

    provider_name = "local-evidence-rules"
    model_name = LOCAL_EVIDENCE_PROFILE_ANALYSIS_MODEL
    sends_data_externally = False

    def analyze(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if not isinstance(response_schema, Mapping):
            raise ProfileDocumentError("로컬 분석 응답 스키마 객체가 필요함")
        if set(request) != {"contract_version", "candidates"}:
            raise ProfileDocumentError("로컬 분석 요청 필드 구성이 올바르지 않음")
        if request.get("contract_version") != PROFILE_ANALYSIS_CONTRACT_VERSION:
            raise ProfileDocumentError("로컬 분석 요청 계약 버전이 올바르지 않음")
        candidates = request.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ProfileDocumentError("로컬 분석 후보가 1개 이상 필요함")

        response: dict[str, list[dict[str, Any]]] = {
            "career_evidence": [],
            "achievement_evidence": [],
            "technology_evidence": [],
            "unknowns": [],
        }
        candidate_ids: set[str] = set()
        for position, raw_candidate in enumerate(candidates):
            candidate = _mapping(raw_candidate, f"candidates[{position}]")
            if set(candidate) != {"candidate_id", "profile_section", "text"}:
                raise ProfileDocumentError(
                    f"candidates[{position}] 필드 구성이 올바르지 않음"
                )
            candidate_id = _text(
                candidate.get("candidate_id"), f"candidates[{position}].candidate_id"
            )
            if candidate_id in candidate_ids:
                raise ProfileDocumentError(f"중복 candidate_id: {candidate_id}")
            candidate_ids.add(candidate_id)
            section = _text(
                candidate.get("profile_section"),
                f"candidates[{position}].profile_section",
            )
            text = _text(candidate.get("text"), f"candidates[{position}].text")
            duration_match = _DURATION_PATTERN.search(text)
            quantified_match = _QUANTIFIED_PATTERN.search(text)
            action_match = _ACTION_PATTERN.search(text)
            outcome_match = _OUTCOME_PATTERN.search(text)
            uncertain = _UNCERTAIN_PATTERN.search(text) is not None
            technologies = _technology_matches(text)
            created_evidence = False

            if (
                section in _CAREER_SECTIONS
                and duration_match is not None
                and action_match is not None
                and not uncertain
            ):
                _append(
                    response["career_evidence"],
                    {
                        "role_or_context": None,
                        "period_expression": duration_match.group(0),
                        "responsibility_evidence": text,
                        "candidate_ids": [candidate_id],
                        "confidence": "medium",
                    },
                    "career_evidence",
                )
                created_evidence = True

            if (
                quantified_match is not None
                and outcome_match is not None
                and not uncertain
            ):
                _append(
                    response["achievement_evidence"],
                    {
                        "problem_evidence": None,
                        "action_evidence": None,
                        "result_evidence": text,
                        "candidate_ids": [candidate_id],
                        "confidence": "medium",
                    },
                    "achievement_evidence",
                )
                created_evidence = True

            if technologies and action_match is not None and not uncertain:
                for technology_name in technologies:
                    _append(
                        response["technology_evidence"],
                        {
                            "technology_name": technology_name,
                            "usage_evidence": text,
                            "proficiency_status": "unconfirmed",
                            "candidate_ids": [candidate_id],
                            "confidence": "medium",
                        },
                        "technology_evidence",
                    )
                created_evidence = True

            unknown: dict[str, Any] | None = None
            if technologies:
                names = ", ".join(technologies)
                unknown = {
                    "question": f"{names}의 실제 사용 범위와 숙련도를 확인해주세요.",
                    "reason": "기술명과 문장만으로 실제 사용 수준을 확정할 수 없습니다.",
                    "candidate_ids": [candidate_id],
                    "confidence": "low",
                }
            elif quantified_match is not None and outcome_match is None:
                unknown = {
                    "question": "이 수치가 업무 규모인지 실제 성과인지 확인해주세요.",
                    "reason": "수치 표현만으로 성과를 확정할 수 없습니다.",
                    "candidate_ids": [candidate_id],
                    "confidence": "low",
                }
            elif section in _CAREER_SECTIONS and not created_evidence:
                unknown = {
                    "question": "이 경력 또는 프로젝트의 역할, 기간과 책임을 확인해주세요.",
                    "reason": "후보 문장만으로 경력 근거를 안전하게 확정할 수 없습니다.",
                    "candidate_ids": [candidate_id],
                    "confidence": "low",
                }
            if unknown is not None:
                _append(response["unknowns"], unknown, "unknowns")

        return response
