from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import SlackEventError, check_slack_setup  # noqa: E402


DEFAULT_CONFIG = REPOSITORY_ROOT / "private-data/slack_interface.json"
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Slack Socket Mode 연결 전 ID 설정과 Token 준비 상태를 확인합니다."
    )
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--env-file", type=Path, default=DEFAULT_ENV_FILE)
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        result = check_slack_setup(args.config, args.env_file)
    except SlackEventError as error:
        print(f"Slack 연결 준비 미완료: {error}", file=sys.stderr)
        print("주의: Token 값을 화면이나 로그에 출력하지 않았습니다.", file=sys.stderr)
        return 1

    print("Slack 연결 준비 확인 완료")
    print(f"- ID와 허용 목록 설정: {'완료' if result['config_ready'] else '미완료'}")
    print(f"- App Token: {'확인됨' if result['app_token_ready'] else '없음'}")
    print(f"- Bot Token: {'확인됨' if result['bot_token_ready'] else '없음'}")
    print("주의: Token 값은 화면이나 로그에 출력하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
