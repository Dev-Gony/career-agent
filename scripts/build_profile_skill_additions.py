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
    build_profile_skill_addition_proposal,
    load_profile_skill_mapping_proposal,
    save_profile_skill_addition_proposal,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_MAPPING_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-skill-mappings"
DEFAULT_CONFIRMATION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-skill-confirmations"
)
DEFAULT_ADDITION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-skill-additions"
)


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"JSON 파일을 읽을 수 없음: {path}") from error
    if not isinstance(document, dict):
        raise ProfileDocumentError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _load_optional_confirmations(directory: Path) -> list[dict]:
    if not directory.exists():
        return []
    if not directory.is_dir():
        raise ProfileDocumentError(f"기술 확인 경로가 디렉터리가 아님: {directory}")
    return [_load_json(path) for path in sorted(directory.glob("*.json"))]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="최신 사용자 확인이 있는 새 기술 후보만 완성된 추가안으로 만듭니다."
    )
    parser.add_argument("--mapping-id", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--mapping-directory",
        type=Path,
        default=DEFAULT_MAPPING_DIRECTORY,
    )
    parser.add_argument(
        "--confirmation-directory",
        type=Path,
        default=DEFAULT_CONFIRMATION_DIRECTORY,
    )
    parser.add_argument(
        "--addition-directory",
        type=Path,
        default=DEFAULT_ADDITION_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        mapping_proposal = load_profile_skill_mapping_proposal(
            args.mapping_id,
            args.mapping_directory,
        )
        addition_proposal = build_profile_skill_addition_proposal(
            _load_json(args.profile),
            mapping_proposal,
            _load_optional_confirmations(args.confirmation_directory),
            created_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_skill_addition_proposal(
            addition_proposal,
            args.addition_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 기술 추가안 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = addition_proposal["summary"]
    print("프로필 기술 추가안 생성 완료" if created else "동일 기술 추가안 재사용")
    print(f"- 새 기술 후보: {summary['new_skill_candidate_count']}개")
    print(f"- 세부정보 확인 완료: {summary['confirmed_skill_count']}개")
    print(f"- 미확인: {summary['unconfirmed_skill_count']}개")
    print(f"- 기존 기술 중복: {summary['duplicate_existing_count']}개")
    print(f"- 기술명 분리 필요: {summary['needs_separation_count']}개")
    print(f"- 상태: {addition_proposal['profile_skill_addition']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 완성된 기술은 제안일 뿐 사용자 프로필에 적용하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
