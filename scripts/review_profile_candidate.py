from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    CANDIDATE_REVIEW_DECISIONS,
    ProfileDocumentError,
    build_profile_candidate_review,
    load_profile_text_extraction,
    save_profile_candidate_review,
)


DEFAULT_EXTRACTION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-extractions"
DEFAULT_REVIEW_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-candidate-reviews"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="추출된 프로필 후보 한 건에 사용자의 승인 또는 거부를 기록합니다."
    )
    parser.add_argument("--extraction-id", required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument(
        "--decision",
        choices=sorted(CANDIDATE_REVIEW_DECISIONS),
        required=True,
        help="approve=승인, reject=거부",
    )
    parser.add_argument("--notes", help="선택 메모, 최대 1000자")
    parser.add_argument(
        "--extraction-directory",
        type=Path,
        default=DEFAULT_EXTRACTION_DIRECTORY,
    )
    parser.add_argument(
        "--review-directory",
        type=Path,
        default=DEFAULT_REVIEW_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        extraction = load_profile_text_extraction(
            args.extraction_id,
            args.extraction_directory,
        )
        review = build_profile_candidate_review(
            extraction,
            candidate_id=args.candidate_id,
            decision=args.decision,
            reviewed_at=datetime.now().astimezone(),
            notes=args.notes,
        )
        output_path = save_profile_candidate_review(
            review,
            args.review_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 후보 검토 기록 실패: {error}", file=sys.stderr)
        return 1

    source = review["source"]
    print("프로필 후보 검토 기록 완료")
    print(f"- 추출 결과: {source['extraction_id']}")
    print(f"- 후보: {source['candidate_id']}")
    print(f"- 프로필 영역: {source['profile_section']}")
    print(f"- 사용자 결정: {args.decision}")
    print(f"- 저장: {output_path}")
    print("주의: 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
