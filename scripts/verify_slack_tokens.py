from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackAuthenticationError,
    SlackEventError,
    load_slack_tokens,
    save_slack_authentication_result,
    verify_slack_authentication,
)


DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "private-data/slack-auth"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Slack Token 인증과 Socket Mode 사용 가능 여부를 안전하게 확인합니다."
    )
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
        app_token, bot_token = load_slack_tokens(args.env_file)
        result = verify_slack_authentication(
            app_token,
            bot_token,
            verified_at=datetime.now().astimezone(),
        )
        output_path, created = save_slack_authentication_result(
            result,
            args.output_directory,
        )
    except (SlackAuthenticationError, SlackEventError) as error:
        print(f"Slack 인증 확인 실패: {error}", file=sys.stderr)
        print("주의: Token 값은 화면이나 로그에 출력하지 않았습니다.", file=sys.stderr)
        return 1

    identity = result["identity"]
    print("Slack 인증 확인 완료" if created else "동일 Slack 인증 결과 재사용")
    print("- Bot Token: 인증됨")
    print("- App Token: 인증됨")
    print("- Socket Mode: 사용 가능")
    print(f"- App ID 자동 확인: {'완료' if identity['api_app_id'] else '수동 확인 필요'}")
    print(f"- 저장: {output_path}")
    print("주의: Token과 임시 WebSocket URL은 출력하거나 저장하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
