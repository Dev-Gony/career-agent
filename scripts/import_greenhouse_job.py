from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.ingestion import (  # noqa: E402
    GreenhouseJobError,
    build_greenhouse_job_posting,
    fetch_greenhouse_job,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Greenhouse 공개 Job Board API 공고 1건을 구조화합니다."
    )
    parser.add_argument("--board", required=True, help="Greenhouse board token")
    parser.add_argument("--job-id", required=True, help="Greenhouse job ID")
    parser.add_argument(
        "--output",
        type=Path,
        help="출력 JSON 경로, 기본값은 private-data/greenhouse-<board>-<job-id>.json",
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    args = _build_parser().parse_args()
    output_path = args.output or (
        REPOSITORY_ROOT
        / "private-data"
        / f"greenhouse-{args.board}-{args.job_id}.json"
    )
    try:
        job = fetch_greenhouse_job(args.board, args.job_id)
        posting = build_greenhouse_job_posting(job, board_token=args.board)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(posting, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except (GreenhouseJobError, OSError, UnicodeError) as error:
        print(f"Greenhouse 공고 가져오기 실패: {error}", file=sys.stderr)
        return 1

    structured = posting["job_posting"]
    print("Greenhouse 공고 구조화 완료")
    print(f"- 공고: {structured['identity']['title']}")
    print(f"- 회사: {structured['company']['name']}")
    print(f"- 근무지: {structured['location']['region']}")
    print(f"- 주요 업무: {len(structured['responsibilities'])}개")
    print(f"- 필수 조건: {len(structured['requirements'])}개")
    print(f"- 우대 조건: {len(structured['preferred_qualifications'])}개")
    print(f"- 저장: {output_path}")
    print("주의: 규칙 기반 추출 결과이며 원문과 대조가 필요합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
