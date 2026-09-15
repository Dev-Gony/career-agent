from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_text_extraction,
    load_profile_document_import,
    save_profile_text_extraction,
)


DEFAULT_DOCUMENT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-documents"
DEFAULT_EXTRACTION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-extractions"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="저장된 경력 문서에서 검토용 프로필 후보를 추출합니다."
    )
    parser.add_argument("--document-id", required=True)
    parser.add_argument(
        "--document-directory",
        type=Path,
        default=DEFAULT_DOCUMENT_DIRECTORY,
    )
    parser.add_argument(
        "--extraction-directory",
        type=Path,
        default=DEFAULT_EXTRACTION_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        manifest, content = load_profile_document_import(
            args.document_id,
            args.document_directory,
        )
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_text_extraction(
            extraction,
            args.extraction_directory,
        )
    except ProfileDocumentError as error:
        print(f"사용자 문서 추출 실패: {error}", file=sys.stderr)
        return 1

    summary = extraction["summary"]
    print("사용자 프로필 후보 추출 완료" if created else "동일 추출 결과 재사용")
    print(f"- 문서 ID: {args.document_id}")
    print(f"- 추출 후보: {summary['candidate_count']}개")
    for section, count in sorted(summary["section_counts"].items()):
        print(f"- {section}: {count}개")
    print(
        "- 제외한 연락처 형태 줄: "
        f"{summary['omitted_sensitive_line_count']}개"
    )
    print(f"- 저장: {output_path}")
    print("주의: 모든 후보는 needs_review이며 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
