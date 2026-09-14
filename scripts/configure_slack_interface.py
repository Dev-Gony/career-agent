from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_slack_interface_config,
    load_slack_authentication_result,
    save_slack_interface_config,
)


DEFAULT_AUTH_DIRECTORY = REPOSITORY_ROOT / "private-data/slack-auth"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "private-data/slack_interface.json"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="검증된 Slack 앱 ID와 개인 허용 목록을 비공개 설정으로 만듭니다."
    )
    parser.add_argument("--auth-id", required=True)
    parser.add_argument("--app-id", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--channel-id", required=True)
    parser.add_argument(
        "--auth-directory",
        type=Path,
        default=DEFAULT_AUTH_DIRECTORY,
    )
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        authentication = load_slack_authentication_result(
            args.auth_id,
            args.auth_directory,
        )
        config = build_slack_interface_config(
            authentication,
            api_app_id=args.app_id,
            allowed_user_id=args.user_id,
            allowed_channel_id=args.channel_id,
        )
        output_path, created = save_slack_interface_config(config, args.output)
    except SlackEventError as error:
        print(f"Slack 비공개 설정 생성 실패: {error}", file=sys.stderr)
        return 1

    print("Slack 비공개 설정 생성 완료" if created else "동일 Slack 비공개 설정 재사용")
    print("- 인증된 워크스페이스와 봇 사용자 연결: 완료")
    print("- 허용 사용자 1명: 설정")
    print("- 허용 채널 1개: 설정")
    print(f"- 저장: {output_path}")
    print("주의: ID 값은 출력하지 않았고 설정 파일은 Git에서 제외됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
