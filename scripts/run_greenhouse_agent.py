from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.config import (  # noqa: E402
    GreenhouseBoardConfigError,
    load_enabled_greenhouse_boards,
)
from career_agent.execution import (  # noqa: E402
    ExecutionLogError,
    build_greenhouse_execution_record,
    save_execution_record,
)
from career_agent.workflows import (  # noqa: E402
    GreenhouseAgentError,
    run_greenhouse_portfolio_agent,
)


DEFAULT_BOARD_CONFIG = REPOSITORY_ROOT / "data/greenhouse_boards.example.json"
DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_SEARCH_PLAN = REPOSITORY_ROOT / "data/job_search_plan.example.json"
DEFAULT_STORE_PATH = REPOSITORY_ROOT / "private-data/discoveries.json"
DEFAULT_RUN_DIRECTORY = REPOSITORY_ROOT / "private-data/agent-runs"
DEFAULT_EXECUTION_DIRECTORY = REPOSITORY_ROOT / "private-data/execution-runs"


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GreenhouseAgentError(f"JSON 파일을 읽을 수 없음: {path}: {error}") from error
    if not isinstance(document, dict):
        raise GreenhouseAgentError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Greenhouse 현재 공고를 발견하고 high 후보 1건만 상세 분석합니다."
    )
    parser.add_argument("--board-config", type=Path, default=DEFAULT_BOARD_CONFIG)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--search-plan", type=Path, default=DEFAULT_SEARCH_PLAN)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--run-directory", type=Path, default=DEFAULT_RUN_DIRECTORY)
    parser.add_argument(
        "--execution-directory", type=Path, default=DEFAULT_EXECUTION_DIRECTORY
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--discovery-only",
        action="store_true",
        help="공식 보드 목록만 갱신하고 상세 공고는 분석하지 않음",
    )
    return parser


def _load_previous_runs(directory: Path) -> tuple[list[dict], dict[str, Path]]:
    if not directory.exists():
        return [], {}
    if not directory.is_dir():
        raise GreenhouseAgentError(f"분석 실행 저장 경로가 디렉터리가 아님: {directory}")

    runs: list[dict] = []
    paths_by_analysis_id: dict[str, Path] = {}
    for path in sorted(directory.glob("*.json")):
        document = _load_json(path)
        runs.append(document)
        analysis_id = _analysis_id(document)
        if isinstance(analysis_id, str) and analysis_id:
            paths_by_analysis_id[analysis_id] = path
    return runs, paths_by_analysis_id


def _analysis_id(document: dict) -> str | None:
    value: object = document
    for key in ("analysis", "match_result", "identity", "analysis_id"):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value if isinstance(value, str) and value else None


