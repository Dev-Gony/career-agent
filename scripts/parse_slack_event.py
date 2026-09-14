from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    SlackEventError,
    build_slack_command_request,
    save_slack_command_request,
)


DEFAULT_EVENT = REPOSITORY_ROOT / "data/slack_app_mention.example.json"
DEFAULT_CONFIG = REPOSITORY_ROOT / "data/slack_interface.example.json"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "private-data/slack-command-requests"


def _load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SlackEventError(f"JSON 파일을 읽을 수 없음: {path}") from error
    if not isinstance(value, dict):
        raise SlackEventError(f"최상위 JSON은 객체여야 함: {path}")
    return value


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Slack app_mention 예제를 검증하고 내부 동작 요청으로 변환합니다."
    )
    parser.add_argument("--event", type=Path, default=DEFAULT_EVENT)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
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
        request = build_slack_command_request(
            _load_json(args.event),
            _load_json(args.config),
            received_at=datetime.now().astimezone(),
        )
        output_path, created = save_slack_command_request(
            request,
            args.output_directory,
        )
    except SlackEventError as error:
        print(f"Slack 이벤트 변환 실패: {error}", file=sys.stderr)
        return 1

    root = request["slack_command_request"]
    print("Slack 명령 요청 생성 완료" if created else "동일 Slack 명령 요청 재사용")
    print(f"- 라우팅 상태: {root['routing_status']}")
    print(f"- 명령: {root['command_name'] or '없음'}")
    print(f"- 내부 동작: {root['action'] or '없음'}")
    print(f"- 처리 이유: {root['reason']}")
    print(f"- 실행 상태: {root['execution_status']}")
    print(f"- 저장: {output_path}")
    print("주의: 로컬 이벤트 변환만 검증했으며 실제 공고 분석은 실행하지 않았습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
