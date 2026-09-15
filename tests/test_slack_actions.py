from __future__ import annotations

from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import SlackEventError, run_slack_career_action  # noqa: E402


SUCCESS_OUTPUT = """Greenhouse 다음 검토 공고 1건 분석 완료
- 선택: Example <AI> & Data / Agent Engineer
- 큐 위치: 4
- 지원 판단: apply_with_preparation
- 우선 확인 항목: 3개
- 학습 과제: 1개
- 포트폴리오 과제: 1개
- 현재 큐 분석 완료: 4개
- 현재 큐 분석 필요: 6개
- 분석 저장: private-data/secret.json
"""


def _repository() -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory()
    scripts = Path(directory.name) / "scripts"
    scripts.mkdir()
    (scripts / "analyze_next_greenhouse_review.py").write_text(
        "# test placeholder\n",
        encoding="utf-8",
    )
    return directory


class SlackActionsTest(unittest.TestCase):
    def test_runs_static_command_and_returns_escaped_public_summary(self) -> None:
        calls: list[tuple] = []

        def run_process(command, **options):
            calls.append((command, options))
            return subprocess.CompletedProcess(command, 0, SUCCESS_OUTPUT, "")

        with _repository() as directory:
            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=run_process,
            )

        self.assertEqual("completed", result["status"])
        self.assertIn("Example &lt;AI&gt; &amp; Data", result["public_message"])
        self.assertNotIn("private-data", result["public_message"])
        command, options = calls[0]
        self.assertEqual(sys.executable, command[0])
        self.assertTrue(command[1].endswith("analyze_next_greenhouse_review.py"))
        self.assertNotIn("shell", options)
        self.assertEqual(180.0, options["timeout"])

    def test_returns_fixed_failure_without_exposing_stderr(self) -> None:
        secret_error = "private path and remote response"

        def run_process(command, **_options):
            return subprocess.CompletedProcess(command, 1, "", secret_error)

        with _repository() as directory:
            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=run_process,
            )

        self.assertEqual("failed", result["status"])
        self.assertNotIn(secret_error, result["public_message"])

    def test_returns_fixed_failure_for_timeout_and_invalid_output(self) -> None:
        def timeout_process(*_args, **_options):
            raise subprocess.TimeoutExpired("command", 180)

        with _repository() as directory:
            timed_out = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=timeout_process,
            )
            malformed = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=lambda command, **_options: subprocess.CompletedProcess(
                    command, 0, "unexpected output", ""
                ),
            )

        self.assertEqual("failed", timed_out["status"])
        self.assertEqual("failed", malformed["status"])

    def test_rejects_unknown_action_before_starting_process(self) -> None:
        with self.assertRaisesRegex(SlackEventError, "허용되지 않은"):
            run_slack_career_action(
                "delete_everything",
                repository_root=REPOSITORY_ROOT,
            )


if __name__ == "__main__":
    unittest.main()
