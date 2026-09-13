from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.workflows import (  # noqa: E402
    GreenhouseAnalysisError,
    analyze_greenhouse_job,
)


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GreenhouseAnalysisError(f"JSON 파일을 읽을 수 없음: {path}: {error}") from error
    if not isinstance(document, dict):
        raise GreenhouseAnalysisError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Greenhouse 공개 공고 1건을 가져와 프로필과 비교하고 저장합니다."
    )
    parser.add_argument("--board", required=True, help="Greenhouse board token")
    parser.add_argument("--job-id", required=True, help="Greenhouse job ID")
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPOSITORY_ROOT / "data/user_profile.example.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="출력 경로, 기본값은 private-data/analysis-greenhouse-<board>-<job-id>.json",
    )
    return parser


def _print_review_priorities(result: dict, *, limit: int = 5) -> None:
    unknowns = result["unknowns"]
    print("우선 확인할 항목")
    for item in unknowns[:limit]:
        print(f"- [{item['impact']}] {item['subject']}")
        print(f"  확인: {item['question']}")
    if not unknowns:
        print("- 없음")
    elif len(unknowns) > limit:
        print(f"- 나머지 {len(unknowns) - limit}개는 저장된 JSON에서 확인")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    output_path = args.output or (
        REPOSITORY_ROOT
        / "private-data"
        / f"analysis-greenhouse-{args.board}-{args.job_id}.json"
    )
    try:
        packaged_result = analyze_greenhouse_job(
            _load_json(args.profile),
            board_token=args.board,
            job_id=args.job_id,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(packaged_result, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (GreenhouseAnalysisError, OSError, UnicodeError) as error:
        print(f"Greenhouse 공고 분석 실패: {error}", file=sys.stderr)
        return 1

    posting = packaged_result["job_posting"]
    result = packaged_result["match_result"]
    recommendation = result["application_recommendation"]
    print("Greenhouse 실공고 분석 완료")
    print(f"- 공고: {posting['company']['name']} / {posting['identity']['title']}")
    print(f"- 지원 판단: {recommendation['decision']}")
    print(f"- 지원 가능 조건: {result['eligibility']['status']}")
    print(f"- 필수 조건 미확인: {result['summary']['required']['unknown']}개")
    print(f"- 지원 시 강조할 강점: {len(result['strengths'])}개")
    print(f"- 추가 확인 항목: {len(result['unknowns'])}개")
    print(f"- 저장: {output_path}")
    _print_review_priorities(result)
    print("주의: 현재 프로필과 규칙 기반 비교 결과이며 합격 가능성 예측이 아닙니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
