from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.review import (  # noqa: E402
    FIT_ASSESSMENTS,
    GreenhouseReviewQueueError,
    build_greenhouse_human_review,
    save_greenhouse_human_review,
)


DEFAULT_QUEUE_DIRECTORY = REPOSITORY_ROOT / "private-data/review-queues"
DEFAULT_REVIEW_DIRECTORY = REPOSITORY_ROOT / "private-data/human-reviews"
_USEFULNESS = {"yes": True, "no": False, "unknown": None}


def _load_json(path: Path) -> dict:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise GreenhouseReviewQueueError(
            f"JSON 파일을 읽을 수 없음: {path}: {error}"
        ) from error
    if not isinstance(document, dict):
        raise GreenhouseReviewQueueError(f"최상위 JSON은 객체여야 함: {path}")
    return document


def _created_timestamp(document: dict) -> float:
    root = document.get("review_queue")
    if not isinstance(root, dict):
        return float("-inf")
    value = root.get("created_at")
    if not isinstance(value, str):
        return float("-inf")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return float("-inf")
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return float("-inf")
    return parsed.timestamp()


def _latest_queue(directory: Path) -> tuple[Path, dict]:
    if not directory.is_dir():
        raise GreenhouseReviewQueueError(f"검토 큐 디렉터리가 아님: {directory}")
    candidates = []
    for path in sorted(directory.glob("*.json")):
        document = _load_json(path)
        if _created_timestamp(document) != float("-inf"):
            candidates.append((path, document))
    if not candidates:
        raise GreenhouseReviewQueueError("사용할 Greenhouse 검토 큐가 없음")
    return max(candidates, key=lambda item: _created_timestamp(item[1]))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="상세 분석된 Greenhouse 공고에 사용자의 실제 판단을 기록합니다."
    )
    parser.add_argument("--position", type=int, required=True)
    parser.add_argument(
        "--fit",
        choices=sorted(FIT_ASSESSMENTS),
        required=True,
        help="fit=적합, hold=보류, not_fit=부적합",
    )
    parser.add_argument(
        "--recommendation-useful",
        choices=sorted(_USEFULNESS),
        default="unknown",
        help="Agent 추천이 유용했는지 yes, no, unknown 중 선택",
    )
    parser.add_argument("--notes", help="선택 메모, 최대 1000자")
    parser.add_argument("--queue-directory", type=Path, default=DEFAULT_QUEUE_DIRECTORY)
    parser.add_argument(
        "--review-directory", type=Path, default=DEFAULT_REVIEW_DIRECTORY
    )
    return parser


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    args = _build_parser().parse_args()
    try:
        queue_path, queue = _latest_queue(args.queue_directory)
        review = build_greenhouse_human_review(
            queue,
            position=args.position,
            fit_assessment=args.fit,
            recommendation_useful=_USEFULNESS[args.recommendation_useful],
            reviewed_at=datetime.now().astimezone(),
            notes=args.notes,
        )
        output_path = save_greenhouse_human_review(
            review, args.review_directory
        )
    except GreenhouseReviewQueueError as error:
        print(f"Greenhouse 사용자 검토 기록 실패: {error}", file=sys.stderr)
        return 1

    candidate = review["candidate"]
    human_review = review["human_review"]
    print("Greenhouse 사용자 검토 기록 완료")
    print(f"- 공고: {candidate['company']} / {candidate['title']}")
    print(f"- 큐 위치: {review['source']['position']}")
    print(f"- 적합 판단: {human_review['fit_assessment']}")
    print(
        "- 추천 유용성: "
        f"{args.recommendation_useful}"
    )
    print(f"- 기준 큐: {queue_path}")
    print(f"- 저장: {output_path}")
    print("주의: 이 값은 Agent의 자동 판단이 아니라 사용자가 직접 입력한 판단입니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
