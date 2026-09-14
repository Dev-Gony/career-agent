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
    build_profile_skill_mapping_proposal,
    load_profile_update_proposal,
    save_profile_skill_mapping_proposal,
)


DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"
DEFAULT_PROPOSAL_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-update-proposals"
DEFAULT_MAPPING_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-skill-mappings"


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"JSON 파일을 읽을 수 없음: {path}") from error
    if not isinstance(document, dict):
        raise ProfileDocumentError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="승인된 기술 후보를 기존 프로필과 비교해 비파괴 매핑안을 만듭니다."
    )
    parser.add_argument("--proposal-id", required=True)
    parser.add_argument("--profile", type=Path, default=DEFAULT_PROFILE)
    parser.add_argument(
        "--proposal-directory",
        type=Path,
        default=DEFAULT_PROPOSAL_DIRECTORY,
    )
    parser.add_argument(
        "--mapping-directory",
        type=Path,
        default=DEFAULT_MAPPING_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        update_proposal = load_profile_update_proposal(
            args.proposal_id,
            args.proposal_directory,
        )
        mapping_proposal = build_profile_skill_mapping_proposal(
            _load_json(args.profile),
            update_proposal,
            created_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_skill_mapping_proposal(
            mapping_proposal,
            args.mapping_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 기술 매핑안 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = mapping_proposal["summary"]
    print("프로필 기술 매핑안 생성 완료" if created else "동일 기술 매핑안 재사용")
    print(f"- 승인 후보: {summary['approved_candidate_count']}개")
    print(f"- 기술 후보: {summary['skill_candidate_count']}개")
    print(f"- 기존 기술 중복: {summary['duplicate_existing_count']}개")
    print(f"- 세부정보 확인 필요: {summary['needs_details_count']}개")
    print(f"- 기술명 분리 필요: {summary['needs_separation_count']}개")
    print(f"- 다른 프로필 영역: {summary['skipped_non_skill_count']}개")
    print(f"- 상태: {mapping_proposal['profile_skill_mapping']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 사용자 프로필과 기술 숙련도는 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
