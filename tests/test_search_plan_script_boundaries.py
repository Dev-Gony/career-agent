from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.review import GreenhouseReviewQueueError  # noqa: E402
from career_agent.search_plan import JobSearchPlanError  # noqa: E402
from scripts import (  # noqa: E402
    analyze_next_greenhouse_review,
    build_greenhouse_review_queue,
    run_greenhouse_agent,
)


def _json_file(root: Path, name: str) -> Path:
    path = root / name
    path.write_text("{}\n", encoding="utf-8")
    return path


class SearchPlanScriptBoundaryTest(unittest.TestCase):
    def test_all_entrypoints_validate_explicit_plan_against_selected_profile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = _json_file(root, "profile.json")
            plan = _json_file(root, "plan.json")
            cases = (
                (
                    run_greenhouse_agent,
                    [
                        "run_greenhouse_agent.py",
                        "--profile",
                        str(profile),
                        "--search-plan",
                        str(plan),
                        "--execution-directory",
                        str(root / "run-executions"),
                    ],
                ),
                (
                    build_greenhouse_review_queue,
                    [
                        "build_greenhouse_review_queue.py",
                        "--profile",
                        str(profile),
                        "--search-plan",
                        str(plan),
                    ],
                ),
                (
                    analyze_next_greenhouse_review,
                    [
                        "analyze_next_greenhouse_review.py",
                        "--profile",
                        str(profile),
                        "--search-plan",
                        str(plan),
                        "--execution-directory",
                        str(root / "analysis-executions"),
                    ],
                ),
            )
            for module, argv in cases:
                with self.subTest(module=module.__name__):
                    with (
                        patch.object(sys, "argv", argv),
                        patch.object(
                            module,
                            "validate_job_search_plan_for_profile",
                            side_effect=JobSearchPlanError("프로필과 계획 불일치"),
                        ) as validate,
                        redirect_stdout(StringIO()),
                        redirect_stderr(StringIO()),
                    ):
                        result = module.main()

                    self.assertEqual(1, result)
                    validate.assert_called_once_with({}, {})

    def test_analyze_next_rejects_stale_queue_before_job_detail_request(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = _json_file(root, "profile.json")
            plan = _json_file(root, "plan.json")
            argv = [
                "analyze_next_greenhouse_review.py",
                "--profile",
                str(profile),
                "--search-plan",
                str(plan),
                "--execution-directory",
                str(root / "executions"),
            ]
            validated_plan = {"job_search_plan": {"identity": {}}}
            with (
                patch.object(sys, "argv", argv),
                patch.object(
                    analyze_next_greenhouse_review,
                    "validate_job_search_plan_for_profile",
                    return_value=validated_plan,
                ),
                patch.object(
                    analyze_next_greenhouse_review,
                    "_latest_queue",
                    return_value=(root / "queue.json", {}),
                ),
                patch.object(
                    analyze_next_greenhouse_review,
                    "validate_greenhouse_review_queue_search_plan",
                    side_effect=GreenhouseReviewQueueError("오래된 검색 계획 큐"),
                ) as validate_queue,
                patch.object(
                    analyze_next_greenhouse_review,
                    "analyze_greenhouse_job",
                ) as analyze_job,
                redirect_stdout(StringIO()),
                redirect_stderr(StringIO()),
            ):
                result = analyze_next_greenhouse_review.main()

        self.assertEqual(1, result)
        validate_queue.assert_called_once_with({}, validated_plan)
        analyze_job.assert_not_called()


if __name__ == "__main__":
    unittest.main()
