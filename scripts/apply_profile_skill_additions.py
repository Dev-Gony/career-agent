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
    build_profile_skill_application,
    load_profile_skill_addition_proposal,
    save_profile_skill_application,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_ADDITION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-skill-additions"
DEFAULT_REVIEW_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-skill-addition-reviews"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-applications"


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"JSON 파일을 읽을 수 없음: {path}") from error
    if not isinstance(value, dict):
        raise ProfileDocumentError(f"최상위 JSON은 객체여야 함: {path}")
    return value


def _load_optional_reviews(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ProfileDocumentError(f"최종 검토 경로가 디렉터리가 아님: {directory}")
    return [_load_json(path) for path in sorted(directory.glob("*.json"))]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최종 승인된 기술만 원본을 덮어쓰지 않고 새 프로필 버전에 적용합니다."
    )
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
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
    parser.add_argument(
        "--output-directory",
        type=Path,
        default=DEFAULT_OUTPUT_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        proposal = load_profile_skill_addition_proposal(
            args.proposal_id,
            args.addition_directory,
        )
        application, updated_profile = build_profile_skill_application(
            _load_json(args.profile),
            proposal,
            _load_optional_reviews(args.review_directory),
            applied_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_skill_application(
            application,
            updated_profile,
            args.output_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 기술 적용 실패: {error}", file=sys.stderr)
        return 1

    summary = application["summary"]
    print("프로필 기술 적용 기록 생성 완료" if created else "동일 적용 기록 재사용")
    print(f"- 추가안 항목: {summary['addition_count']}개")
    print(f"- 최종 검토 완료: {summary['reviewed_count']}개")
    print(f"- 최종 승인: {summary['approved_count']}개")
    print(f"- 실제 적용: {summary['applied_count']}개")
    print(f"- 상태: {application['profile_skill_application']['status']}")
    print(f"- 적용 기록: {output_path}")
    if updated_profile is not None:
        print(f"- 새 프로필: {output_path.parent / 'profile.json'}")
    else:
        print("- 새 프로필: 생성하지 않음")
    print("주의: 기준 프로필 원본 파일은 수정하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
