"""Run one allowlisted Career Agent action for the Slack interface."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping

from .slack_events import SlackEventError


ANALYZE_NEXT_REVIEW_ACTION = "analyze_next_greenhouse_review"
MAX_ACTION_OUTPUT_CHARS = 32 * 1024

_RESULT_LABELS = (
    "선택",
    "지원 판단",
    "우선 확인 항목",
    "학습 과제",
    "포트폴리오 과제",
    "현재 큐 분석 완료",
    "현재 큐 분석 필요",
)


def _safe_slack_text(value: str, *, limit: int = 500) -> str:
    normalized = " ".join(value.split())[:limit]
    return (
        normalized.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _public_success_message(stdout: str) -> str:
    if "Greenhouse 다음 검토 공고 1건 분석 완료" not in stdout.splitlines():
        raise SlackEventError("다음 공고 분석 출력의 완료 표시가 없음")
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.startswith("- "):
            continue
        label, separator, value = line[2:].partition(": ")
        if separator and label in _RESULT_LABELS and value.strip():
            values[label] = _safe_slack_text(value)
    if "선택" not in values or "지원 판단" not in values:
        raise SlackEventError("다음 공고 분석 출력의 필수 요약이 없음")

    lines = [
        "공고 1건 분석을 완료했습니다.",
        f"- 선택: {values['선택']}",
        f"- 지원 판단: {values['지원 판단']}",
    ]
    for label in _RESULT_LABELS[2:]:
        if label in values:
            lines.append(f"- {label}: {values[label]}")
    lines.append("합격 가능성 예측이 아니며, 현재 프로필과 공고의 비교 결과입니다.")
    return "\n".join(lines)


def run_slack_career_action(
    action: str,
    *,
    repository_root: str | Path,
    timeout_seconds: float = 180.0,
    run_process: Callable[..., Any] = subprocess.run,
) -> dict[str, str]:
    """Run one static allowlisted script and return only a safe Slack summary."""

    if action != ANALYZE_NEXT_REVIEW_ACTION:
        raise SlackEventError("허용되지 않은 Slack 내부 동작")
    if not isinstance(timeout_seconds, (int, float)) or not 0 < timeout_seconds <= 300:
        raise SlackEventError("Slack 동작 제한 시간은 0초 초과 300초 이하여야 함")
    root = Path(repository_root).resolve()
    script_path = root / "scripts" / "analyze_next_greenhouse_review.py"
    if not script_path.is_file():
        raise SlackEventError("다음 공고 분석 실행 파일을 찾을 수 없음")
    try:
        completed = run_process(
            [sys.executable, str(script_path)],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "failed",
            "public_message": "공고 분석 제한 시간을 초과했습니다. 로컬 실행 이력을 확인해주세요.",
        }
    except OSError as error:
        raise SlackEventError("다음 공고 분석 프로세스를 시작할 수 없음") from error

    stdout = completed.stdout if isinstance(completed.stdout, str) else ""
    stderr = completed.stderr if isinstance(completed.stderr, str) else ""
    if len(stdout) + len(stderr) > MAX_ACTION_OUTPUT_CHARS:
        return {
            "status": "failed",
            "public_message": "공고 분석 출력이 허용 크기를 초과했습니다. 로컬 실행 이력을 확인해주세요.",
        }
    if completed.returncode != 0:
        return {
            "status": "failed",
            "public_message": "공고 분석에 실패했습니다. 로컬 실행 이력을 확인해주세요.",
        }
    try:
        message = _public_success_message(stdout)
    except SlackEventError:
        return {
            "status": "failed",
            "public_message": "공고 분석은 끝났지만 결과 요약을 만들지 못했습니다. 로컬 실행 이력을 확인해주세요.",
        }
    return {"status": "completed", "public_message": message}
