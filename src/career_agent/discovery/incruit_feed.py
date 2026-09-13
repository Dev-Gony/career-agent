"""Read the official Incruit RSS feed with narrow safety limits."""

from __future__ import annotations

from email.message import Message
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


ALLOWED_HOSTS = {"www.incruit.com"}
ALLOWED_CONTENT_TYPES = {"application/rss+xml", "application/xml", "text/xml"}
DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT_SECONDS = 10.0
USER_AGENT = "career-agent-personal-mvp/0.1"


class IncruitFeedError(RuntimeError):
    """Raised when the official RSS feed cannot be read safely."""


def fetch_incruit_rss(
    feed_url: str,
    *,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> str:
    """Fetch one allowed Incruit RSS URL and return decoded XML text."""

    _validate_feed_url(feed_url)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds는 0보다 커야 함")
    if max_bytes <= 0:
        raise ValueError("max_bytes는 0보다 커야 함")

    request = Request(
        feed_url,
        headers={
            "Accept": "application/rss+xml, application/xml, text/xml",
            "User-Agent": USER_AGENT,
        },
        method="GET",
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            status = getattr(response, "status", None)
            if status != 200:
                raise IncruitFeedError(f"RSS 응답 상태가 200이 아님: {status}")

            final_url = response.geturl()
            _validate_feed_url(final_url)
            _validate_content_type(response.headers)
            _validate_content_length(response.headers, max_bytes)

            payload = response.read(max_bytes + 1)
            if len(payload) > max_bytes:
                raise IncruitFeedError("RSS 응답이 허용 크기를 초과함")
            return _decode_xml(payload, response.headers)
    except HTTPError as error:
        raise IncruitFeedError(f"RSS HTTP 오류: {error.code}") from error
    except URLError as error:
        raise IncruitFeedError(f"RSS 네트워크 오류: {error.reason}") from error
    except TimeoutError as error:
        raise IncruitFeedError("RSS 요청 시간 초과") from error


def _validate_feed_url(value: str) -> None:
    parts = urlsplit(value)
    if parts.scheme != "https":
        raise IncruitFeedError("RSS URL은 HTTPS여야 함")
    if parts.hostname not in ALLOWED_HOSTS:
        raise IncruitFeedError("허용되지 않은 RSS 호스트")
    if parts.username or parts.password:
        raise IncruitFeedError("RSS URL에 인증정보를 포함할 수 없음")


def _validate_content_type(headers: Message) -> None:
    content_type = headers.get_content_type().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise IncruitFeedError(f"RSS XML 콘텐츠 형식이 아님: {content_type}")


def _validate_content_length(headers: Message, max_bytes: int) -> None:
    content_length = headers.get("Content-Length")
    if content_length is None:
        return
    try:
        declared_size = int(content_length)
    except ValueError as error:
        raise IncruitFeedError("Content-Length를 해석할 수 없음") from error
    if declared_size < 0 or declared_size > max_bytes:
        raise IncruitFeedError("RSS 응답이 허용 크기를 초과함")


def _decode_xml(payload: bytes, headers: Message) -> str:
    declared_encoding = _xml_declared_encoding(payload)
    candidates = [headers.get_content_charset(), declared_encoding, "utf-8", "cp949"]
    tried: set[str] = set()
    for encoding in candidates:
        if not encoding:
            continue
        normalized = encoding.lower()
        if normalized in tried:
            continue
        tried.add(normalized)
        try:
            return payload.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    raise IncruitFeedError("RSS 문자 인코딩을 해석할 수 없음")


def _xml_declared_encoding(payload: bytes) -> str | None:
    match = re.search(br"<\?xml[^>]+encoding=[\"']([^\"']+)[\"']", payload[:200], re.I)
    return match.group(1).decode("ascii", errors="ignore") if match else None
