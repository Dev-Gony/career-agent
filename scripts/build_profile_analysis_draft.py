from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    analyze_profile_extraction,
    load_profile_text_extraction,
    save_profile_analysis_draft,
)


DEFAULT_EXTRACTION_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-extractions"
DEFAULT_DRAFT_DIRECTORY = REPOSITORY_ROOT / "private-data/profile-analysis-drafts"


class LocalJsonProfileAnalysisProvider:
    """Return a local JSON fixture without making a network request."""

    sends_data_externally = False

    def __init__(
        self,
        response: Mapping[str, Any],
        *,
        provider_name: str,
        model_name: str,
    ) -> None:
        self._response = response
        self.provider_name = provider_name
        self.model_name = model_name

    def analyze(
        self,
        request: Mapping[str, Any],
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        del request, response_schema
        return self._response


def _load_json(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ProfileDocumentError(f"JSON 파일을 읽을 수 없음: {path}") from error
    if not isinstance(document, dict):
        raise ProfileDocumentError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="저장된 프로필 후보와 로컬 합성 응답으로 분석 초안을 만듭니다."
    )
    parser.add_argument("--extraction-id", required=True)
    parser.add_argument("--response-file", type=Path, required=True)
    parser.add_argument("--provider-name", default="synthetic-file")
    parser.add_argument("--model-name", default="fixture-v1")
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
    try:
        extraction = load_profile_text_extraction(
            args.extraction_id,
            args.extraction_directory,
        )
        provider = LocalJsonProfileAnalysisProvider(
            _load_json(args.response_file),
            provider_name=args.provider_name,
            model_name=args.model_name,
        )
        draft = analyze_profile_extraction(
            extraction,
            provider,
            analyzed_at=datetime.now().astimezone(),
        )
        output_path, created = save_profile_analysis_draft(
            draft,
            args.draft_directory,
        )
    except ProfileDocumentError as error:
        print(f"프로필 분석 초안 생성 실패: {error}", file=sys.stderr)
        return 1

    summary = draft["summary"]
    print("프로필 분석 초안 생성 완료" if created else "동일 프로필 분석 초안 재사용")
    print(f"- 경력 근거: {summary['career_evidence_count']}개")
    print(f"- 성과 근거: {summary['achievement_evidence_count']}개")
    print(f"- 기술 근거: {summary['technology_evidence_count']}개")
    print(f"- 미확인 질문: {summary['unknown_count']}개")
    print(f"- 상태: {draft['profile_analysis_draft']['status']}")
    print(f"- 저장: {output_path}")
    print("주의: 로컬 합성 응답만 사용했으며 사용자 프로필은 변경하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
