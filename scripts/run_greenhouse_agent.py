from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.workflows import (  # noqa: E402
    GreenhouseAgentError,
    run_greenhouse_agent,
)


DEFAULT_BOARD = "sendbird"
DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_SEARCH_PLAN = REPOSITORY_ROOT / "data/job_search_plan.example.json"
DEFAULT_STORE_PATH = REPOSITORY_ROOT / "private-data/discoveries.json"
POLICY_CHECKED_AT = date(2026, 9, 14)


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
    parser.add_argument("--board", default=DEFAULT_BOARD)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument("--search-plan", type=Path, default=DEFAULT_SEARCH_PLAN)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE_PATH)
    parser.add_argument("--output", type=Path)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        result = run_greenhouse_agent(
            _load_json(args.profile),
            _load_json(args.search_plan),
            args.store,
            board_token=args.board,
            policy_checked_at=POLICY_CHECKED_AT,
        )
        if result["status"] == "no_high_candidate":
            print("현재 Greenhouse 보드에 high 후보가 없어 상세 분석을 실행하지 않았습니다.")
            return 0

        analysis_id = result["analysis"]["match_result"]["identity"]["analysis_id"]
        output_path = args.output or (
            REPOSITORY_ROOT / "private-data" / "agent-runs" / f"{analysis_id}.json"
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (GreenhouseAgentError, OSError, UnicodeError) as error:
        print(f"Greenhouse Agent 실행 실패: {error}", file=sys.stderr)
        return 1

    selection = result["selection"]
    match_result = result["analysis"]["match_result"]
    print("Greenhouse 자동 발견·분석 완료")
    print(f"- 선택: {selection['company']} / {selection['title']}")
    print(f"- 선택 이유: {selection['reason']}")
    print(f"- 지원 판단: {match_result['application_recommendation']['decision']}")
    print(f"- 지원 시 강조할 강점: {len(match_result['strengths'])}개")
    print(f"- 우선 확인 항목: {min(5, len(match_result['unknowns']))}개")
    print(f"- 저장: {output_path}")
    print("주의: 현재 조회된 high 후보 1건만 분석했으며 합격 가능성 예측이 아닙니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
