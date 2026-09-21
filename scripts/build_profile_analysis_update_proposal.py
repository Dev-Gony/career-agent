from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_update_proposal,
    load_profile_analysis_draft,
    save_profile_analysis_update_proposal,
    select_latest_profile_analysis_reviews,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_DRAFT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-drafts"
DEFAULT_REVIEW_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-reviews"
DEFAULT_PROPOSAL_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-update-proposals"
)


def _load_profile(path: Path) -> dict:
    try:
        profile = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError("기준 사용자 프로필을 읽을 수 없음") from error
    if not isinstance(profile, dict):
        raise ProfileDocumentError("기준 사용자 프로필 최상위 JSON은 객체여야 함")
    return profile


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="승인된 분석 항목으로 비파괴 프로필 변경 제안을 만듭니다."
    )
    parser.add_argument("--draft-id", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
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
    parser.add_argument(
        "--proposal-directory",
        type=Path,
        default=DEFAULT_PROPOSAL_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        draft = load_profile_analysis_draft(args.draft_id, args.draft_directory)
        latest_reviews = select_latest_profile_analysis_reviews(
            args.draft_id,
            args.review_directory,
        )
        proposal = build_profile_analysis_update_proposal(
            _load_profile(args.profile),
            draft,
            latest_reviews.values(),
            created_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_analysis_update_proposal(
            proposal,
            args.proposal_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 분석 변경 제안 생성 실패: {error}", file=sys.stderr)
        return 1

    root = proposal["profile_analysis_update_proposal"]
    summary = proposal["summary"]
    excluded = proposal["excluded"]
    print("프로필 분석 변경 제안 생성 완료" if created else "동일 변경 제안 재사용")
    print(f"- 분석 항목: {summary['analyzed_item_count']}개")
    print(f"- 검토 완료: {summary['reviewed_count']}개")
    print(f"- 승인된 프로필 근거: {summary['approved_profile_fact_count']}개")
    print(f"- 변경 제안: {summary['proposed_change_count']}개")
    print(f"- 추가 확인 질문 제외: {excluded['approved_unknown_count']}개")
    print(f"- 중복 기술 근거 제외: {excluded['duplicate_skill_evidence_count']}개")
    print(f"- 상태: {root['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 기존 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
