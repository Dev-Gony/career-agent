"""Read one public Greenhouse job and map explicit sections conservatively."""

from __future__ import annotations

from datetime import date
from email.message import Message
from html import unescape
from html.parser import HTMLParser
import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ALLOWED_API_HOST = "boards-api.greenhouse.io"
ALLOWED_CONTENT_TYPES = {"application/json", "text/json"}
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 10.0
USER_AGENT = "career-agent-personal-mvp/0.1"

_BOARD_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
_JOB_ID_PATTERN = re.compile(r"^[0-9]{1,20}$")
_YEAR_PATTERN = re.compile(r"\b(\d{1,2})\s*\+\s*years?\b", re.I)

_RESPONSIBILITY_HEADINGS = (
    "what you'll actually do",
    "what you will actually do",
    "responsibilities",
    "what you'll do",
    "이런 일을 하실 수 있어요",
    "주요 업무",
)
_REQUIREMENT_HEADINGS = (
    "you need to have",
    "requirements",
    "qualifications",
    "이런 분과 함께 하고 싶어요",
    "자격 요건",
    "지원 자격",
)
_PREFERRED_HEADINGS = (
    "added value",
    "preferred qualifications",
    "nice to have",
    "이런 점이 있으시면 더 좋아요",
    "우대 사항",
    "우대사항",
)
_ROLE_HEADINGS = ("the role", "about the role", "포지션 소개", "직무 소개")


class GreenhouseJobError(RuntimeError):
    """Raised when a Greenhouse job cannot be fetched or mapped safely."""


