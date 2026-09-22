from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import SlackEventError, run_slack_career_action  # noqa: E402


def _success_output(path: Path) -> str:
    return f"""Greenhouse 다음 검토 공고 1건 분석 완료
- 선택: Example AI & Data / Agent Engineer
- 큐 위치: 4
- 지원 판단: apply_with_preparation
- 우선 확인 항목: 3개
- 학습 과제: 1개
- 포트폴리오 과제: 1개
- 현재 큐 분석 완료: 4개
- 현재 큐 분석 필요: 6개
- 분석 저장: {path}
"""


def _analysis_document(*, source_url: str = "https://example.com/jobs/1") -> dict:
    return {
        "status": "analyzed",
        "workflow": "greenhouse_review_queue",
        "selection": {
            "company": "Example <AI> & Data",
            "title": "Agent Engineer",
            "source_url": source_url,
        },
        "analysis": {
            "job_posting": {"source": {"url": source_url}},
            "match_result": {
                "job_posting_information": {
                    "level": "partial",
                    "confirmed_fields": ["company", "position", "requirements"],
                    "missing_fields": ["responsibilities", "employment"],
                    "reasons": ["일부 비교 근거만 확인됩니다."],
                    "interpretation": "적합도 판정이 아닙니다.",
                },
                "confirmed_matches": [
                    {
                        "source_section": "requirements",
                        "name": "Python",
                        "result": "strong_match",
                        "posting_evidence": "Python 개발 경험",
                        "user_evidence": [
                            {
                                "source_type": "project",
                                "source_name": "Tech News Automation",
                                "source_id": "project-tech-news",
                                "evidence_level": "project",
                                "detail": "Python 자동화 구현",
                            }
                        ],
                    }
                ],
                "strengths": [
                    {
                        "title": "Python 활용 경험",
                        "evidence": ["Tech News Automation"],
                    }
                ],
                "gaps": [
                    {
                        "name": "운영 경험",
                        "reason": "직접 운영 근거가 부족합니다.",
                    }
                ],
                "unknowns": [
                    {
                        "question": "운영 시스템을 직접 소유한 범위를 확인",
                    }
                ],
                "application_recommendation": {
                    "status": "HOLD",
                    "decision": "조건부 지원",
                    "reasons": ["필수 조건의 충족 여부를 추가 확인해야 합니다."],
                    "next_steps": ["필수 조건부터 확인합니다."],
                },
            },
        },
    }


def _repository() -> tempfile.TemporaryDirectory:
    directory = tempfile.TemporaryDirectory()
    scripts = Path(directory.name) / "scripts"
    scripts.mkdir()
    (scripts / "analyze_next_greenhouse_review.py").write_text(
        "# test placeholder\n",
        encoding="utf-8",
    )
    (scripts / "build_greenhouse_review_queue.py").write_text(
        "# test placeholder\n",
        encoding="utf-8",
    )
    (scripts / "run_greenhouse_agent.py").write_text(
        "# test placeholder\n",
        encoding="utf-8",
    )
    return directory


def _save_analysis(directory: str, document: dict | None = None) -> Path:
    path = Path(directory) / "private-data" / "agent-runs" / "analysis.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(document or _analysis_document(), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


