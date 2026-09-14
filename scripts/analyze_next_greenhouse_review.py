from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.execution import (  # noqa: E402
    ExecutionLogError,
    build_greenhouse_execution_record,
    save_execution_record,
)
from career_agent.review import (  # noqa: E402
    GreenhouseReviewQueueError,
    build_greenhouse_review_analysis_run,
    build_greenhouse_review_queue,
    save_greenhouse_review_analysis_run,
    save_greenhouse_review_queue,
    select_next_greenhouse_review_candidate,
)
from career_agent.workflows import (  # noqa: E402
    GreenhouseAnalysisError,
    analyze_greenhouse_job,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_SEARCH_PLAN = REPOSITORY_ROOT / "data/job_search_plan.example.json"
DEFAULT_RUN_DIRECTORY = REPOSITORY_ROOT / "private-data/agent-runs"
DEFAULT_QUEUE_DIRECTORY = REPOSITORY_ROOT / "private-data/review-queues"
DEFAULT_EXECUTION_DIRECTORY = REPOSITORY_ROOT / "private-data/execution-runs"
DEFAULT_REVIEW_DIRECTORY = REPOSITORY_ROOT / "private-data/human-reviews"


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GreenhouseReviewQueueError(
            f"JSON 파일을 읽을 수 없음: {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise GreenhouseReviewQueueError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _load_documents(directory: Path) -> list[tuple[Path, dict]]:
    if not directory.is_dir():
        raise GreenhouseReviewQueueError(f"디렉터리가 아님: {directory}")
    return [(path, _load_json(path)) for path in sorted(directory.glob("*.json"))]


def _load_optional_documents(directory: Path) -> list[tuple[Path, dict]]:
    if not directory.exists():
        return []
    return _load_documents(directory)


def _created_timestamp(document: dict) -> float:
    root = document.get("review_queue")
    if not isinstance(root, dict):
        return float("-inf")
    value = root.get("created_at")
    if not isinstance(value, str):
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return float("-inf")
    return parsed.timestamp()


def _latest_queue(directory: Path) -> tuple[Path, dict]:
    documents = _load_documents(directory)
    candidates = [
        item for item in documents if _created_timestamp(item[1]) != float("-inf")
    ]
    if not candidates:
        raise GreenhouseReviewQueueError("사용할 Greenhouse 검토 큐가 없음")
    return max(candidates, key=lambda item: _created_timestamp(item[1]))


def _source_run(queue: dict, run_directory: Path) -> tuple[Path, dict]:
    root = queue.get("review_queue")
    if not isinstance(root, dict):
        raise GreenhouseReviewQueueError("review_queue 객체가 필요함")
    filename = root.get("source_run_filename")
    if not isinstance(filename, str) or Path(filename).name != filename:
        raise GreenhouseReviewQueueError(
            "검토 큐의 source_run_filename이 올바르지 않음"
        )
    path = run_directory / filename
    return path, _load_json(path)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="검토 큐의 첫 미분석 Greenhouse 공고 1건만 상세 분석합니다."
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--search-plan", type=Path, default=DEFAULT_SEARCH_PLAN)
    parser.add_argument("--run-directory", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument("--queue-directory", type=Path, default=DEFAULT_QUEUE_DIRECTORY)
    parser.add_argument(
        "--review-directory", type=Path, default=DEFAULT_REVIEW_DIRECTORY
    )
    parser.add_argument(
        "--execution-directory",
        type=Path,
        default=DEFAULT_EXECUTION_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    execution_time = datetime.now().astimezone()
    execution_path: Path | None = None
    try:
        profile = _load_json(args.profile)
        search_plan = _load_json(args.search_plan)
        queue_path, queue = _latest_queue(args.queue_directory)
        candidate = select_next_greenhouse_review_candidate(queue, profile)
        source_path, source_run = _source_run(queue, args.run_directory)
        runs_with_paths = _load_documents(args.run_directory)
        reviews_with_paths = _load_optional_documents(args.review_directory)

        analysis = analyze_greenhouse_job(
            profile,
            board_token=candidate["board_token"],
            job_id=candidate["external_job_id"],
            created_at=execution_time,
        )
        analysis_run = build_greenhouse_review_analysis_run(
            queue,
            candidate,
            analysis,
            queue_filename=queue_path.name,
        )
        updated_queue = build_greenhouse_review_queue(
            source_run["discovery"],
            [*[run for _, run in runs_with_paths], analysis_run],
            profile,
            search_plan,
            created_at=execution_time,
            source_run_filename=source_path.name,
            limit=queue["review_queue"]["limit"],
            human_reviews=[review for _, review in reviews_with_paths],
        )

        analysis_path = save_greenhouse_review_analysis_run(
            analysis_run,
            args.run_directory,
        )
        updated_queue_path = save_greenhouse_review_queue(
            updated_queue,
            args.queue_directory,
        )
        analysis_id = analysis["match_result"]["identity"]["analysis_id"]
        execution_path = save_execution_record(
            build_greenhouse_execution_record(
                executed_at=execution_time,
                status="analyzed",
                selection=analysis_run["selection"],
                analysis_id=analysis_id,
                analysis_filename=analysis_path.name,
            ),
            args.execution_directory,
        )
    except (
        ExecutionLogError,
        GreenhouseAnalysisError,
        GreenhouseReviewQueueError,
        KeyError,
        OSError,
        TypeError,
    ) as error:
        try:
            execution_path = save_execution_record(
                build_greenhouse_execution_record(
                    executed_at=execution_time,
                    status="failed",
                    error=str(error),
                ),
                args.execution_directory,
            )
        except (ExecutionLogError, OSError):
            execution_path = None
        print(f"Greenhouse 다음 검토 공고 분석 실패: {error}", file=sys.stderr)
        if execution_path is not None:
            print(f"- 실패 실행 이력: {execution_path}", file=sys.stderr)
        return 1

    result = analysis["match_result"]
    summary = updated_queue["summary"]["analysis_statuses"]
    print("Greenhouse 다음 검토 공고 1건 분석 완료")
    print(f"- 선택: {candidate['company']} / {candidate['title']}")
    print(f"- 큐 위치: {candidate['position']}")
    print(f"- 지원 판단: {result['application_recommendation']['decision']}")
    print(f"- 추출된 필수 조건: {result['summary']['required']['total']}개")
    print(f"- 추출된 우대 조건: {result['summary']['preferred']['total']}개")
    print(f"- 추출된 주요 업무: {result['summary']['responsibilities']['total']}개")
    if (
        result["summary"]["required"]["total"] == 0
        or result["summary"]["responsibilities"]["total"] == 0
    ):
        print("- 추출 경고: 필수 조건 또는 주요 업무 섹션이 비어 있어 수동 검토 필요")
    print(f"- 우선 확인 항목: {min(5, len(result['unknowns']))}개")
    print(f"- 학습 과제: {len(result['learning_recommendations'])}개")
    print(f"- 포트폴리오 과제: {len(result['portfolio_recommendations'])}개")
    print(f"- 현재 큐 분석 완료: {summary.get('analyzed_current', 0)}개")
    print(f"- 현재 큐 분석 필요: {summary.get('needs_analysis', 0)}개")
    print(
        "- 사용자 검토 완료: "
        f"{updated_queue['summary']['human_review_statuses'].get('reviewed', 0)}개"
    )
    print(f"- 분석 저장: {analysis_path}")
    print(f"- 갱신 큐: {updated_queue_path}")
    print(f"- 실행 이력: {execution_path}")
    print("주의: 사용자 검토 상태는 not_reviewed로 유지됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
