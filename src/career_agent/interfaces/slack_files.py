"""Download one authenticated Slack attachment into the private document store."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import re
import tempfile
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from career_agent.profile_input import (
    ProfileDocumentError,
    build_profile_document_import,
    save_profile_document_import,
)

from .slack_events import (
    SlackEventError,
    build_slack_profile_document_reference,
    validate_slack_profile_document_reference,
)


SLACK_FILES_INFO_URL = "https://slack.com/api/files.info"
MAX_SLACK_FILE_INFO_BYTES = 512 * 1024
_SAFE_SLACK_FILE_HOST = "files.slack.com"
_SAFE_SLACK_ERROR_PATTERN = re.compile(r"^[a-z0-9_]{1,80}$")


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _open_without_redirect(request: Request, *, timeout: float) -> Any:
    return build_opener(_NoRedirectHandler()).open(request, timeout=timeout)


def _validate_token(token: Any) -> str:
    if (
        not isinstance(token, str)
        or not token.startswith("xoxb-")
        or len(token) > 500
        or any(character.isspace() for character in token)
    ):
        raise SlackEventError("Slack Bot Token 형식이 올바르지 않음")
    return token


def _validate_timeout(value: Any) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not 0 < value <= 30
    ):
        raise SlackEventError("Slack 파일 요청 제한 시간은 0초 초과 30초 이하여야 함")
    return float(value)


def _response_status(response: Any) -> int | None:
    status = getattr(response, "status", None)
    return status if status is not None else response.getcode()


def _read_response(response: Any, *, max_bytes: int) -> bytes:
    if _response_status(response) != 200:
        raise SlackEventError("Slack 파일 요청의 HTTP 상태가 올바르지 않음")
    content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise SlackEventError("Slack 파일 응답이 허용 크기를 초과함")
    return content


def _files_info(
    file_id: str,
    token: str,
    *,
    open_url: Callable[..., Any],
    timeout_seconds: float,
) -> Mapping[str, Any]:
    request = Request(
        SLACK_FILES_INFO_URL,
        data=urlencode({"file": file_id}).encode("ascii"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "career-agent-personal-mvp/0.1",
        },
        method="POST",
    )
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            if "application/json" not in content_type.casefold():
                raise SlackEventError("Slack files.info 응답이 JSON이 아님")
            raw = _read_response(response, max_bytes=MAX_SLACK_FILE_INFO_BYTES)
    except SlackEventError:
        raise
    except (HTTPError, URLError, OSError) as error:
        raise SlackEventError(
            f"Slack files.info 요청 실패: {type(error).__name__}"
        ) from error
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("Slack files.info JSON을 해석할 수 없음") from error
    if not isinstance(payload, Mapping):
        raise SlackEventError("Slack files.info 최상위 응답이 객체가 아님")
    if payload.get("ok") is not True:
        raw_error = payload.get("error")
        safe_error = (
            raw_error
            if isinstance(raw_error, str)
            and _SAFE_SLACK_ERROR_PATTERN.fullmatch(raw_error) is not None
            else "unknown_error"
        )
        raise SlackEventError(f"Slack 파일 정보 조회 거부: {safe_error}")
    file_object = payload.get("file")
    if not isinstance(file_object, Mapping):
        raise SlackEventError("Slack files.info 응답에 file 객체가 없음")
    return file_object


def _verified_download_url(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise SlackEventError("Slack 비공개 파일 URL 형식이 올바르지 않음")
    if any(character in value for character in "<>|\r\n\t"):
        raise SlackEventError("Slack 비공개 파일 URL에 허용되지 않은 문자가 있음")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise SlackEventError("Slack 비공개 파일 URL 포트가 올바르지 않음") from error
    if (
        parsed.scheme != "https"
        or parsed.hostname != _SAFE_SLACK_FILE_HOST
        or port not in {None, 443}
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/files-pri/")
        or parsed.fragment
    ):
        raise SlackEventError("Slack이 관리하는 비공개 파일 URL만 허용함")
    return value


def _matching_file_reference(
    expected: Mapping[str, Any],
    file_object: Mapping[str, Any],
) -> str:
    actual = build_slack_profile_document_reference(file_object)
    for field in ("file_id", "filename", "extension", "mimetype", "size_bytes"):
        if actual.get(field) != expected.get(field):
            raise SlackEventError(f"Slack 파일 정보가 최초 이벤트와 다름: {field}")
    raw_url = file_object.get("url_private_download") or file_object.get("url_private")
    return _verified_download_url(raw_url)


def _download_file(
    url: str,
    token: str,
    *,
    expected_size: int,
    open_url: Callable[..., Any],
    timeout_seconds: float,
) -> bytes:
    request = Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept-Encoding": "identity",
            "User-Agent": "career-agent-personal-mvp/0.1",
        },
        method="GET",
    )
    try:
        with open_url(request, timeout=timeout_seconds) as response:
            content_encoding = response.headers.get("Content-Encoding", "identity")
            if content_encoding.casefold() not in {"", "identity"}:
                raise SlackEventError("Slack 파일 응답 압축 형식이 허용되지 않음")
            content = _read_response(response, max_bytes=expected_size)
    except SlackEventError:
        raise
    except (HTTPError, URLError, OSError) as error:
        raise SlackEventError(
            f"Slack 비공개 파일 다운로드 실패: {type(error).__name__}"
        ) from error
    if len(content) != expected_size:
        raise SlackEventError("Slack 파일 크기가 메타데이터와 일치하지 않음")
    return content


def import_slack_profile_document(
    reference: Mapping[str, Any],
    *,
    bot_token: str,
    document_kind: str,
    imported_at: datetime,
    directory: str | Path,
    open_url: Callable[..., Any] = _open_without_redirect,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    """Authenticate, download, validate, and privately store one Slack file."""

    validate_slack_profile_document_reference(reference)
    token = _validate_token(bot_token)
    timeout = _validate_timeout(timeout_seconds)
    file_object = _files_info(
        reference["file_id"],
        token,
        open_url=open_url,
        timeout_seconds=timeout,
    )
    download_url = _matching_file_reference(reference, file_object)
    content = _download_file(
        download_url,
        token,
        expected_size=reference["size_bytes"],
        open_url=open_url,
        timeout_seconds=timeout,
    )

    target_root = Path(directory)
    try:
        target_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix=".slack-download-",
            dir=target_root,
        ) as temporary_directory:
            source_path = Path(temporary_directory) / reference["filename"]
            source_path.write_bytes(content)
            manifest, verified_content = build_profile_document_import(
                source_path,
                document_kind=document_kind,
                imported_at=imported_at,
                source_type="slack_attachment",
            )
            manifest_path, created = save_profile_document_import(
                manifest,
                verified_content,
                target_root,
            )
    except (OSError, ProfileDocumentError) as error:
        raise SlackEventError(
            "다운로드한 Slack 문서를 비공개 저장소에 저장할 수 없음"
        ) from error
    root = manifest["profile_document"]
    return {
        "status": "stored" if created else "reused",
        "document_id": root["document_id"],
        "document_kind": root["document_kind"],
        "processing_status": root["processing_status"],
        "manifest_path": manifest_path,
    }
