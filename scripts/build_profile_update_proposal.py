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
    build_profile_update_proposal,
    load_profile_text_extraction,
    save_profile_update_proposal,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_EXTRACTION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-extractions"
DEFAULT_REVIEW_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-candidate-reviews"
)
DEFAULT_PROPOSAL_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-update-proposals"
)


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"JSON 파일을 읽을 수 없음: {path}") from error
    if not isinstance(document, dict):
        raise ProfileDocumentError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _load_optional_reviews(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ProfileDocumentError(f"후보 검토 경로가 디렉터리가 아님: {directory}")
    return [_load_json(path) for path in sorted(directory.glob("*.json"))]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최종 승인된 문서 후보만 포함하는 프로필 갱신안을 만듭니다."
    )
    parser.add_argument("--extraction-id", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
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
        extraction = load_profile_text_extraction(
            args.extraction_id,
            args.extraction_directory,
        )
        proposal = build_profile_update_proposal(
            _load_json(args.profile),
            extraction,
            _load_optional_reviews(args.review_directory),
            created_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_update_proposal(
            proposal,
            args.proposal_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 갱신안 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = proposal["summary"]
    print("프로필 갱신안 생성 완료" if created else "동일 프로필 갱신안 재사용")
    print(f"- 전체 후보: {summary['candidate_count']}개")
    print(f"- 검토 완료: {summary['reviewed_count']}개")
    print(f"- 최종 승인: {summary['approved_count']}개")
    print(f"- 최종 거부: {summary['rejected_count']}개")
    print(f"- 미검토: {summary['unreviewed_count']}개")
    print(f"- 상태: {proposal['profile_update_proposal']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 기존 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