class _ContentParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.events: list[tuple[str, str]] = []
        self._heading_parts: list[str] | None = None
        self._paragraph_parts: list[str] | None = None
        self._list_parts: list[list[str]] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        del attrs
        tag = tag.casefold()
        if tag in {"strong", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_parts = []
        if tag == "p":
            self._paragraph_parts = []
        if tag == "li":
            self._list_parts.append([])
        if tag == "br":
            self._append_text(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag in {"strong", "h1", "h2", "h3", "h4", "h5", "h6"}:
            self._emit("heading", self._heading_parts)
            self._heading_parts = None
        if tag == "li" and self._list_parts:
            self._emit("item", self._list_parts.pop())
        if tag == "p":
            self._emit("paragraph", self._paragraph_parts)
            self._paragraph_parts = None

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def _append_text(self, data: str) -> None:
        if self._heading_parts is not None:
            self._heading_parts.append(data)
        if self._paragraph_parts is not None:
            self._paragraph_parts.append(data)
        if self._list_parts:
            self._list_parts[-1].append(data)

    def _emit(self, event_type: str, parts: list[str] | None) -> None:
        if parts is None:
            return
        text = _clean_text("".join(parts))
        if text:
            self.events.append((event_type, text))


def fetch_greenhouse_job(
    board_token: str,
    job_id: str | int,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> dict[str, Any]:
    """Fetch one job from Greenhouse's public, read-only Job Board API."""

    normalized_board = _validate_board_token(board_token)
    normalized_job_id = _validate_job_id(job_id)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds는 0보다 커야 함")
    if max_bytes <= 0:
        raise ValueError("max_bytes는 0보다 커야 함")

    api_url = (
        f"https://{ALLOWED_API_HOST}/v1/boards/"
        f"{normalized_board}/jobs/{normalized_job_id}"
    )
    request = Request(
        api_url,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        method="GET",
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise GreenhouseJobError(
                    f"Greenhouse 응답 상태가 200이 아님: {status}"
                )
            _validate_api_response_url(response.geturl(), normalized_board, normalized_job_id)
            _validate_content_type(response.headers)
            _validate_content_length(response.headers, max_bytes)
            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise GreenhouseJobError("Greenhouse 응답이 허용 크기를 초과함")
    except HTTPError as error:
        raise GreenhouseJobError(f"Greenhouse HTTP 오류: {error.code}") from error
    except URLError as error:
        raise GreenhouseJobError(f"Greenhouse 네트워크 오류: {error.reason}") from error
    except TimeoutError as error:
        raise GreenhouseJobError("Greenhouse 요청 시간 초과") from error

    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise GreenhouseJobError("Greenhouse JSON 응답을 해석할 수 없음") from error
    if not isinstance(document, dict):
        raise GreenhouseJobError("Greenhouse JSON 최상위 값이 객체가 아님")
    if str(document.get("id")) != normalized_job_id:
        raise GreenhouseJobError("요청한 공고 ID와 응답 공고 ID가 일치하지 않음")
    return document


def build_greenhouse_job_posting(
    job: dict[str, Any],
    *,
    board_token: str,
    collected_at: date | None = None,
) -> dict[str, Any]:
    """Convert explicit Greenhouse fields into the internal job posting schema."""

    if not isinstance(job, dict):
        raise GreenhouseJobError("Greenhouse 공고는 JSON 객체여야 함")
    normalized_board = _validate_board_token(board_token)
    job_id = _validate_job_id(job.get("id"))
    title = _required_text(job, "title")
    company_name = _required_text(job, "company_name")
    absolute_url = _required_https_url(job, "absolute_url")
    content = _required_text(job, "content")
    location_data = job.get("location")
    if not isinstance(location_data, dict):
        raise GreenhouseJobError("Greenhouse location 객체가 필요함")
    location_name = _required_text(location_data, "name")

    events = _parse_content(content)
    sections = _extract_sections(events)
    responsibilities = _numbered_text_items(
        sections["responsibilities"], "responsibility", "text"
    )
    requirements = _numbered_requirement_items(
        sections["requirements"], "requirement", required=True
    )
    preferred = _numbered_requirement_items(
        sections["preferred"], "qualification", required=False
    )
    experience = _extract_experience(sections["requirements"])
    education = _extract_education(sections["requirements"])
    employment_type = _extract_employment_type(title, content)
    remote = _extract_remote_mode(content)
    role_summary = sections["role"][0] if sections["role"] else title

    required_technologies = _technology_names(requirements)
    preferred_technologies = _technology_names(preferred)
    all_plain_text = " ".join(text for _, text in events)
    mentioned = _mentioned_technologies(
        all_plain_text,
        excluded={*required_technologies, *preferred_technologies},
    )
    extraction_unknowns = []
    if employment_type == "unknown":
        extraction_unknowns.append("고용 형태가 제목과 본문에 명시적으로 확인되지 않음")
    if not sections["responsibilities"]:
        extraction_unknowns.append("인식 가능한 주요 업무 섹션을 찾지 못함")
    if not sections["requirements"]:
        extraction_unknowns.append("인식 가능한 필수 조건 섹션을 찾지 못함")

    collection_date = collected_at or date.today()
    return {
        "job_posting": {
            "identity": {
                "posting_id": f"greenhouse-{normalized_board}-{job_id}",
                "title": title,
                "status": "open",
            },
            "source": {
                "platform": "greenhouse",
                "url": absolute_url,
                "collected_at": collection_date.isoformat(),
                "input_method": "ats_api",
                "board_token": normalized_board,
                "external_job_id": job_id,
                "updated_at": str(job.get("updated_at") or "unknown"),
            },
            "company": {
                "name": company_name,
                "industry": "unknown",
                "size": "unknown",
            },
            "role": {
                "normalized_title": title,
                "category": "unknown",
                "seniority": _extract_seniority(title),
                "summary": role_summary,
            },
            "responsibilities": responsibilities,
            "requirements": requirements,
            "preferred_qualifications": preferred,
            "technologies": {
                "required": required_technologies,
                "preferred": preferred_technologies,
                "mentioned": mentioned,
            },
            "experience": experience,
            "education": education,
            "employment": {
                "type": employment_type,
                "contract_period": None,
                "probation": "unknown",
            },
            "location": {
                "region": _normalize_region(location_name),
                "district": None,
                "remote": remote,
            },
            "compensation": {
                "disclosed": False,
                "min": None,
                "max": None,
                "currency": "unknown",
                "period": "unknown",
            },
            "work_environment": {
                "collaboration": [],
                "pace": [],
                "ownership": [],
            },
            "extracted_keywords": {
                "role_keywords": _role_keywords(title),
                "skill_keywords": [
                    *required_technologies,
                    *preferred_technologies,
                    *mentioned,
                ],
            },
            "analysis_notes": {
                "facts": [
                    "Greenhouse 공개 Job Board API에서 현재 공고 상세를 조회함",
                    f"근무지는 API에서 '{location_name}'로 제공됨",
                    "필수·우대·주요 업무는 인식된 원문 섹션의 항목만 구조화함",
                ],
                "interpretations": [
                    "섹션 제목과 명시적 기술명에 한정한 규칙 기반 추출 결과",
                ],
                "unknowns": extraction_unknowns,
            },
            "raw_text": (
                "공고 전문은 저장하지 않음. 구조화된 항목과 source.url에서 원문 확인 가능."
            ),
        }
    }


def _validate_board_token(value: Any) -> str:
    if not isinstance(value, str) or not _BOARD_TOKEN_PATTERN.fullmatch(value):
        raise GreenhouseJobError("board_token 형식이 올바르지 않음")
    return value


def _validate_job_id(value: Any) -> str:
    if isinstance(value, bool):
        raise GreenhouseJobError("job_id 형식이 올바르지 않음")
    normalized = str(value)
    if not _JOB_ID_PATTERN.fullmatch(normalized):
        raise GreenhouseJobError("job_id 형식이 올바르지 않음")
    return normalized


def _validate_api_response_url(url: str, board_token: str, job_id: str) -> None:
    parts = urlsplit(url)
    expected_path = f"/v1/boards/{board_token}/jobs/{job_id}"
    if (
        parts.scheme != "https"
        or parts.hostname != ALLOWED_API_HOST
        or parts.path.rstrip("/") != expected_path
        or parts.username
        or parts.password
    ):
        raise GreenhouseJobError("허용되지 않은 Greenhouse 응답 URL")


def _validate_content_type(headers: Message) -> None:
    content_type = headers.get_content_type().casefold()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise GreenhouseJobError(f"Greenhouse JSON 콘텐츠 형식이 아님: {content_type}")


def _validate_content_length(headers: Message, max_bytes: int) -> None:
    content_length = headers.get("Content-Length")
    if content_length is None:
        return
    try:
        declared_size = int(content_length)
    except ValueError as error:
        raise GreenhouseJobError("Content-Length를 해석할 수 없음") from error
    if declared_size < 0 or declared_size > max_bytes:
        raise GreenhouseJobError("Greenhouse 응답이 허용 크기를 초과함")


def _required_text(document: dict[str, Any], key: str) -> str:
    value = document.get(key)
    if not isinstance(value, str) or not value.strip():
        raise GreenhouseJobError(f"Greenhouse '{key}' 문자열이 필요함")
    return _clean_text(value)


def _required_https_url(document: dict[str, Any], key: str) -> str:
    value = _required_text(document, key)
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise GreenhouseJobError(f"Greenhouse '{key}'는 인증정보 없는 HTTPS URL이어야 함")
    return value


def _decode_html(value: str) -> str:
    decoded = value
    for _ in range(2):
        candidate = unescape(decoded)
        if candidate == decoded:
            break
        decoded = candidate
    return decoded


def _parse_content(content: str) -> list[tuple[str, str]]:
    parser = _ContentParser()
    try:
        parser.feed(_decode_html(content))
        parser.close()
    except Exception as error:
        raise GreenhouseJobError("Greenhouse HTML 본문을 해석할 수 없음") from error
    return parser.events


def _clean_text(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())


def _classify_heading(heading: str) -> str | None:
    normalized = heading.casefold().strip().rstrip(":")
    if any(term in normalized for term in _RESPONSIBILITY_HEADINGS):
        return "responsibilities"
    if any(term in normalized for term in _PREFERRED_HEADINGS):
        return "preferred"
    if any(term in normalized for term in _REQUIREMENT_HEADINGS):
        return "requirements"
    if any(term == normalized for term in _ROLE_HEADINGS):
        return "role"
    return None


def _extract_sections(events: list[tuple[str, str]]) -> dict[str, list[str]]:
    sections = {
        "responsibilities": [],
        "requirements": [],
        "preferred": [],
        "role": [],
    }
    active_section: str | None = None
    last_heading = ""
    for event_type, text in events:
        if event_type == "heading":
            active_section = _classify_heading(text)
            last_heading = text
            continue
        if active_section is None:
            continue
        cleaned = text
        if last_heading and cleaned.casefold().startswith(last_heading.casefold()):
            cleaned = _clean_text(cleaned[len(last_heading) :].lstrip(" :"))
        if not cleaned:
            continue
        if active_section == "role" and event_type == "paragraph":
            sections[active_section].append(cleaned)
            active_section = None
        elif active_section != "role" and event_type == "item":
            if cleaned not in sections[active_section]:
                sections[active_section].append(cleaned)
    return sections


def _numbered_text_items(
    texts: list[str], id_prefix: str, text_field: str
) -> list[dict[str, str]]:
    return [
        {f"{id_prefix}_id": f"{id_prefix}-{position:03d}", text_field: text}
        for position, text in enumerate(texts, start=1)
    ]


def _requirement_identity(text: str) -> tuple[str, str]:
    normalized = text.casefold()
    if "python" in normalized:
        return "skill", "Python"
    if "llm api" in normalized or "large language model api" in normalized:
        return "skill", "LLM API"
    if "rest api" in normalized and (
        "integration" in normalized or "integrat" in normalized or "연동" in text
    ):
        return "experience", "REST API integration"
    if "langchain" in normalized or "langgraph" in normalized:
        return "skill", "LangChain / LangGraph"
    if "vector database" in normalized or "vector db" in normalized:
        return "skill", "Vector database"
    if "aws" in normalized and "gcp" not in normalized:
        return "cloud", "AWS"
    if "gcp" in normalized and "aws" not in normalized:
        return "cloud", "GCP"
    if "english" in normalized or "영어" in text:
        return "language", "English"
    if _YEAR_PATTERN.search(text) and "experience" in normalized:
        return "experience", "software engineering experience"
    if "automation" in normalized or "자동화" in text:
        return "experience", "automation project"
    concise_name = text if len(text) <= 80 else f"{text[:77].rstrip()}..."
    return "other", concise_name


def _numbered_requirement_items(
    texts: list[str], id_prefix: str, *, required: bool
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for position, text in enumerate(texts, start=1):
        item_type, name = _requirement_identity(text)
        item: dict[str, Any] = {
            f"{id_prefix}_id": f"{id_prefix}-{position:03d}",
            "type": item_type,
            "name": name,
            "evidence_text": text,
        }
        if required:
            item["level"] = "required"
        items.append(item)
    return items


def _technology_names(items: list[dict[str, Any]]) -> list[str]:
    return [item["name"] for item in items if item["type"] in {"skill", "cloud"}]


def _mentioned_technologies(text: str, *, excluded: set[str]) -> list[str]:
    candidates = (
        ("RAG", r"\brag\b"),
        ("AWS", r"\baws\b"),
        ("GCP", r"\bgcp\b"),
        ("Docker", r"\bdocker\b"),
        ("CI/CD", r"\bci\s*/\s*cd\b"),
    )
    return [
        name
        for name, pattern in candidates
        if name not in excluded and re.search(pattern, text, re.I)
    ]


def _extract_experience(requirements: list[str]) -> dict[str, Any]:
    for requirement in requirements:
        match = _YEAR_PATTERN.search(requirement)
        if match:
            return {
                "minimum_years": int(match.group(1)),
                "maximum_years": None,
                "level_text": requirement,
                "equivalent_experience_allowed": False,
            }
    return {
        "minimum_years": None,
        "maximum_years": None,
        "level_text": "경력 연수 미확인",
        "equivalent_experience_allowed": False,
    }


def _extract_education(requirements: list[str]) -> dict[str, Any]:
    combined = " ".join(requirements).casefold()
    levels = (
        ("doctorate", ("doctorate", "phd", "박사")),
        ("master", ("master's", "masters", "석사")),
        ("bachelor", ("bachelor's", "bachelors", "학사")),
        ("associate", ("associate degree", "전문학사")),
    )
    for level, terms in levels:
        if any(term in combined for term in terms):
            return {"required": True, "level": level, "notes": None}
    return {"required": False, "level": "not_required", "notes": None}


def _extract_employment_type(title: str, content: str) -> str:
    combined = f"{title} {_decode_html(content)}".casefold()
    title_normalized = title.casefold()
    if "intern" in title_normalized or "인턴" in title:
        return "internship"
    if "contract" in title_normalized or "계약직" in title:
        return "contract"
    explicit_patterns = (
        ("full_time", ("full-time position", "full time position", "정규직 포지션")),
        ("part_time", ("part-time position", "part time position", "파트타임")),
        ("freelance", ("freelance position", "프리랜서")),
    )
    for employment_type, terms in explicit_patterns:
        if any(term in combined for term in terms):
            return employment_type
    return "unknown"


def _extract_remote_mode(content: str) -> str:
    normalized = _decode_html(content).casefold()
    if "hybrid work" in normalized or "하이브리드" in normalized:
        return "hybrid"
    if "fully remote" in normalized or "100% remote" in normalized or "완전 원격" in normalized:
        return "remote"
    if "on-site" in normalized or "onsite" in normalized or "상주 근무" in normalized:
        return "onsite"
    return "unknown"


def _normalize_region(location_name: str) -> str:
    normalized = location_name.casefold()
    if "seoul" in normalized or "서울" in location_name:
        return "서울"
    return location_name


def _extract_seniority(title: str) -> str:
    normalized = title.casefold()
    if "intern" in normalized or "인턴" in title:
        return "intern"
    if any(term in normalized for term in ("senior", "staff", "lead", "principal")):
        return "senior"
    if "junior" in normalized:
        return "junior"
    return "unknown"


def _role_keywords(title: str) -> list[str]:
    keywords = []
    for name, pattern in (
        ("AI", r"\bai\b"),
        ("automation", r"\bautomation\b"),
        ("solution", r"\bsolutions?\b"),
        ("data", r"\bdata\b"),
        ("engineer", r"\bengineer\b"),
    ):
        if re.search(pattern, title, re.I):
            keywords.append(name)
    return keywords
