from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    SKILL_ADDITION_REVIEW_DECISIONS,
    ProfileDocumentError,
    build_profile_skill_addition_review,
    load_profile_skill_addition_proposal,
    save_profile_skill_addition_review,
)


DEFAULT_ADDITION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-skill-additions"
DEFAULT_REVIEW_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-skill-addition-reviews"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="완성된 기술 추가안 한 건의 최종 승인 또는 거부를 기록합니다."
    )
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--addition-item-id", required=True)
    parser.add_argument(
        "--decision",
        choices=sorted(SKILL_ADDITION_REVIEW_DECISIONS),
        required=True,
        help="approve=최종 승인, reject=최종 거부",
    )
    parser.add_argument("--notes", help="선택 메모, 최대 1000자")
    parser.add_argument(
        "--addition-directory",
        type=Path,
        default=DEFAULT_ADDITION_DIRECTORY,
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
        addition_proposal = load_profile_skill_addition_proposal(
            args.proposal_id,
            args.addition_directory,
        )
        review = build_profile_skill_addition_review(
            addition_proposal,
            addition_item_id=args.addition_item_id,
            decision=args.decision,
            reviewed_at=datetime.now().astimezone(),
            notes=args.notes,
        )
        output_path = save_profile_skill_addition_review(
            review,
            args.review_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 기술 추가 최종 검토 기록 실패: {error}", file=sys.stderr)
        return 1

    source = review["source"]
    print("프로필 기술 추가 최종 검토 기록 완료")
    print(f"- 기술 추가안: {source['addition_proposal_id']}")
    print(f"- 추가 항목: {source['addition_item_id']}")
    print(f"- 최종 결정: {args.decision}")
    print(f"- 저장: {output_path}")
    print("주의: 제안 기술 내용과 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
