"""Validate model-suggested role names as inert job-search terms."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from .generator import JobSearchPlanError


MAX_SEARCH_FOCUS_ROLES = 3
MAX_SEARCH_FOCUS_ROLE_CHARS = 80
MAX_SEARCH_FOCUS_TOTAL_CHARS = 240

_URL_PATTERN = re.compile(
    r"(?:[a-z][a-z0-9+.-]*://|www\.|mailto:|"
    r"(?:[a-z0-9-]+\.)+(?:com|net|org|io|dev|ai|kr|co\.kr)(?:[/\s]|$))",
    re.IGNORECASE,
)
_PATH_PATTERN = re.compile(
    r"(?:^[a-z]:[\\/]|^\\\\|^(?:/|~[/\\]|\.\.?[/\\])|%[A-Z_]+%)",
    re.IGNORECASE,
)
_SLACK_IDENTIFIER_PATTERN = re.compile(
    r"(?:<(?:[@#][A-Z0-9]+(?:\|[^>]*)?|![^>]+)>|"
    r"\b[UWTCGD][A-Z0-9]{7,31}\b)",
)
_SECRET_PATTERN = re.compile(
    r"(?:xox[baprs]-\S+|AIza[0-9A-Za-z_-]{16,}|sk-[0-9A-Za-z_-]{16,}|"
    r"gh[pousr]_[0-9A-Za-z]{16,}|bearer\s+[0-9A-Za-z._~+/-]{12,})",
    re.IGNORECASE,
)
_INJECTION_PATTERNS = (
    re.compile(
        r"\b(?:ignore|disregard)\s+(?:all\s+|any\s+)?"
        r"(?:previous|prior|above)\s+instructions?\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:system\s+prompt|developer\s+message)\b", re.IGNORECASE),
    re.compile(
        r"\b(?:reveal|print|show|expose)\s+(?:the\s+)?"
        r"(?:system\s+prompt|instructions?)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?:이전|위의|기존)\s*(?:지시|지침|명령|규칙)(?:을|를)?\s*무시"),
    re.compile(r"(?:시스템\s*프롬프트|개발자\s*메시지)(?:를|을)?\s*(?:공개|출력|보여)"),
    re.compile(r"(?:명령|셸|쉘)\s*(?:을|를)?\s*실행"),
)
_SHELL_FRAGMENT_PATTERN = re.compile(
    r"(?:`|\$\(|\$\{|&&|\|\||[;|<>]|\brm\s+-rf\b|\bcmd\.exe\b|"
    r"\bpowershell(?:\.exe)?\s+-)",
    re.IGNORECASE,
)
_ALLOWED_PUNCTUATION = frozenset({" ", "+", "#", ".", "-", "&", "(", ")", "/"})
_ACRONYM_SLASH_PATTERN = re.compile(r"(?<=[A-Z0-9])/(?=[A-Z0-9])")


def _normalized_role(value: Any, position: int) -> str:
    if not isinstance(value, str):
        raise JobSearchPlanError(f"search_focus_roles[{position}] 문자열이 필요함")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 제어 문자가 포함됨"
        )
    normalized = " ".join(unicodedata.normalize("NFKC", value).split())
    if not normalized:
        raise JobSearchPlanError(f"search_focus_roles[{position}]이 비어 있음")
    if len(normalized) > MAX_SEARCH_FOCUS_ROLE_CHARS:
        raise JobSearchPlanError(
            f"search_focus_roles[{position}] 길이가 허용 범위를 초과함"
        )
    if _URL_PATTERN.search(normalized):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 URL을 사용할 수 없음"
        )
    if _PATH_PATTERN.search(normalized) or "\\" in normalized:
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 경로를 사용할 수 없음"
        )
    if "/" in _ACRONYM_SLASH_PATTERN.sub("", normalized):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]의 슬래시는 AI/ML 같은 직무 약어에만 사용할 수 있음"
        )
    if _SLACK_IDENTIFIER_PATTERN.search(normalized):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 Slack 식별자를 사용할 수 없음"
        )
    if _SECRET_PATTERN.search(normalized):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 비밀정보 형태를 사용할 수 없음"
        )
    if _SHELL_FRAGMENT_PATTERN.search(normalized):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 명령 구문을 사용할 수 없음"
        )
    if any(pattern.search(normalized) for pattern in _INJECTION_PATTERNS):
        raise JobSearchPlanError(
            f"search_focus_roles[{position}]에 지시 변경 문구를 사용할 수 없음"
        )
    for character in normalized:
        if (
            character not in _ALLOWED_PUNCTUATION
            and not unicodedata.category(character).startswith(("L", "N"))
        ):
            raise JobSearchPlanError(
                f"search_focus_roles[{position}]에 허용되지 않은 문자가 포함됨"
            )
    return normalized


def validate_search_focus_roles(value: Any) -> list[str]:
    """Return normalized inert query terms or reject the entire model output."""

    if not isinstance(value, list):
        raise JobSearchPlanError("search_focus_roles 배열이 필요함")
    if not value:
        raise JobSearchPlanError("search_focus_roles에는 직무가 1개 이상 필요함")
    if len(value) > MAX_SEARCH_FOCUS_ROLES:
        raise JobSearchPlanError("search_focus_roles 개수가 허용 범위를 초과함")
    roles = [_normalized_role(item, position) for position, item in enumerate(value)]
    folded = [role.casefold() for role in roles]
    if len(folded) != len(set(folded)):
        raise JobSearchPlanError("search_focus_roles에는 중복 직무를 사용할 수 없음")
    if sum(len(role) for role in roles) > MAX_SEARCH_FOCUS_TOTAL_CHARS:
        raise JobSearchPlanError("search_focus_roles 전체 길이가 허용 범위를 초과함")
    return roles
