"""Build and atomically save minimal Greenhouse execution history."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping


EXECUTION_SCHEMA_VERSION = "1.0"
ALLOWED_STATUSES = {
    "analyzed",
    "reused",
    "no_high_candidate",
    "no_eligible_candidate",
    "failed",
}


class ExecutionLogError(ValueError):
    """Raised when a minimal execution record cannot be built or saved."""


def build_greenhouse_execution_record(
    *,
    executed_at: datetime,
    status: str,
    discovery: Mapping[str, Any] | None = None,
    selection: Mapping[str, Any] | None = None,
    analysis_id: str | None = None,
    analysis_filename: str | None = None,
    error: str | None = None,
) -> dict[str, Any]:
    """Build an audit record without profile or full job content."""

    if executed_at.tzinfo is None or executed_at.utcoffset() is None:
        raise ExecutionLogError("executed_at은 시간대가 포함되어야 함")
    if status not in ALLOWED_STATUSES:
        raise ExecutionLogError(f"지원하지 않는 실행 상태: {status}")
    if status == "failed" and (not isinstance(error, str) or not error.strip()):
        raise ExecutionLogError("실패 실행에는 error 문자열이 필요함")

    execution_id = "greenhouse-run-" + executed_at.strftime("%Y%m%dT%H%M%S%f%z")
    return {
        "execution": {
            "execution_id": execution_id,
            "provider": "greenhouse",
            "status": status,
            "executed_at": executed_at.isoformat(timespec="microseconds"),
        },
        "discovery": _minimal_discovery(discovery),
        "selection": dict(selection) if isinstance(selection, Mapping) else None,
        "analysis_reference": {
            "analysis_id": analysis_id,
            "analysis_filename": analysis_filename,
            "reused": status == "reused",
        }
        if analysis_id
        else None,
        "error": error.strip() if isinstance(error, str) and error.strip() else None,
        "metadata": {
            "schema_version": EXECUTION_SCHEMA_VERSION,
            "contains_profile_content": False,
            "contains_job_description_content": False,
        },
    }


def save_execution_record(
    record: Mapping[str, Any], directory: str | Path
) -> Path:
    """Atomically save one execution record without overwriting another run."""

    execution = record.get("execution")
    if not isinstance(execution, Mapping):
        raise ExecutionLogError("execution 객체가 필요함")
    execution_id = execution.get("execution_id")
    if not isinstance(execution_id, str) or not execution_id.strip():
        raise ExecutionLogError("execution.execution_id 문자열이 필요함")
    target_directory = Path(directory)
    target_directory.mkdir(parents=True, exist_ok=True)
    target_path = target_directory / f"{execution_id}.json"
    if target_path.exists():
        raise ExecutionLogError(f"실행 이력 파일이 이미 존재함: {target_path}")

    serialized = json.dumps(record, ensure_ascii=False, indent=2) + "\n"
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target_directory,
            prefix=f".{execution_id}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_file.write(serialized)
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
            temporary_path = Path(temporary_file.name)
        os.replace(temporary_path, target_path)
    except OSError as error:
        raise ExecutionLogError(f"실행 이력을 저장할 수 없음: {target_path}") from error
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()
    return target_path


def _minimal_discovery(
    discovery: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(discovery, Mapping):
        return None
    attempts = discovery.get("board_attempts", [])
    safe_attempts = [
        dict(attempt) for attempt in attempts if isinstance(attempt, Mapping)
    ] if isinstance(attempts, list) else []
    return {
        "boards_requested": discovery.get("boards_requested"),
        "boards_succeeded": discovery.get("boards_succeeded"),
        "boards_failed": discovery.get("boards_failed"),
        "fetched_records": discovery.get("fetched_records"),
        "board_attempts": safe_attempts,
    }
