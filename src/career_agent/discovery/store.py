"""Local JSON storage for deduplicating discovered job records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import json
import os
from pathlib import Path
import tempfile
from typing import Any


STORE_SCHEMA_VERSION = "1.0"


class DiscoveryStoreError(ValueError):
    """Raised when discovery records cannot be safely loaded or stored."""


def load_discovery_records(store_path: str | Path) -> list[dict[str, Any]]:
    """Load validated discovery records from a local JSON store."""

    return _load_records(Path(store_path))


def merge_discovery_records(
    records: Iterable[Mapping[str, Any]], store_path: str | Path
) -> dict[str, Any]:
    """Persist unseen records and report records already present in the store."""

    path = Path(store_path)
    stored_records = _load_records(path)
    seen_keys = {_record_key(record) for record in stored_records}

    new_records: list[dict[str, Any]] = []
    duplicate_keys: list[str] = []
    for record in records:
        key = _record_key(record)
        if key in seen_keys:
            duplicate_keys.append(key)
            continue
        copied_record = dict(record)
        new_records.append(copied_record)
        seen_keys.add(key)

    if new_records:
        stored_records.extend(new_records)
        _write_records(path, stored_records)

    return {
        "new_records": new_records,
        "duplicate_keys": duplicate_keys,
        "total_records": len(stored_records),
    }


def _load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    if not path.is_file():
        raise DiscoveryStoreError(f"저장 경로가 파일이 아님: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise DiscoveryStoreError(f"발견 저장 파일을 읽을 수 없음: {path}") from error

    if not isinstance(payload, dict):
        raise DiscoveryStoreError("발견 저장 파일의 최상위 값은 객체여야 함")
    if payload.get("schema_version") != STORE_SCHEMA_VERSION:
        raise DiscoveryStoreError("지원하지 않는 발견 저장 스키마 버전")

    records = payload.get("records")
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise DiscoveryStoreError("발견 저장 파일의 records는 객체 배열이어야 함")

    keys = [_record_key(record) for record in records]
    if len(keys) != len(set(keys)):
        raise DiscoveryStoreError("발견 저장 파일에 중복 키가 있음")
    return records


def _record_key(record: Mapping[str, Any]) -> str:
    try:
        key = record["deduplication"]["key"]
    except (KeyError, TypeError) as error:
        raise DiscoveryStoreError("발견 레코드에 deduplication.key가 없음") from error
    if not isinstance(key, str) or not key.strip():
        raise DiscoveryStoreError("deduplication.key는 비어 있지 않은 문자열이어야 함")
    return key


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": STORE_SCHEMA_VERSION,
        "records": records,
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, path)
    except OSError as error:
        raise DiscoveryStoreError(f"발견 저장 파일을 쓸 수 없음: {path}") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
