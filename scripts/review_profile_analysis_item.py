from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    PROFILE_ANALYSIS_ITEM_TYPES,
    PROFILE_ANALYSIS_REVIEW_DECISIONS,
    ProfileDocumentError,
    build_profile_analysis_review,
    load_profile_analysis_draft,
    save_profile_analysis_review,
)


DEFAULT_DRAFT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-drafts"
DEFAULT_REVIEW_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-reviews"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="프로필 분석 초안의 항목 한 건에 승인 또는 거부를 기록합니다."
    )
    parser.add_argument("--draft-id", required=True)
    parser.add_argument(
        "--item-type",
        choices=sorted(PROFILE_ANALYSIS_ITEM_TYPES),
        required=True,
    )
    parser.add_argument("--item-position", type=int, required=True)
    parser.add_argument(
        "--decision",
        choices=sorted(PROFILE_ANALYSIS_REVIEW_DECISIONS),
        required=True,
        help="approve=승인, reject=거부",
    )
    parser.add_argument("--notes", help="선택 메모, 최대 1000자")
    parser.add_argument(
        "--draft-directory",
        type=Path,
        default=DEFAULT_DRAFT_DIRECTORY,
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
        draft = load_profile_analysis_draft(args.draft_id, args.draft_directory)
        review = build_profile_analysis_review(
            draft,
            item_type=args.item_type,
            item_position=args.item_position,
            decision=args.decision,
            reviewed_at=datetime.now().astimezone(),
            notes=args.notes,
        )
        output_path = save_profile_analysis_review(
            review,
            args.review_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 분석 항목 검토 기록 실패: {error}", file=sys.stderr)
        return 1

    print("프로필 분석 항목 검토 기록 완료")
    print(f"- 항목 종류: {args.item_type}")
    print(f"- 항목 순번: {args.item_position}")
    print(f"- 사용자 결정: {args.decision}")
    print(f"- 저장: {output_path}")
    print("주의: 분석 문장과 후보 원문은 복제하지 않았습니다.")
    print("주의: 개인 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
