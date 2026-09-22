"""Run one allowlisted Career Agent action for the Slack interface."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any, Callable, Mapping
from urllib.parse import urlsplit

from .slack_events import SlackEventError


ANALYZE_NEXT_REVIEW_ACTION = "analyze_next_greenhouse_review"
MAX_ACTION_OUTPUT_CHARS = 32 * 1024
MAX_ANALYSIS_FILE_BYTES = 2 * 1024 * 1024
NO_CANDIDATE_MARKER = "Greenhouse 다음 검토 공고 없음"
STALE_QUEUE_MARKERS = (
    "검토 큐를 다시 생성해야 함",
    "현재 스키마 버전의 검토 큐가 아님",
    "검색 계획 식별 정보가 없는 검토 큐는 재사용할 수 없음",
    "검색 계획 내용 지문이 없는 검토 큐는 재사용할 수 없음",
    "검토 큐의 검색 계획 ID가 현재 계획과 다름",
    "검토 큐의 검색 계획 내용이 현재 계획과 다름",
)

_RESULT_LABELS = (
    "선택",
    "지원 판단",
    "우선 확인 항목",
    "학습 과제",
    "포트폴리오 과제",
    "현재 큐 분석 완료",
    "현재 큐 분석 필요",
)

_INFORMATION_LEVEL_LABELS = {
    "sufficient": "충분",
    "partial": "일부 부족",
    "insufficient": "부족",
}
_POSTING_FIELD_LABELS = {
    "company": "회사명",
    "position": "직무명",
    "responsibilities": "주요 업무",
    "required_qualifications": "필수 조건",
    "preferred_qualifications": "우대 조건",
    "experience": "요구 경력",
    "employment": "고용 형태",
    "location": "근무 지역",
}
_MATCH_SECTION_LABELS = {
    "requirements": "필수 조건",
    "responsibilities": "주요 업무",
    "preferred_qualifications": "우대 조건",
}


def _safe_slack_text(value: str, *, limit: int = 500) -> str:
    normalized = " ".join(value.split())[:limit]
    return (
        normalized.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SlackEventError(f"{name} 객체가 필요함")
    return value


def _text(value: Any, name: str, *, limit: int = 500) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SlackEventError(f"{name} 문자열이 필요함")
    return _safe_slack_text(value, limit=limit)


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise SlackEventError(f"{name} 문자열 배열이 필요함")
    return [item for item in value if item.strip()]


def _safe_https_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise SlackEventError("공고 원문 URL 형식이 올바르지 않음")
    if any(character in value for character in "<>|\r\n\t"):
        raise SlackEventError("공고 원문 URL에 허용되지 않은 문자가 있음")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise SlackEventError("공고 원문 URL은 인증정보가 없는 HTTPS여야 함")
    return value


def _analysis_path(stdout: str, repository_root: Path) -> Path:
    paths = [
        line.removeprefix("- 분석 저장: ").strip()
        for line in stdout.splitlines()
        if line.startswith("- 분석 저장: ")
    ]
    if len(paths) != 1 or not paths[0]:
        raise SlackEventError("다음 공고 분석 파일 경로가 한 개가 아님")
    raw_path = Path(paths[0])
    path = (raw_path if raw_path.is_absolute() else repository_root / raw_path).resolve()
    allowed_directory = (repository_root / "private-data" / "agent-runs").resolve()
    if not path.is_relative_to(allowed_directory) or path.suffix.casefold() != ".json":
        raise SlackEventError("다음 공고 분석 파일이 허용 경로 밖에 있음")
    try:
        if path.stat().st_size > MAX_ANALYSIS_FILE_BYTES:
            raise SlackEventError("다음 공고 분석 파일이 너무 큼")
    except OSError as error:
        raise SlackEventError("다음 공고 분석 파일을 확인할 수 없음") from error
    return path


def _load_analysis(stdout: str, repository_root: Path) -> Mapping[str, Any]:
    path = _analysis_path(stdout, repository_root)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("다음 공고 분석 파일을 읽을 수 없음") from error
    root = _mapping(document, "분석 파일")
    if root.get("status") != "analyzed" or root.get("workflow") != "greenhouse_review_queue":
        raise SlackEventError("현재 검토 큐 분석 결과가 아님")
    return root


def _result_values(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in stdout.splitlines():
        if not line.startswith("- "):
            continue
        label, separator, value = line[2:].partition(": ")
        if separator and label in _RESULT_LABELS and value.strip():
            values[label] = _safe_slack_text(value)
    return values


def _summary_values(stdout: str) -> dict[str, str]:
    if "Greenhouse 다음 검토 공고 1건 분석 완료" not in stdout.splitlines():
        raise SlackEventError("다음 공고 분석 출력의 완료 표시가 없음")
    return _result_values(stdout)


def _public_no_candidate_message(
    stdout: str,
    *,
    source_refreshed: bool | None = None,
) -> str:
    if NO_CANDIDATE_MARKER not in stdout.splitlines():
        raise SlackEventError("다음 공고 없음 출력의 완료 표시가 없음")
    values = _result_values(stdout)
    analyzed = values.get("현재 큐 분석 완료")
    remaining = values.get("현재 큐 분석 필요")
    if analyzed is None or remaining is None:
        raise SlackEventError("다음 공고 없음 출력의 큐 상태가 없음")
    lines = [
            "*현재 조건에 맞는 새 공고가 없습니다.*",
            (
                "현재 등록된 공식 채용 소스에서 프로필 직무 근거와 "
                "지역·고용 조건을 함께 만족하는 미분석 공고를 찾지 못했습니다."
            ),
            "",
            "*검토 큐*",
            f"- 분석 완료: {analyzed}",
            f"- 미분석이지만 조건 불일치: {remaining}",
            "- 현재 분석 가능: 0",
            "",
        ]
    if source_refreshed is True:
        lines.append("공식 채용 소스를 방금 갱신했지만 새 분석 후보가 없습니다.")
    elif source_refreshed is False:
        lines.append(
            "현재 큐에는 후보가 없고 공식 채용 소스 갱신도 완료하지 못했습니다."
        )
    else:
        lines.append("새 공고 목록이 갱신되면 다시 확인할 수 있습니다.")
    return "\n".join(lines)


def _strength_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SlackEventError("strengths 배열이 필요함")
    lines: list[str] = []
    for index, raw_item in enumerate(value[:2]):
        item = _mapping(raw_item, f"strengths[{index}]")
        title = _text(item.get("title"), f"strengths[{index}].title", limit=180)
        evidence = _strings(item.get("evidence"), f"strengths[{index}].evidence")
        evidence_text = ", ".join(_safe_slack_text(entry, limit=100) for entry in evidence[:2])
        suffix = f" (근거: {evidence_text})" if evidence_text else ""
        lines.append(f"- {title}{suffix}")
    return lines


def _gap_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SlackEventError("gaps 배열이 필요함")
    lines: list[str] = []
    for index, raw_item in enumerate(value[:2]):
        item = _mapping(raw_item, f"gaps[{index}]")
        name = _text(item.get("name"), f"gaps[{index}].name", limit=180)
        reason = _text(item.get("reason"), f"gaps[{index}].reason", limit=220)
        lines.append(f"- {name}: {reason}")
    return lines


def _unknown_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SlackEventError("unknowns 배열이 필요함")
    lines: list[str] = []
    for index, raw_item in enumerate(value[:3], start=1):
        item = _mapping(raw_item, f"unknowns[{index - 1}]")
        question = _text(
            item.get("question"),
            f"unknowns[{index - 1}].question",
            limit=240,
        )
        lines.append(f"{index}. {question}")
    return lines


def _posting_information(value: Any) -> tuple[str, list[str]]:
    information = _mapping(value, "job_posting_information")
    level = information.get("level")
    if level not in _INFORMATION_LEVEL_LABELS:
        raise SlackEventError("공고 정보 충분도 값을 해석할 수 없음")
    missing = _strings(
        information.get("missing_fields"),
        "job_posting_information.missing_fields",
    )
    missing_labels = [
        _POSTING_FIELD_LABELS.get(field, _safe_slack_text(field, limit=80))
        for field in missing[:5]
    ]
    return f"{_INFORMATION_LEVEL_LABELS[level]} ({level})", missing_labels


def _confirmed_match_lines(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise SlackEventError("confirmed_matches 배열이 필요함")
    lines: list[str] = []
    for index, raw_item in enumerate(value[:3]):
        item = _mapping(raw_item, f"confirmed_matches[{index}]")
        section = _text(
            item.get("source_section"),
            f"confirmed_matches[{index}].source_section",
            limit=80,
        )
        name = _text(item.get("name"), f"confirmed_matches[{index}].name", limit=180)
        evidence_items = item.get("user_evidence")
        if not isinstance(evidence_items, list) or not evidence_items:
            raise SlackEventError("확인된 일치에 사용자 근거가 필요함")
        evidence = _mapping(
            evidence_items[0],
            f"confirmed_matches[{index}].user_evidence[0]",
        )
        detail = _text(
            evidence.get("detail"),
            f"confirmed_matches[{index}].user_evidence[0].detail",
            limit=140,
        )
        section_label = _MATCH_SECTION_LABELS.get(section, section)
        lines.append(f"- [{section_label}] {name} (근거: {detail})")
    return lines


def _public_success_message(
    stdout: str,
    analysis_document: Mapping[str, Any],
) -> str:
    values = _summary_values(stdout)
    selection = _mapping(analysis_document.get("selection"), "selection")
    analysis = _mapping(analysis_document.get("analysis"), "analysis")
    posting = _mapping(analysis.get("job_posting"), "analysis.job_posting")
    source = _mapping(posting.get("source"), "analysis.job_posting.source")
    match_result = _mapping(analysis.get("match_result"), "analysis.match_result")
    recommendation = _mapping(
        match_result.get("application_recommendation"),
        "analysis.match_result.application_recommendation",
    )
    information_level, missing_posting_fields = _posting_information(
        match_result.get("job_posting_information")
    )

    company = _text(selection.get("company"), "selection.company", limit=150)
    title = _text(selection.get("title"), "selection.title", limit=250)
    source_url = _safe_https_url(source.get("url"))
    if selection.get("source_url") != source.get("url"):
        raise SlackEventError("선택 공고와 분석 공고의 원문 URL이 일치하지 않음")
    decision = _text(recommendation.get("decision"), "recommendation.decision", limit=100)
    status = _text(recommendation.get("status"), "recommendation.status", limit=30)
    if status not in {"RECOMMEND", "HOLD", "NOT_RECOMMEND"}:
        raise SlackEventError("지원 추천 상태를 해석할 수 없음")
    reasons = _strings(recommendation.get("reasons"), "recommendation.reasons")
    next_steps = _strings(
        recommendation.get("next_steps"),
        "recommendation.next_steps",
    )
    confirmed_matches = _confirmed_match_lines(match_result.get("confirmed_matches"))
    gaps = _gap_lines(match_result.get("gaps"))
    unknowns = _unknown_lines(match_result.get("unknowns"))

    lines = [
        "*공고 분석 완료*",
        f"*{company}*",
        title,
        f"<{source_url}|공고 원문 보기>",
        "",
        f"*공고 정보 수준: {information_level}*",
        f"*최종 추천: {status}*",
        f"- 판단 설명: {decision}",
    ]
    lines.extend(
        f"- {_safe_slack_text(reason, limit=300)}"
        for reason in reasons[:2]
    )
    lines.extend(["", "*확인된 일치*"])
    lines.extend(confirmed_matches or ["- 확인된 일치 항목이 없습니다."])
    if gaps:
        lines.extend(["", "*확인된 부족 또는 불일치*"])
        lines.extend(gaps)
    if missing_posting_fields:
        lines.extend(["", "*공고에서 확인할 수 없는 정보*"])
        lines.extend(f"- {field}" for field in missing_posting_fields)
    lines.extend(["", "*비교를 위해 추가 확인할 정보*"])
    lines.extend(unknowns or ["- 추가 확인 항목이 없습니다."])
    if next_steps:
        lines.extend(
            ["", "*다음 행동*", f"- {_safe_slack_text(next_steps[0], limit=250)}"]
        )
    analyzed = values.get("현재 큐 분석 완료")
    remaining = values.get("현재 큐 분석 필요")
    if analyzed or remaining:
        lines.extend(
            [
                "",
                "*검토 큐*",
                f"- 분석 완료: {analyzed or '확인 불가'} / 분석 필요: {remaining or '확인 불가'}",
            ]
        )
    lines.extend(
        [
            "",
            "_합격 가능성 예측이 아니라 현재 프로필과 공고의 비교 결과입니다._",
        ]
    )
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

    def run_script(path: Path, *arguments: str) -> Any:
        return run_process(
            [sys.executable, str(path), *arguments],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=float(timeout_seconds),
            check=False,
        )

    try:
        source_refreshed: bool | None = None
        completed = run_script(script_path)
        initial_stderr = (
            completed.stderr if isinstance(completed.stderr, str) else ""
        )
        if completed.returncode != 0 and any(
            marker in initial_stderr for marker in STALE_QUEUE_MARKERS
        ):
            queue_script = root / "scripts" / "build_greenhouse_review_queue.py"
            if not queue_script.is_file():
                raise SlackEventError("검토 큐 생성 실행 파일을 찾을 수 없음")
            rebuilt = run_script(queue_script)
            rebuild_output = "".join(
                value
                for value in (rebuilt.stdout, rebuilt.stderr)
                if isinstance(value, str)
            )
            if (
                rebuilt.returncode != 0
                or len(rebuild_output) > MAX_ACTION_OUTPUT_CHARS
            ):
                return {
                    "status": "failed",
                    "public_message": "공고 검토 목록을 갱신하지 못했습니다. 로컬 실행 이력을 확인해주세요.",
                }
            completed = run_script(script_path)

        current_stdout = (
            completed.stdout if isinstance(completed.stdout, str) else ""
        )
        if completed.returncode == 0 and NO_CANDIDATE_MARKER in current_stdout.splitlines():
            discovery_script = root / "scripts" / "run_greenhouse_agent.py"
            queue_script = root / "scripts" / "build_greenhouse_review_queue.py"
            if not discovery_script.is_file() or not queue_script.is_file():
                raise SlackEventError("공식 공고 갱신 실행 파일을 찾을 수 없음")
            refreshed = run_script(discovery_script, "--discovery-only")
            refresh_output = "".join(
                value
                for value in (refreshed.stdout, refreshed.stderr)
                if isinstance(value, str)
            )
            if refreshed.returncode != 0 or len(refresh_output) > MAX_ACTION_OUTPUT_CHARS:
                return {
                    "status": "no_candidate",
                    "public_message": _public_no_candidate_message(
                        current_stdout,
                        source_refreshed=False,
                    ),
                }
            rebuilt = run_script(queue_script)
            rebuild_output = "".join(
                value
                for value in (rebuilt.stdout, rebuilt.stderr)
                if isinstance(value, str)
            )
            if rebuilt.returncode != 0 or len(rebuild_output) > MAX_ACTION_OUTPUT_CHARS:
                return {
                    "status": "no_candidate",
                    "public_message": _public_no_candidate_message(
                        current_stdout,
                        source_refreshed=False,
                    ),
                }
            completed = run_script(script_path)
            source_refreshed = True
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
        if NO_CANDIDATE_MARKER in stdout.splitlines():
            return {
                "status": "no_candidate",
                "public_message": _public_no_candidate_message(
                    stdout,
                    source_refreshed=source_refreshed,
                ),
            }
        analysis_document = _load_analysis(stdout, root)
        message = _public_success_message(stdout, analysis_document)
    except SlackEventError:
        return {
            "status": "failed",
            "public_message": "공고 분석은 끝났지만 결과 요약을 만들지 못했습니다. 로컬 실행 이력을 확인해주세요.",
        }
    return {"status": "completed", "public_message": message}
