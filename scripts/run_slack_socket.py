from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    create_slack_bolt_app,
    load_slack_interface_config,
    load_slack_tokens,
    register_slack_app_mention_listener,
    run_slack_career_action,
    run_slack_socket_mode,
)


DEFAULT_CONFIG = REPOSITORY_ROOT / "private-data/slack_interface.json"
DEFAULT_ENV_FILE = REPOSITORY_ROOT / ".env"
DEFAULT_OUTPUT_DIRECTORY = (
    REPOSITORY_ROOT / "private-data/slack-command-requests"
)


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
        )
        print("Slack Socket Mode 수신기를 시작합니다.")
        print("- 지원 명령: @career_break 다음 공고 찾아줘")
        print("- 현재 단계: 수신·검증·다음 공고 1건 분석 수행")
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
