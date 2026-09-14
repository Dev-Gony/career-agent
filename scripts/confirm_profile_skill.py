from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    SKILL_LEVELS,
    ProfileDocumentError,
    build_profile_skill_confirmation,
    load_profile_skill_mapping_proposal,
    save_profile_skill_confirmation,
)


DEFAULT_MAPPING_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-skill-mappings"
DEFAULT_CONFIRMATION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-skill-confirmations"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="새 기술 후보 한 건의 숙련도와 사용 증거를 명시적으로 기록합니다."
    )
    parser.add_argument("--mapping-id", required=True)
    parser.add_argument("--mapping-item-id", required=True)
    parser.add_argument(
        "--level",
        choices=sorted(SKILL_LEVELS),
        required=True,
        help="none, exposure, learning, basic, project, work 중 하나",
    )
    parser.add_argument(
        "--evidence",
        action="append",
        required=True,
        help="확인된 사용 증거. 여러 개면 인자를 반복함",
    )
    parser.add_argument("--notes", help="선택 메모, 최대 1000자")
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
        confirmation = build_profile_skill_confirmation(
            mapping_proposal,
            mapping_item_id=args.mapping_item_id,
            level=args.level,
            evidence=args.evidence,
            confirmed_at=datetime.now().astimezone(),
            notes=args.notes,
        )
        output_path = save_profile_skill_confirmation(
            confirmation,
            args.confirmation_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 기술 세부정보 기록 실패: {error}", file=sys.stderr)
        return 1

    root = confirmation["profile_skill_confirmation"]
    source = confirmation["source"]
    print("프로필 기술 세부정보 기록 완료")
    print(f"- 기술 매핑: {source['mapping_id']}")
    print(f"- 매핑 항목: {source['mapping_item_id']}")
    print(f"- 확인 숙련도: {root['level']}")
    print(f"- 사용 증거: {len(root['evidence'])}개")
    print(f"- 저장: {output_path}")
    print("주의: 후보 기술명과 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