def _save_discovery_snapshot(
    result: dict,
    directory: Path,
    *,
    executed_at: datetime,
) -> Path:
    discovery = result.get("discovery")
    if not isinstance(discovery, dict):
        raise GreenhouseAgentError("저장할 Greenhouse 발견 결과가 없음")
    timestamp = executed_at.strftime("%Y%m%dT%H%M%S%f%z")
    path = directory / f"discovery-greenhouse-{timestamp}.json"
    if path.exists():
        raise GreenhouseAgentError(f"발견 스냅샷이 이미 존재함: {path}")
    document = {
        "status": "discovered",
        "workflow": "greenhouse_discovery_snapshot",
        "discovery": discovery,
        "selection": result.get("selection"),
        "analysis": None,
        "reuse": result.get("reuse"),
        "metadata": {
            "created_at": executed_at.isoformat(timespec="seconds"),
            "contains_profile_content": False,
            "contains_job_description_content": False,
        },
    }
    directory.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    execution_time = datetime.now().astimezone()
    try:
        boards = load_enabled_greenhouse_boards(_load_json(args.board_config))
        previous_runs, previous_paths = _load_previous_runs(args.run_directory)
        result = run_greenhouse_portfolio_agent(
            _load_json(args.profile),
            _load_json(args.search_plan),
            args.store,
            boards=boards,
            executed_at=execution_time,
            previous_runs=previous_runs,
            discovery_only=args.discovery_only,
        )
        discovery = result["discovery"]
        print(
            "Greenhouse 보드 조회: "
            f"성공 {discovery['boards_succeeded']}개, 실패 {discovery['boards_failed']}개"
        )
        if discovery["board_errors"]:
            failed_boards = ", ".join(
                error["board_token"] for error in discovery["board_errors"]
            )
            print(f"- 목록 조회 실패 보드: {failed_boards}")
        discovery_snapshot_path: Path | None = None
        if result["status"] in {
            "reused",
            "no_high_candidate",
            "discovered_only",
        }:
            discovery_snapshot_path = _save_discovery_snapshot(
                result,
                args.run_directory,
                executed_at=execution_time,
            )
        if result["status"] == "discovered_only":
            execution_path = save_execution_record(
                build_greenhouse_execution_record(
                    executed_at=execution_time,
                    status="discovered_only",
                    discovery=result["discovery"],
                ),
                args.execution_directory,
            )
            print("Greenhouse 공식 보드 목록 갱신 완료")
            print(f"- 발견 스냅샷: {discovery_snapshot_path}")
            print(f"- 실행 이력: {execution_path}")
            print("주의: 상세 공고 분석은 실행하지 않았습니다.")
            return 0
        if result["status"] == "no_high_candidate":
            execution_path = save_execution_record(
                build_greenhouse_execution_record(
                    executed_at=execution_time,
                    status=result["status"],
                    discovery=result["discovery"],
                ),
                args.execution_directory,
            )
            print("현재 Greenhouse 보드들에 high 후보가 없어 상세 분석을 실행하지 않았습니다.")
            print(f"- 발견 스냅샷: {discovery_snapshot_path}")
            print(f"- 실행 이력: {execution_path}")
            return 0

        analysis_id = result["analysis"]["match_result"]["identity"]["analysis_id"]
        if result["status"] == "reused":
            output_path = previous_paths.get(analysis_id)
            if output_path is None:
                raise GreenhouseAgentError("재사용할 기존 분석 파일 경로를 찾을 수 없음")
        else:
            output_path = args.output or args.run_directory / f"{analysis_id}.json"
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        execution_path = save_execution_record(
            build_greenhouse_execution_record(
                executed_at=execution_time,
                status=result["status"],
                discovery=result["discovery"],
                selection=result["selection"],
                analysis_id=analysis_id,
                analysis_filename=output_path.name,
            ),
            args.execution_directory,
        )
    except (
        GreenhouseAgentError,
        GreenhouseBoardConfigError,
        ExecutionLogError,
        OSError,
        UnicodeError,
    ) as error:
        failure_path = _save_failure_execution(
            args.execution_directory,
            executed_at=execution_time,
            error=error,
        )
        print(f"Greenhouse Agent 실행 실패: {error}", file=sys.stderr)
        if failure_path is not None:
            print(f"실패 실행 이력: {failure_path}", file=sys.stderr)
        return 1

    selection = result["selection"]
    match_result = result["analysis"]["match_result"]
    if result["status"] == "reused":
        print("Greenhouse 자동 발견 완료, 기존 상세 분석 재사용")
        print(f"- 재사용 이유: {result['reuse']['reason']}")
        print(f"- 발견 스냅샷: {discovery_snapshot_path}")
    else:
        print("Greenhouse 자동 발견·분석 완료")
    print(f"- 선택: {selection['company']} / {selection['title']}")
    print(f"- 선택 이유: {selection['reason']}")
    print(f"- 지원 판단: {match_result['application_recommendation']['decision']}")
    print(f"- 지원 시 강조할 강점: {len(match_result['strengths'])}개")
    print(f"- 우선 확인 항목: {min(5, len(match_result['unknowns']))}개")
    print(f"- 우선 학습 과제: {len(match_result['learning_recommendations'])}개")
    print(f"- 포트폴리오 개선 과제: {len(match_result['portfolio_recommendations'])}개")
    print(f"- 저장: {output_path}")
    print(f"- 실행 이력: {execution_path}")
    print("주의: 현재 조회된 high 후보 1건만 분석했으며 합격 가능성 예측이 아닙니다.")
    return 0


def _save_failure_execution(
    directory: Path,
    *,
    executed_at: datetime,
    error: Exception,
) -> Path | None:
    discovery = (
        error.discovery if isinstance(error, GreenhouseAgentError) else None
    )
    try:
        record = build_greenhouse_execution_record(
            executed_at=executed_at,
            status="failed",
            discovery=discovery,
            error=str(error),
        )
        return save_execution_record(record, directory)
    except ExecutionLogError:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
