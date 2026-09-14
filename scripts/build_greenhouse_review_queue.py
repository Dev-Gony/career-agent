from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.review import (  # noqa: E402
    GreenhouseReviewQueueError,
    build_greenhouse_review_queue,
    save_greenhouse_review_queue,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_SEARCH_PLAN = REPOSITORY_ROOT / "data/job_search_plan.example.json"
DEFAULT_RUN_DIRECTORY = REPOSITORY_ROOT / "private-data/agent-runs"
DEFAULT_QUEUE_DIRECTORY = REPOSITORY_ROOT / "private-data/review-queues"


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


def _load_runs(directory: Path) -> list[tuple[Path, dict]]:
    if not directory.is_dir():
        raise GreenhouseReviewQueueError(
            f"분석 실행 저장 경로가 디렉터리가 아님: {directory}"
        )
    return [(path, _load_json(path)) for path in sorted(directory.glob("*.json"))]


def _discovery_time(run: dict) -> float:
    discovery = run.get("discovery")
    if not isinstance(discovery, dict) or not isinstance(
        discovery.get("board_results"), list
    ):
        return float("-inf")
    value = discovery.get("executed_at")
    if not isinstance(value, str):
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return float("-inf")
    return parsed.timestamp()


def _latest_discovery_run(runs: list[tuple[Path, dict]]) -> tuple[Path, dict]:
    candidates = [item for item in runs if _discovery_time(item[1]) != float("-inf")]
    if not candidates:
        raise GreenhouseReviewQueueError(
            "현재 후보 목록이 포함된 Greenhouse 분석 실행 파일이 없음"
        )
    return max(candidates, key=lambda item: _discovery_time(item[1]))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최근 Greenhouse 목록에서 실제 공고 검토 후보를 자동 정렬합니다."
    )
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--search-plan", type=Path, default=DEFAULT_SEARCH_PLAN)
    parser.add_argument("--run-directory", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument("--queue-directory", type=Path, default=DEFAULT_QUEUE_DIRECTORY)
    parser.add_argument("--limit", type=int, default=10)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        runs_with_paths = _load_runs(args.run_directory)
        source_path, source_run = _latest_discovery_run(runs_with_paths)
        queue = build_greenhouse_review_queue(
            source_run["discovery"],
            [run for _, run in runs_with_paths],
            _load_json(args.profile),
            _load_json(args.search_plan),
            created_at=datetime.now().astimezone(),
            limit=args.limit,
        )
        output_path = save_greenhouse_review_queue(queue, args.queue_directory)
    except GreenhouseReviewQueueError as error:
        print(f"Greenhouse 검토 큐 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = queue["summary"]
    print("Greenhouse 실제 공고 검토 큐 생성 완료")
    print(f"- 목록 기준 분석 파일: {source_path}")
    print(f"- 현재 검토 가능 후보: {summary['eligible_current_candidates']}개")
    print(f"- 큐에 포함: {summary['selected_candidates']}개")
    print(
        "- 최신 규칙 분석 완료: "
        f"{summary['analysis_statuses'].get('analyzed_current', 0)}개"
    )
    print(
        "- 상세 분석 필요: "
        f"{summary['analysis_statuses'].get('needs_analysis', 0)}개"
    )
    print(f"- 저장: {output_path}")
    print("주의: 이 큐는 목록 메타데이터만 사용하며 추가 상세 조회를 하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
