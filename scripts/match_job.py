from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import RequirementMatchError, match_job_requirements  # noqa: E402


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RequirementMatchError(f"JSON 파일을 읽을 수 없습니다: {path}: {error}") from error
    if not isinstance(document, dict):
        raise RequirementMatchError(f"최상위 JSON은 객체여야 합니다: {path}")
    return document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="사용자 프로필과 채용공고의 필수·우대 조건을 비교합니다."
    )
    parser.add_argument(
        "--profile",
        type=Path,
        default=REPOSITORY_ROOT / "data/user_profile.example.json",
    )
    parser.add_argument(
        "--posting",
        type=Path,
        default=REPOSITORY_ROOT / "data/job_posting.example.json",
    )
    return parser


def _print_section(title: str, matches: list[dict]) -> None:
    print(title)
    for item in matches:
        requirement = item["requirement"]
        assessment = item["assessment"]
        print(f"- {requirement['name']}: {assessment['result']}")
        print(f"  공고 근거: {requirement['evidence_text']}")
        print(f"  판단: {assessment['reason']}")
    if not matches:
        print("- 평가할 조건 없음")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    try:
        result = match_job_requirements(
            _load_json(args.profile),
            _load_json(args.posting),
        )
    except RequirementMatchError as error:
        print(f"통합 요구사항 비교 실패: {error}", file=sys.stderr)
        return 1

    print("통합 요구사항 비교 결과")
    print("주의: 지원 가능 조건, 주요 업무와 최종 지원 추천은 아직 평가하지 않습니다.")
    _print_section("필수 조건", result["required_matches"])
    _print_section("우대 조건", result["preferred_matches"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
