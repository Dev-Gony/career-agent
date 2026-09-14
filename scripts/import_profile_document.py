from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    DOCUMENT_KINDS,
    ProfileDocumentError,
    build_profile_document_import,
    save_profile_document_import,
)


DEFAULT_DOCUMENT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-documents"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="사용자 경력 문서 1개를 검증해 비공개 원본 저장소에 보관합니다."
    )
    parser.add_argument("--file", type=Path, required=True)
    parser.add_argument(
        "--kind",
        choices=sorted(DOCUMENT_KINDS),
        required=True,
        help="resume, career_history, portfolio, other 중 선택",
    )
    parser.add_argument(
        "--document-directory",
        type=Path,
        default=DEFAULT_DOCUMENT_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        manifest, content = build_profile_document_import(
            args.file,
            document_kind=args.kind,
            imported_at=datetime.now().astimezone(),
        )
        manifest_path, created = save_profile_document_import(
            manifest,
            content,
            args.document_directory,
        )
    except ProfileDocumentError as error:
        print(f"사용자 문서 가져오기 실패: {error}", file=sys.stderr)
        return 1

    root = manifest["profile_document"]
    print("사용자 문서 비공개 저장 완료" if created else "동일 사용자 문서 재사용")
    print(f"- 문서 종류: {root['document_kind']}")
    print(f"- 파일 형식: {root['document_format']}")
    print(f"- 파일 크기: {root['size_bytes']}바이트")
    print(f"- 처리 상태: {root['processing_status']}")
    print(f"- 메타데이터: {manifest_path}")
    print("주의: 문서 내용은 아직 사용자 프로필로 자동 반영하지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
