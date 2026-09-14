"""Validate and privately store one user-supplied career document."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, Mapping
from zipfile import BadZipFile, ZipFile


PROFILE_DOCUMENT_SCHEMA_VERSION = "0.1"
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024
DOCUMENT_KINDS = frozenset({"resume", "career_history", "portfolio", "other"})
SOURCE_TYPES = frozenset({"local_file", "slack_attachment", "telegram_attachment"})
_FORMATS = {
    ".txt": "plain_text",
    ".md": "markdown",
    ".pdf": "pdf",
    ".docx": "docx",
}
_DOCUMENT_ID_PATTERN = re.compile(
    r"^profile-document-(?:resume|career_history|portfolio|other)-[0-9a-f]{20}$"
)


class ProfileDocumentError(ValueError):
    """Raised when a private profile document cannot be accepted safely."""


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileDocumentError(f"{name} 문자열이 필요함")
    return value.strip()


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ProfileDocumentError(f"{name} 객체가 필요함")
    return value


def _validate_content(document_format: str, content: bytes) -> None:
    if document_format in {"plain_text", "markdown"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ProfileDocumentError("텍스트 문서는 UTF-8이어야 함") from error
        if "\x00" in text:
            raise ProfileDocumentError("텍스트 문서에 null 문자가 포함됨")
        return
    if document_format == "pdf":
        if not content.startswith(b"%PDF-"):
            raise ProfileDocumentError("확장자는 PDF이지만 PDF 서명이 없음")
        return
    if document_format == "docx":
        try:
            with ZipFile(BytesIO(content)) as archive:
                names = set(archive.namelist())
        except BadZipFile as error:
            raise ProfileDocumentError("확장자는 DOCX이지만 ZIP 구조가 아님") from error
        required = {"[Content_Types].xml", "word/document.xml"}
        if not required.issubset(names):
            raise ProfileDocumentError("DOCX 필수 문서 항목이 없음")


def _read_document(source_path: Path, max_bytes: int) -> bytes:
    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < 1:
        raise ProfileDocumentError("max_bytes는 1 이상의 정수여야 함")
    if not source_path.is_file():
        raise ProfileDocumentError(f"입력 문서 파일을 찾을 수 없음: {source_path}")
    try:
        with source_path.open("rb") as source_file:
            content = source_file.read(max_bytes + 1)
    except OSError as error:
        raise ProfileDocumentError(f"입력 문서를 읽을 수 없음: {source_path}") from error
    if not content:
        raise ProfileDocumentError("빈 문서는 가져올 수 없음")
    if len(content) > max_bytes:
        raise ProfileDocumentError(f"문서 크기는 {max_bytes}바이트 이하여야 함")
    return content


def build_profile_document_import(
    source_path: str | Path,
    *,
    document_kind: str,
    imported_at: datetime,
    source_type: str = "local_file",
    max_bytes: int = MAX_DOCUMENT_BYTES,
) -> tuple[dict[str, Any], bytes]:
    """Validate a document and build a content-free private storage manifest."""

    if imported_at.tzinfo is None or imported_at.utcoffset() is None:
        raise ProfileDocumentError("imported_at은 시간대가 포함되어야 함")
    if document_kind not in DOCUMENT_KINDS:
        allowed = ", ".join(sorted(DOCUMENT_KINDS))
        raise ProfileDocumentError(f"document_kind 허용값: {allowed}")
    if source_type not in SOURCE_TYPES:
        allowed = ", ".join(sorted(SOURCE_TYPES))
        raise ProfileDocumentError(f"source_type 허용값: {allowed}")

    path = Path(source_path)
    suffix = path.suffix.casefold()
    document_format = _FORMATS.get(suffix)
    if document_format is None:
        allowed = ", ".join(sorted(_FORMATS))
        raise ProfileDocumentError(f"허용 문서 확장자: {allowed}")
    content = _read_document(path, max_bytes)
    _validate_content(document_format, content)

    content_hash = sha256(content).hexdigest()
    document_id = f"profile-document-{document_kind}-{content_hash[:20]}"
    stored_filename = f"original{suffix}"
    return (
        {
            "profile_document": {
                "document_id": document_id,
                "imported_at": imported_at.isoformat(timespec="microseconds"),
                "document_kind": document_kind,
                "source_type": source_type,
                "original_filename": path.name,
                "document_format": document_format,
                "stored_filename": stored_filename,
                "size_bytes": len(content),
                "content_sha256": content_hash,
                "processing_status": "stored_unparsed",
            },
            "metadata": {
                "schema_version": PROFILE_DOCUMENT_SCHEMA_VERSION,
                "contains_personal_data": True,
                "git_tracking_allowed": False,
                "contains_document_content": False,
            },
        },
        content,
    )


def _validate_existing_import(
    target_directory: Path,
    manifest: Mapping[str, Any],
    content: bytes,
) -> Path:
    manifest_path = target_directory / "manifest.json"
    try:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(
            f"기존 문서 저장소가 불완전함: {target_directory}"
        ) from error
    existing_root = _mapping(existing.get("profile_document"), "profile_document")
    expected_root = _mapping(manifest.get("profile_document"), "profile_document")
    for field in ("document_id", "document_kind", "content_sha256", "size_bytes"):
        if existing_root.get(field) != expected_root.get(field):
            raise ProfileDocumentError(
                f"같은 문서 ID의 기존 메타데이터가 일치하지 않음: {field}"
            )
    stored_filename = _text(
        existing_root.get("stored_filename"), "profile_document.stored_filename"
    )
    if Path(stored_filename).name != stored_filename:
        raise ProfileDocumentError("기존 stored_filename이 파일명이 아님")
    stored_path = target_directory / stored_filename
    try:
        existing_content = stored_path.read_bytes()
    except OSError as error:
        raise ProfileDocumentError(
            f"기존 원본 문서를 읽을 수 없음: {stored_path}"
        ) from error
    if sha256(existing_content).hexdigest() != sha256(content).hexdigest():
        raise ProfileDocumentError("기존 원본 문서의 내용 해시가 일치하지 않음")
    return manifest_path


def save_profile_document_import(
    manifest: Mapping[str, Any],
    content: bytes,
    directory: str | Path,
) -> tuple[Path, bool]:
    """Atomically store one immutable document directory or reuse an identical one."""

    root = _mapping(manifest.get("profile_document"), "profile_document")
    metadata = _mapping(manifest.get("metadata"), "metadata")
    if metadata.get("schema_version") != PROFILE_DOCUMENT_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 문서 메타데이터가 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("문서 메타데이터에 Git 제외 표시가 없음")
    document_id = _text(root.get("document_id"), "profile_document.document_id")
    stored_filename = _text(
        root.get("stored_filename"), "profile_document.stored_filename"
    )
    if Path(stored_filename).name != stored_filename:
        raise ProfileDocumentError("stored_filename은 파일명이어야 함")
    expected_hash = _text(
        root.get("content_sha256"), "profile_document.content_sha256"
    )
    if sha256(content).hexdigest() != expected_hash:
        raise ProfileDocumentError("저장할 원본과 메타데이터의 내용 해시가 다름")

    target_root = Path(directory)
    target_root.mkdir(parents=True, exist_ok=True)
    target_directory = target_root / document_id
    if target_directory.exists():
        return _validate_existing_import(target_directory, manifest, content), False

    temporary_directory = Path(
        tempfile.mkdtemp(prefix=f".{document_id}.", dir=target_root)
    )
    try:
        (temporary_directory / stored_filename).write_bytes(content)
        serialized = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
        (temporary_directory / "manifest.json").write_text(
            serialized, encoding="utf-8", newline="\n"
        )
        os.replace(temporary_directory, target_directory)
    except OSError as error:
        if target_directory.exists():
            return _validate_existing_import(target_directory, manifest, content), False
        raise ProfileDocumentError(
            f"프로필 문서를 저장할 수 없음: {target_directory}"
        ) from error
    finally:
        if temporary_directory.exists():
            shutil.rmtree(temporary_directory)
    return target_directory / "manifest.json", True


def load_profile_document_import(
    document_id: str,
    directory: str | Path,
) -> tuple[dict[str, Any], bytes]:
    """Load and verify one previously stored private document."""

    normalized_id = _text(document_id, "document_id")
    if _DOCUMENT_ID_PATTERN.fullmatch(normalized_id) is None:
        raise ProfileDocumentError("document_id 형식이 올바르지 않음")
    target_directory = Path(directory) / normalized_id
    manifest_path = target_directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(
            f"저장된 문서 manifest를 읽을 수 없음: {manifest_path}"
        ) from error
    root = _mapping(manifest.get("profile_document"), "profile_document")
    metadata = _mapping(manifest.get("metadata"), "metadata")
    if root.get("document_id") != normalized_id:
        raise ProfileDocumentError("manifest의 document_id가 요청과 일치하지 않음")
    if metadata.get("schema_version") != PROFILE_DOCUMENT_SCHEMA_VERSION:
        raise ProfileDocumentError("현재 버전의 문서 manifest가 아님")
    if metadata.get("git_tracking_allowed") is not False:
        raise ProfileDocumentError("문서 manifest에 Git 제외 표시가 없음")
    stored_filename = _text(
        root.get("stored_filename"), "profile_document.stored_filename"
    )
    if Path(stored_filename).name != stored_filename:
        raise ProfileDocumentError("stored_filename은 파일명이 아니므로 읽을 수 없음")
    stored_path = target_directory / stored_filename
    try:
        content = stored_path.read_bytes()
    except OSError as error:
        raise ProfileDocumentError(
            f"저장된 원본 문서를 읽을 수 없음: {stored_path}"
        ) from error
    expected_size = root.get("size_bytes")
    if isinstance(expected_size, bool) or not isinstance(expected_size, int):
        raise ProfileDocumentError("manifest의 size_bytes가 올바르지 않음")
    if len(content) != expected_size:
        raise ProfileDocumentError("저장된 원본 문서 크기가 manifest와 다름")
    expected_hash = _text(
        root.get("content_sha256"), "profile_document.content_sha256"
    )
    if sha256(content).hexdigest() != expected_hash:
        raise ProfileDocumentError("저장된 원본 문서 해시가 manifest와 다름")
    return manifest, content
