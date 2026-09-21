"""Extract reviewable profile candidates from a stored career document."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Mapping
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from .document_store import PROFILE_DOCUMENT_SCHEMA_VERSION, ProfileDocumentError


PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION = "0.1"
PROFILE_TEXT_EXTRACTION_RULES_VERSION = "0.3"
MAX_DOCX_DOCUMENT_XML_BYTES = 8 * 1024 * 1024
MAX_DOCX_PARAGRAPHS = 20_000
_MAX_STORED_EXTRACTION_FILES = 1000
_SUPPORTED_FORMATS = {"plain_text", "markdown", "docx"}
_WORDPROCESSINGML_NAMESPACE = (
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
)
_WORD_PARAGRAPH_TAG = f"{{{_WORDPROCESSINGML_NAMESPACE}}}p"
_WORD_TEXT_TAG = f"{{{_WORDPROCESSINGML_NAMESPACE}}}t"
_WORD_TAB_TAG = f"{{{_WORDPROCESSINGML_NAMESPACE}}}tab"
_WORD_BREAK_TAGS = {
    f"{{{_WORDPROCESSINGML_NAMESPACE}}}br",
    f"{{{_WORDPROCESSINGML_NAMESPACE}}}cr",
}
_HEADING_SECTIONS = {
    "경력": "career_history",
    "경력사항": "career_history",
    "경력 요약": "career_history",
    "경력요약": "career_history",
    "경력 기술": "career_history",
    "경력기술": "career_history",
    "career": "career_history",
    "experience": "career_history",
    "work experience": "career_history",
    "프로젝트": "projects",
    "주요 프로젝트": "projects",
    "project": "projects",
    "projects": "projects",
    "기술": "skills",
    "기술 스택": "skills",
    "보유 기술": "skills",
    "skill": "skills",
    "skills": "skills",
    "technical skills": "skills",
    "학력": "education",
    "교육": "education",
    "education": "education",
    "희망 직무": "target_roles",
    "지원 분야": "target_roles",
    "target role": "target_roles",
    "target roles": "target_roles",
    "desired role": "target_roles",
    "업무 선호": "work_preferences",
    "근무 선호": "work_preferences",
    "work preferences": "work_preferences",
}
_SENSITIVE_HEADINGS = {
    "개인정보",
    "연락처",
    "주소",
    "contact",
    "contact information",
    "address",
}
_EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_PATTERN = re.compile(
    r"(?<!\d)(?:(?:\+?82[-\s]?)?0?1[016789]|0\d{1,2})[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"
)
_RESIDENT_ID_PATTERN = re.compile(r"(?<!\d)\d{6}-?[1-4]\d{6}(?!\d)")
_SENSITIVE_LABEL_PATTERN = re.compile(
    r"^\s*(?:이메일|email|전화|전화번호|휴대폰|연락처|phone|주소|address)\s*[:：]",
    re.I,
)
_MARKDOWN_HEADING_PATTERN = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$")
_BULLET_PATTERN = re.compile(r"^\s*(?:[-*+] |\d+[.)]\s+)(.+)$")
_EXTRACTION_ID_PATTERN = re.compile(r"^profile-text-extraction-[0-9a-f]{24}$")
_CANDIDATE_ID_PATTERN = re.compile(r"^candidate-\d{3,6}$")


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _normalized_heading(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().rstrip(":：")).casefold()


def _heading(line: str) -> tuple[str | None, str | None, bool]:
    markdown = _MARKDOWN_HEADING_PATTERN.match(line)
    raw = markdown.group(1) if markdown else line.strip()
    normalized = _normalized_heading(raw)
    if normalized in _SENSITIVE_HEADINGS:
        return None, None, True
    section = _HEADING_SECTIONS.get(normalized)
    if section is not None:
        return section, None, True
    for separator in (":", "："):
        if separator not in raw:
            continue
        heading_text, inline_text = raw.split(separator, 1)
        normalized = _normalized_heading(heading_text)
        if normalized in _SENSITIVE_HEADINGS:
            return None, None, True
        section = _HEADING_SECTIONS.get(normalized)
        if section is not None:
            return section, inline_text.strip() or None, True
    if markdown:
        return None, None, True
    return None, None, False


def _contains_sensitive_contact(line: str) -> bool:
    return any(
        pattern.search(line) is not None
        for pattern in (
            _EMAIL_PATTERN,
            _PHONE_PATTERN,
            _RESIDENT_ID_PATTERN,
            _SENSITIVE_LABEL_PATTERN,
        )
    )


def _candidate_text(line: str) -> str:
    bullet = _BULLET_PATTERN.match(line)
    value = bullet.group(1) if bullet else line
    return re.sub(r"\s+", " ", value).strip()


def _utf8_lines(content: bytes) -> list[str]:
    try:
        body = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ProfileDocumentError("텍스트 문서는 UTF-8이어야 함") from error
    return body.splitlines()


def _read_docx_document_xml(content: bytes) -> bytes:
    try:
        with ZipFile(BytesIO(content)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.flag_bits & 0x1:
                raise ProfileDocumentError("암호화된 DOCX 본문은 추출할 수 없음")
            if not 0 < info.file_size <= MAX_DOCX_DOCUMENT_XML_BYTES:
                raise ProfileDocumentError("DOCX 본문 XML 크기가 허용 범위를 벗어남")
            with archive.open(info) as document_file:
                document_xml = document_file.read(MAX_DOCX_DOCUMENT_XML_BYTES + 1)
    except KeyError as error:
        raise ProfileDocumentError("DOCX에 word/document.xml이 없음") from error
    except BadZipFile as error:
        raise ProfileDocumentError("DOCX ZIP 구조를 읽을 수 없음") from error
    if len(document_xml) > MAX_DOCX_DOCUMENT_XML_BYTES:
        raise ProfileDocumentError("DOCX 본문 XML이 허용 크기를 초과함")
    return document_xml


def _docx_lines(content: bytes) -> list[str]:
    document_xml = _read_docx_document_xml(content)
    upper_xml = document_xml.upper()
    if b"<!DOCTYPE" in upper_xml or b"<!ENTITY" in upper_xml:
        raise ProfileDocumentError("DOCX 본문 XML의 DTD 또는 ENTITY는 허용하지 않음")
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError as error:
        raise ProfileDocumentError("DOCX 본문 XML을 해석할 수 없음") from error

    lines: list[str] = []
    paragraph_count = 0
    for paragraph in root.iter(_WORD_PARAGRAPH_TAG):
        paragraph_count += 1
        if paragraph_count > MAX_DOCX_PARAGRAPHS:
            raise ProfileDocumentError("DOCX 문단 수가 허용 범위를 초과함")
        parts: list[str] = []
        for node in paragraph.iter():
            if node.tag == _WORD_TEXT_TAG and node.text:
                parts.append(node.text)
            elif node.tag == _WORD_TAB_TAG:
                parts.append("\t")
            elif node.tag in _WORD_BREAK_TAGS:
                parts.append("\n")
        paragraph_text = "".join(parts)
        lines.extend(paragraph_text.splitlines() or [paragraph_text])
    return lines


def _document_lines(
    document_format: str,
    content: bytes,
) -> tuple[list[str], str, str]:
    if document_format in {"plain_text", "markdown"}:
        return (
            _utf8_lines(content),
            "heading_based_text",
            "UTF-8 문서에서 인식된 섹션 제목과 원문 줄 위치만 사용함",
        )
    if document_format == "docx":
        return (
            _docx_lines(content),
            "heading_based_docx",
            "DOCX 본문의 문단 순서와 인식된 섹션 제목만 사용함",
        )
    raise ProfileDocumentError("현재는 UTF-8 TXT, Markdown와 DOCX만 추출할 수 있음")


def build_profile_text_extraction(
    manifest: Mapping[str, Any],
    content: bytes,
    *,
    extracted_at: datetime,
) -> dict[str, Any]:
    """Build heading-based candidates without changing the user profile."""

    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise ProfileDocumentError("extracted_at은 시간대가 포함되어야 함")
    document = _mapping(manifest.get("profile_document"), "profile_document")
    metadata = _mapping(manifest.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_DOCUMENT_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 문서 manifest가 아님")
    document_format = document.get("document_format")
    if document_format not in _SUPPORTED_FORMATS:
        raise ProfileDocumentError(
            "현재는 UTF-8 TXT, Markdown와 DOCX만 추출할 수 있음"
        )
    expected_hash = _text(
        document.get("content_sha256"), "profile_document.content_sha256"
    )
    if sha256(content).hexdigest() != expected_hash:
        raise ProfileDocumentError("추출할 원본의 내용 해시가 manifest와 다름")
    lines, extraction_method, extraction_fact = _document_lines(
        document_format,
        content,
    )

    document_id = _text(document.get("document_id"), "profile_document.document_id")
    candidates: list[dict[str, Any]] = []
    active_section: str | None = None
    sensitive_count = 0
    unclassified_count = 0
    oversized_count = 0
    for line_number, raw_line in enumerate(lines, start=1):
        if not raw_line.strip():
            continue
        section, inline_text, is_heading = _heading(raw_line)
        if is_heading:
            active_section = section
            if inline_text is None:
                continue
            raw_line = inline_text
        if _contains_sensitive_contact(raw_line):
            sensitive_count += 1
            continue
        if active_section is None:
            unclassified_count += 1
            continue
        candidate_text = _candidate_text(raw_line)
        if not candidate_text:
            continue
        if len(candidate_text) > 1000:
            oversized_count += 1
            continue
        candidates.append(
            {
                "candidate_id": f"candidate-{len(candidates) + 1:03d}",
                "profile_section": active_section,
                "text": candidate_text,
                "status": "needs_review",
                "source_evidence": {
                    "document_id": document_id,
                    "line_start": line_number,
                    "line_end": line_number,
                },
            }
        )

    section_counts = Counter(
        candidate["profile_section"] for candidate in candidates
    )
    extraction_key = f"{document_id}|{PROFILE_TEXT_EXTRACTION_RULES_VERSION}"
    extraction_id = "profile-text-extraction-" + sha256(
        extraction_key.encode("utf-8")
    ).hexdigest()[:24]
    unknowns = [
        "제목 아래 문장을 프로필 후보로만 분류했으며 사실 여부는 사용자 확인 필요"
    ]
    if not candidates:
        unknowns.append("인식된 섹션 아래에서 프로필 후보를 찾지 못함")
    return {
        "profile_extraction": {
            "extraction_id": extraction_id,
            "extracted_at": extracted_at.isoformat(timespec="microseconds"),
            "method": extraction_method,
            "rules_version": PROFILE_TEXT_EXTRACTION_RULES_VERSION,
            "status": "needs_review",
        },
        "source_document": {
            "document_id": document_id,
            "document_kind": document.get("document_kind"),
            "document_format": document_format,
            "content_sha256": expected_hash,
        },
        "summary": {
            "candidate_count": len(candidates),
            "section_counts": dict(section_counts),
            "omitted_sensitive_line_count": sensitive_count,
            "unclassified_nonempty_line_count": unclassified_count,
            "omitted_oversized_line_count": oversized_count,
        },
        "candidates": candidates,
        "analysis_notes": {
            "facts": [
                extraction_fact,
                "연락처 형태의 줄은 후보 내용에 포함하지 않음",
            ],
            "unknowns": unknowns,
        },
        "metadata": {
            "schema_version": PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION,
            "contains_personal_data": True,
            "git_tracking_allowed": False,
            "profile_updated": False,
        },
    }


def save_profile_text_extraction(
    extraction: Mapping[str, Any],
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically save or reuse one extraction for the same document and rules."""

    root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    source = _mapping(extraction.get("source_document"), "source_document")
    metadata = _mapping(extraction.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 텍스트 추출 결과가 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("텍스트 추출 결과에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("검토 전 추출 결과는 프로필 갱신 상태일 수 없음")
    extraction_id = _text(
        root.get("extraction_id"), "profile_extraction.extraction_id"
    )
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{extraction_id}.json"
    if target_path.exists():
        try:
            existing = json.loads(target_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError(
                f"기존 텍스트 추출 결과를 읽을 수 없음: {target_path}"
            ) from error
        existing_root = _mapping(
            existing.get("profile_extraction"), "profile_extraction"
        )
        existing_source = _mapping(existing.get("source_document"), "source_document")
        if (
            existing_root.get("extraction_id") != root.get("extraction_id")
            or existing_root.get("method") != root.get("method")
            or existing_root.get("rules_version") != root.get("rules_version")
            or existing_root.get("status") != root.get("status")
            or existing_source.get("document_id") != source.get("document_id")
            or existing_source.get("content_sha256") != source.get("content_sha256")
        ):
            raise ProfileDocumentError("같은 추출 ID의 기존 결과가 입력과 일치하지 않음")
        for field in (
            "source_document",
            "summary",
            "candidates",
            "analysis_notes",
            "metadata",
        ):
            if existing.get(field) != extraction.get(field):
                raise ProfileDocumentError(
                    f"같은 추출 ID의 기존 결과 내용이 일치하지 않음: {field}"
                )
        return target_path, False

    serialized = json.dumps(extraction, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{extraction_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ProfileDocumentError(
            f"텍스트 추출 결과를 저장할 수 없음: {target_path}"
        ) from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path, True


def load_profile_text_extraction(
    extraction_id: str,
    directory: str | Path,
) -> dict[str, Any]:
    """Load and validate one private profile extraction result."""

    normalized_id = _text(extraction_id, "extraction_id")
    if _EXTRACTION_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("extraction_id 형식이 올바르지 않음")
    path = Path(directory) / f"{normalized_id}.json"
    if path.is_symlink():
        raise ProfileDocumentError("프로필 추출 결과 심볼릭 링크는 읽을 수 없음")
    try:
        extraction = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(
            f"프로필 추출 결과를 읽을 수 없음: {path}"
        ) from error
    root = _mapping(extraction.get("profile_extraction"), "profile_extraction")
    source = _mapping(extraction.get("source_document"), "source_document")
    metadata = _mapping(extraction.get("metadata"), "metadata")
    if root.get("extraction_id") != normalized_id:
        raise ProfileDocumentError("추출 결과의 extraction_id가 요청과 일치하지 않음")
    if root.get("rules_version") != PROFILE_TEXT_EXTRACTION_RULES_VERSION:
        raise ProfileDocumentError("현재 규칙 버전의 프로필 추출 결과가 아님")
    if root.get("status") != "needs_review":
        raise ProfileDocumentError("검토 대기 상태인 프로필 추출 결과가 아님")
    extracted_at_text = _text(
        root.get("extracted_at"), "profile_extraction.extracted_at"
    )
    try:
        extracted_at = datetime.fromisoformat(extracted_at_text)
    except ValueError as error:
        raise ProfileDocumentError("프로필 추출 시간이 올바르지 않음") from error
    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise ProfileDocumentError("프로필 추출 시간에 시간대가 필요함")
    if metadata.get("schema_version") != PROFILE_TEXT_EXTRACTION_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 프로필 추출 결과가 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("프로필 추출 결과에 Git 제외 표시가 없음")
    if metadata.get("profile_updated") is not False:
        raise ProfileDocumentError("검토 전 추출 결과는 프로필 갱신 상태일 수 없음")
    document_id = _text(source.get("document_id"), "source_document.document_id")
    expected_id = "profile-text-extraction-" + sha256(
        f"{document_id}|{PROFILE_TEXT_EXTRACTION_RULES_VERSION}".encode("utf-8")
    ).hexdigest()[:24]
    if normalized_id != expected_id:
        raise ProfileDocumentError("프로필 추출 ID와 문서 지문이 일치하지 않음")
    candidates = extraction.get("candidates")
    if not isinstance(candidates, list):
        raise ProfileDocumentError("candidates 배열이 필요함")
    candidate_ids: set[str] = set()
    for position, raw_candidate in enumerate(candidates):
        candidate = _mapping(raw_candidate, f"candidates[{position}]")
        candidate_id = _text(
            candidate.get("candidate_id"), f"candidates[{position}].candidate_id"
        )
        if _CANDIDATE_ID_PATTERN.fullmatch(candidate_id) is None:
            raise ProfileDocumentError(
                f"candidates[{position}].candidate_id 형식이 올바르지 않음"
            )
        if candidate_id in candidate_ids:
            raise ProfileDocumentError(f"중복 candidate_id: {candidate_id}")
        candidate_ids.add(candidate_id)
        if candidate.get("status") != "needs_review":
            raise ProfileDocumentError(
                f"candidates[{position}].status는 needs_review여야 함"
            )
        _text(candidate.get("profile_section"), f"candidates[{position}].profile_section")
        _text(candidate.get("text"), f"candidates[{position}].text")
        evidence = _mapping(
            candidate.get("source_evidence"),
            f"candidates[{position}].source_evidence",
        )
        if evidence.get("document_id") != document_id:
            raise ProfileDocumentError(
                f"candidates[{position}]의 문서 근거가 source_document와 다름"
            )
        for field in ("line_start", "line_end"):
            value = evidence.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ProfileDocumentError(
                    f"candidates[{position}].source_evidence.{field}가 올바르지 않음"
                )
        if evidence["line_end"] < evidence["line_start"]:
            raise ProfileDocumentError(
                f"candidates[{position}]의 원문 줄 범위가 올바르지 않음"
            )
    summary = _mapping(extraction.get("summary"), "summary")
    candidate_count = summary.get("candidate_count")
    if (
        isinstance(candidate_count, bool)
        or not isinstance(candidate_count, int)
        or candidate_count != len(candidates)
    ):
        raise ProfileDocumentError("프로필 추출 후보 합계가 일치하지 않음")
    return extraction


def select_latest_profile_text_extraction(
    directory: str | Path,
) -> dict[str, Any] | None:
    """Select the newest verified extraction for the single-user local MVP."""

    target_directory = Path(directory)
    if not target_directory.exists():
        return None
    if not target_directory.is_dir() or target_directory.is_symlink():
        raise ProfileDocumentError("프로필 추출 경로가 안전한 디렉터리가 아님")
    paths = sorted(target_directory.glob("profile-text-extraction-*.json"))
    if len(paths) > _MAX_STORED_EXTRACTION_FILES:
        raise ProfileDocumentError("프로필 추출 파일이 허용 개수를 초과함")

    verified: list[tuple[datetime, str, dict[str, Any]]] = []
    for path in paths:
        if path.is_symlink():
            raise ProfileDocumentError("프로필 추출 결과 심볼릭 링크는 읽을 수 없음")
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise ProfileDocumentError(
                f"프로필 추출 결과를 읽을 수 없음: {path}"
            ) from error
        stored_root = _mapping(
            stored.get("profile_extraction"),
            "profile_extraction",
        )
        if stored_root.get("rules_version") != PROFILE_TEXT_EXTRACTION_RULES_VERSION:
            continue
        extraction = load_profile_text_extraction(path.stem, target_directory)
        extracted_at_text = extraction["profile_extraction"]["extracted_at"]
        extracted_at = datetime.fromisoformat(extracted_at_text)
        verified.append((extracted_at, path.stem, extraction))
    if not verified:
        return None
    return max(verified, key=lambda item: (item[0], item[1]))[2]
