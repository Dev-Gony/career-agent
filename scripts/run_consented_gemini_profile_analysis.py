from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    GeminiConsentedProfileAnalysisProvider,
    ProfileDocumentError,
    analyze_profile_extraction_with_approved_external_consent,
    load_gemini_api_key,
    load_profile_text_extraction,
    save_profile_analysis_draft,
    select_latest_profile_text_extraction,
)


DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_EXTRACTION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-extractions"
DEFAULT_SESSION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-profile-analysis-consent-sessions"
)
DEFAULT_CONSENT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-analysis-external-consents"
)
DEFAULT_DRAFT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-drafts"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "정확한 Slack 승인이 기록된 개인 문서 후보만 Gemini로 분석합니다."
        )
    )
    parser.add_argument("--extraction-id")
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    parser.add_argument(
        "--extraction-directory",
        type=Path,
        default=DEFAULT_EXTRACTION_DIRECTORY,
    )
    parser.add_argument(
        "--session-directory",
        type=Path,
        default=DEFAULT_SESSION_DIRECTORY,
    )
    parser.add_argument(
        "--consent-directory",
        type=Path,
        default=DEFAULT_CONSENT_DIRECTORY,
    )
    parser.add_argument(
        "--draft-directory",
        type=Path,
        default=DEFAULT_DRAFT_DIRECTORY,
    )
    return parser


def _select_extraction(args: argparse.Namespace) -> dict:
    if args.extraction_id:
        return load_profile_text_extraction(
            args.extraction_id,
            args.extraction_directory,
        )
    extraction = select_latest_profile_text_extraction(args.extraction_directory)
    if extraction is None:
        raise ProfileDocumentError("분석할 프로필 문서 추출 결과가 없음")
    return extraction


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        extraction = _select_extraction(args)
        provider = GeminiConsentedProfileAnalysisProvider(
            load_gemini_api_key(args.env_file),
        )
        draft = analyze_profile_extraction_with_approved_external_consent(
            extraction,
            provider,
            analyzed_at=datetime.now().astimezone(),
            session_directory=args.session_directory,
            consent_directory=args.consent_directory,
        )
        output_path, created = save_profile_analysis_draft(
            draft,
            args.draft_directory,
        )
    except ProfileDocumentError as error:
        print(f"승인된 Gemini 프로필 분석 실패: {error}", file=sys.stderr)
        return 1

    summary = draft["summary"]
    print("승인된 Gemini 프로필 분석 초안 생성 완료" if created else "동일 Gemini 분석 초안 재사용")
    print(f"- 경력 근거: {summary['career_evidence_count']}개")
    print(f"- 성과 근거: {summary['achievement_evidence_count']}개")
    print(f"- 기술 근거: {summary['technology_evidence_count']}개")
    print(f"- 추가 확인 질문: {summary['unknown_count']}개")
    print(f"- 상태: {draft['profile_analysis_draft']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: Gemini 분석 초안이며 개인 프로필과 검색 조건은 아직 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