class SlackActionsTest(unittest.TestCase):
    def test_runs_static_command_and_returns_escaped_public_summary(self) -> None:
        calls: list[tuple] = []

        with _repository() as directory:
            analysis_path = _save_analysis(directory)

            def run_process(command, **options):
                calls.append((command, options))
                return subprocess.CompletedProcess(
                    command,
                    0,
                    _success_output(analysis_path),
                    "",
                )

            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=run_process,
            )

        self.assertEqual("completed", result["status"])
        self.assertIn("Example &lt;AI&gt; &amp; Data", result["public_message"])
        self.assertIn("<https://example.com/jobs/1|공고 원문 보기>", result["public_message"])
        self.assertIn("공고 정보 수준: 일부 부족 (partial)", result["public_message"])
        self.assertIn("최종 추천: HOLD", result["public_message"])
        self.assertIn("[필수 조건] Python", result["public_message"])
        self.assertIn("Python 자동화 구현", result["public_message"])
        self.assertIn("공고에서 확인할 수 없는 정보", result["public_message"])
        self.assertIn("주요 업무", result["public_message"])
        self.assertIn("고용 형태", result["public_message"])
        self.assertIn("운영 경험", result["public_message"])
        self.assertIn("운영 시스템을 직접 소유한 범위를 확인", result["public_message"])
        self.assertIn("분석 완료: 4개 / 분석 필요: 6개", result["public_message"])
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

    def test_rebuilds_stale_queue_once_and_retries_analysis(self) -> None:
        calls: list[str] = []

        with _repository() as directory:
            analysis_path = _save_analysis(directory)
            responses = iter(
                [
                    subprocess.CompletedProcess(
                        [],
                        1,
                        "",
                        "매칭 규칙이 바뀌었음. 검토 큐를 다시 생성해야 함",
                    ),
                    subprocess.CompletedProcess([], 0, "큐 생성 완료", ""),
                    subprocess.CompletedProcess(
                        [],
                        0,
                        _success_output(analysis_path),
                        "",
                    ),
                ]
            )

            def run_process(command, **_options):
                calls.append(Path(command[1]).name)
                return next(responses)

            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=run_process,
            )

        self.assertEqual("completed", result["status"])
        self.assertEqual(
            [
                "analyze_next_greenhouse_review.py",
                "build_greenhouse_review_queue.py",
                "analyze_next_greenhouse_review.py",
            ],
            calls,
        )

    def test_rebuilds_legacy_queue_without_search_plan_identity(self) -> None:
        calls: list[str] = []

        with _repository() as directory:
            analysis_path = _save_analysis(directory)
            responses = iter(
                [
                    subprocess.CompletedProcess(
                        [],
                        1,
                        "",
                        (
                            "Greenhouse 다음 검토 공고 분석 실패: "
                            "검색 계획 식별 정보가 없는 검토 큐는 재사용할 수 없음"
                        ),
                    ),
                    subprocess.CompletedProcess([], 0, "큐 생성 완료", ""),
                    subprocess.CompletedProcess(
                        [],
                        0,
                        _success_output(analysis_path),
                        "",
                    ),
                ]
            )

            def run_process(command, **_options):
                calls.append(Path(command[1]).name)
                return next(responses)

            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=run_process,
            )

        self.assertEqual("completed", result["status"])
        self.assertEqual(
            [
                "analyze_next_greenhouse_review.py",
                "build_greenhouse_review_queue.py",
                "analyze_next_greenhouse_review.py",
            ],
            calls,
        )

    def test_returns_normal_message_when_no_candidate_is_available(self) -> None:
        output = """Greenhouse 다음 검토 공고 없음
- 현재 큐 분석 완료: 1개
- 현재 큐 분석 필요: 3개
"""

        with _repository() as directory:
            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=lambda command, **_options: subprocess.CompletedProcess(
                    command,
                    0,
                    output,
                    "",
                ),
            )

        self.assertEqual("no_candidate", result["status"])
        self.assertIn("현재 조건에 맞는 새 공고가 없습니다", result["public_message"])
        self.assertIn("분석 완료: 1개", result["public_message"])
        self.assertIn("미분석이지만 조건 불일치: 3개", result["public_message"])
        self.assertIn("현재 분석 가능: 0", result["public_message"])
        self.assertIn("공식 채용 소스를 방금 갱신", result["public_message"])

    def test_refreshes_sources_and_retries_when_queue_has_no_candidate(self) -> None:
        no_candidate = """Greenhouse 다음 검토 공고 없음
- 현재 큐 분석 완료: 1개
- 현재 큐 분석 필요: 1개
"""
        calls: list[list[str]] = []

        with _repository() as directory:
            analysis_path = _save_analysis(directory)
            responses = iter(
                [
                    subprocess.CompletedProcess([], 0, no_candidate, ""),
                    subprocess.CompletedProcess([], 0, "공식 목록 갱신 완료", ""),
                    subprocess.CompletedProcess([], 0, "큐 생성 완료", ""),
                    subprocess.CompletedProcess(
                        [], 0, _success_output(analysis_path), ""
                    ),
                ]
            )

            def run_process(command, **_options):
                calls.append(command)
                return next(responses)

            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=run_process,
            )

        self.assertEqual("completed", result["status"])
        self.assertEqual("analyze_next_greenhouse_review.py", Path(calls[0][1]).name)
        self.assertEqual("run_greenhouse_agent.py", Path(calls[1][1]).name)
        self.assertEqual("--discovery-only", calls[1][2])
        self.assertEqual("build_greenhouse_review_queue.py", Path(calls[2][1]).name)
        self.assertEqual("analyze_next_greenhouse_review.py", Path(calls[3][1]).name)

    def test_reports_refresh_failure_without_exposing_error(self) -> None:
        no_candidate = """Greenhouse 다음 검토 공고 없음
- 현재 큐 분석 완료: 1개
- 현재 큐 분석 필요: 0개
"""
        secret_error = "remote private response"
        responses = iter(
            [
                subprocess.CompletedProcess([], 0, no_candidate, ""),
                subprocess.CompletedProcess([], 1, "", secret_error),
            ]
        )

        with _repository() as directory:
            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=lambda command, **_options: next(responses),
            )

        self.assertEqual("no_candidate", result["status"])
        self.assertIn("공식 채용 소스 갱신도 완료하지 못했습니다", result["public_message"])
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

    def test_rejects_analysis_file_outside_private_agent_runs(self) -> None:
        with _repository() as directory:
            outside_path = Path(directory) / "outside.json"
            outside_path.write_text(
                json.dumps(_analysis_document()),
                encoding="utf-8",
            )
            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=lambda command, **_options: subprocess.CompletedProcess(
                    command,
                    0,
                    _success_output(outside_path),
                    "",
                ),
            )

        self.assertEqual("failed", result["status"])
        self.assertNotIn(str(outside_path), result["public_message"])

    def test_rejects_unsafe_source_url_from_analysis(self) -> None:
        unsafe_url = "https://example.com/jobs/1|<!channel>"
        with _repository() as directory:
            analysis_path = _save_analysis(
                directory,
                _analysis_document(source_url=unsafe_url),
            )
            result = run_slack_career_action(
                "analyze_next_greenhouse_review",
                repository_root=directory,
                run_process=lambda command, **_options: subprocess.CompletedProcess(
                    command,
                    0,
                    _success_output(analysis_path),
                    "",
                ),
            )

        self.assertEqual("failed", result["status"])
        self.assertNotIn("<!channel>", result["public_message"])

    def test_rejects_unknown_action_before_starting_process(self) -> None:
        with self.assertRaisesRegex(SlackEventError, "허용되지 않은"):
            run_slack_career_action(
                "delete_everything",
                repository_root=REPOSITORY_ROOT,
            )


if __name__ == "__main__":
    unittest.main()
