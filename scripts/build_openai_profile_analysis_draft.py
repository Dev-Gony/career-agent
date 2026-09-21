from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    DEFAULT_OPENAI_PROFILE_ANALYSIS_MODEL,
    OPENAI_PROFILE_ANALYSIS_MODELS,
    OpenAIResponsesProfileAnalysisProvider,
    ProfileDocumentError,
    analyze_profile_extraction,
    load_openai_api_key,
    load_profile_text_extraction,
    save_profile_analysis_draft,
)


DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_EXTRACTION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-extractions"
DEFAULT_DRAFT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-drafts"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="저장된 프로필 후보를 OpenAI API로 분석해 검토 초안을 만듭니다."
    )
    parser.add_argument("--extraction-id", required=True)
    parser.add_argument(
        "--approve-external-transfer",
        action="store_true",
        help="후보 문장의 OpenAI API 전송과 과금 가능성을 확인합니다.",
    )
    parser.add_argument(
        "--model",
        choices=sorted(OPENAI_PROFILE_ANALYSIS_MODELS),
        default=DEFAULT_OPENAI_PROFILE_ANALYSIS_MODEL,
    )
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--extraction-directory",
        type=Path,
        default=DEFAULT_EXTRACTION_DIRECTORY,
    )
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
    if not args.approve_external_transfer:
        print(
            "프로필 분석 초안 생성 중단: 외부 전송 승인이 필요합니다. "
            "후보 문장 전송과 API 과금 가능성을 확인한 뒤 "
            "--approve-external-transfer를 사용하세요.",
            file=sys.stderr,
        )
        return 2
    try:
        extraction = load_profile_text_extraction(
            args.extraction_id,
            args.extraction_directory,
        )
        provider = OpenAIResponsesProfileAnalysisProvider(
            load_openai_api_key(args.env_file),
            model_name=args.model,
        )
        draft = analyze_profile_extraction(
            extraction,
            provider,
            analyzed_at=datetime.now().astimezone(),
            external_transfer_approved=True,
        )
        output_path, created = save_profile_analysis_draft(
            draft,
            args.draft_directory,
        )
    except ProfileDocumentError as error:
        print(f"OpenAI 프로필 분석 초안 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = draft["summary"]
    print("OpenAI 프로필 분석 초안 생성 완료" if created else "동일 분석 초안 재사용")
    print(f"- 경력 근거: {summary['career_evidence_count']}개")
    print(f"- 성과 근거: {summary['achievement_evidence_count']}개")
    print(f"- 기술 근거: {summary['technology_evidence_count']}개")
    print(f"- 미확인 질문: {summary['unknown_count']}개")
    print(f"- 상태: {draft['profile_analysis_draft']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 사용자 승인 전 개인 프로필과 검색 조건은 변경되지 않습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
