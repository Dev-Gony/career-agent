from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
from typing import Any, Mapping


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    create_slack_bolt_app,
    import_slack_profile_document,
    load_slack_interface_config,
    load_slack_tokens,
    register_slack_app_mention_listener,
    run_slack_career_action,
    run_slack_socket_mode,
)
from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_evidence_summary,
    build_profile_text_extraction,
    load_profile_document_import,
    save_profile_evidence_summary,
    save_profile_text_extraction,
)


DEFAULT_CONFIG = REPOSITORY_ROOT / "private-data/slack_interface.json"
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-command-requests"
)
DEFAULT_PROFILE_DOCUMENT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-documents"
)
DEFAULT_PROFILE_EXTRACTION_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-extractions"
)
DEFAULT_PROFILE_EVIDENCE_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/profile-evidence-summaries"
)
DEFAULT_PROFILE = REPOSITORY_ROOT / "data/user_profile.example.json"


def _load_profile() -> dict[str, Any]:
    try:
        profile = json.loads(DEFAULT_PROFILE.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError("기준 사용자 프로필을 읽을 수 없음") from error
    if not isinstance(profile, dict):
        raise SlackEventError("기준 사용자 프로필 형식이 올바르지 않음")
    return profile


def _extract_imported_profile_document(
    import_result: Mapping[str, Any],
    extracted_at: datetime,
) -> dict[str, Any]:
    document_id = import_result.get("document_id")
    if not isinstance(document_id, str) or not document_id:
        raise SlackEventError("저장 결과에 문서 ID가 없음")
    try:
        manifest, content = load_profile_document_import(
            document_id,
            DEFAULT_PROFILE_DOCUMENT_DIRECTORY,
        )
        document_format = manifest["profile_document"].get("document_format")
        if document_format == "pdf":
            return {"status": "unsupported", "document_format": "pdf"}
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=extracted_at,
        )
        _, created = save_profile_text_extraction(
            extraction,
            DEFAULT_PROFILE_EXTRACTION_DIRECTORY,
        )
        evidence_summary = build_profile_evidence_summary(
            extraction,
            _load_profile(),
            analyzed_at=extracted_at,
        )
        save_profile_evidence_summary(
            evidence_summary,
            DEFAULT_PROFILE_EVIDENCE_DIRECTORY,
        )
    except ProfileDocumentError as error:
        raise SlackEventError("저장된 프로필 문서를 추출할 수 없음") from error
    return {
        "status": "extracted" if created else "reused",
        "document_format": document_format,
        "summary": extraction["summary"],
        "evidence_summary": evidence_summary["summary"],
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="실제 Slack app_mention을 Socket Mode로 받아 안전하게 확인합니다."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
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
        config = load_slack_interface_config(args.config)
        app_token, bot_token = load_slack_tokens(args.env_file)
        app = create_slack_bolt_app(bot_token)
        register_slack_app_mention_listener(
            app,
            config,
            output_directory=args.output_directory,
            action_runner=lambda action: run_slack_career_action(
                action,
                repository_root=REPOSITORY_ROOT,
            ),
            profile_document_importer=lambda reference, imported_at: (
                import_slack_profile_document(
                    reference,
                    bot_token=bot_token,
                    document_kind="other",
                    imported_at=imported_at,
                    directory=DEFAULT_PROFILE_DOCUMENT_DIRECTORY,
                )
            ),
            profile_document_extractor=_extract_imported_profile_document,
        )
        print("Slack Socket Mode 수신기를 시작합니다.")
        print("- 지원 명령: @career_break 다음 공고 찾아줘")
        print("- 지원 입력: @career_break 프로필 분석해줘 + 첨부파일 1개")
        print("- 현재 단계: 공고 1건 분석 또는 첨부파일 저장과 검토 후보 추출")
        print("- 종료: Ctrl+C")
        print("주의: 메시지 원문과 Token은 콘솔에 출력하지 않습니다.")
        run_slack_socket_mode(app, app_token)
    except SlackEventError as error:
        print(f"Slack Socket Mode 시작 실패: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Slack Socket Mode 수신기를 종료했습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
