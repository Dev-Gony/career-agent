from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    GeminiDevelopmentProfileAnalysisProvider,
    ProfileDocumentError,
    analyze_profile_extraction,
    build_profile_document_import,
    build_profile_text_extraction,
    load_gemini_api_key,
    save_profile_analysis_draft,
)


PUBLIC_SYNTHETIC_DOCUMENT = REPOSITORY_ROOT / "data/profile_document.example.md"
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_DRAFT_DIRECTORY = REPOSITORY_ROOT / "private-data/gemini-development-drafts"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "저장소의 공개 합성 문서만 Gemini 무료 API로 분석해 개발 초안을 만듭니다."
        )
    )
    parser.add_argument(
        "--confirm-public-synthetic-data",
        action="store_true",
        help="실제 이력서가 아닌 공개 합성 예제만 전송함을 확인합니다.",
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--draft-directory",
        type=Path,
        default=DEFAULT_DRAFT_DIRECTORY,
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    if not args.confirm_public_synthetic_data:
        print(
            "Gemini 개발 분석 중단: 공개 합성 예제 전송 확인이 필요합니다. "
            "실제 이력서나 private-data는 이 명령에서 사용할 수 없습니다.",
            file=sys.stderr,
        )
        return 2

    now = datetime.now().astimezone()
    try:
        manifest, content = build_profile_document_import(
            PUBLIC_SYNTHETIC_DOCUMENT,
            document_kind="resume",
            imported_at=now,
        )
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=now,
        )
        provider = GeminiDevelopmentProfileAnalysisProvider(
            load_gemini_api_key(args.env_file),
        )
        draft = analyze_profile_extraction(
            extraction,
            provider,
            analyzed_at=now,
            external_transfer_approved=True,
        )
        output_path, created = save_profile_analysis_draft(
            draft,
            args.draft_directory,
        )
    except ProfileDocumentError as error:
        print(f"Gemini 합성 프로필 분석 초안 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = draft["summary"]
    print("Gemini 합성 프로필 분석 초안 생성 완료" if created else "동일 분석 초안 재사용")
    print(f"- 경력 근거: {summary['career_evidence_count']}개")
    print(f"- 성과 근거: {summary['achievement_evidence_count']}개")
    print(f"- 기술 근거: {summary['technology_evidence_count']}개")
    print(f"- 미확인 질문: {summary['unknown_count']}개")
    print(f"- 상태: {draft['profile_analysis_draft']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 공개 합성 예제 결과이며 실제 개인 프로필은 변경되지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
