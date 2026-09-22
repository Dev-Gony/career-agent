from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.search_plan import (  # noqa: E402
    JobSearchPlanError,
    build_job_search_plan,
)
from career_agent.discovery.ranking import build_profile_relevance  # noqa: E402


GENERATED_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _profile() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
            encoding="utf-8"
        )
    )


class JobSearchPlanGeneratorTest(unittest.TestCase):
    def test_builds_plan_only_from_confirmed_roles_skills_and_preferences(self) -> None:
        result = build_job_search_plan(_profile(), generated_at=GENERATED_AT)
        plan = result["job_search_plan"]

        self.assertEqual("sample-user-001", plan["identity"]["profile_id"])
        self.assertEqual(
            ["AI Automation / Workflow Engineer", "AI Automation", "Workflow Engineer"],
            plan["role_axes"][0]["discovery_terms"][:3],
        )
        self.assertIn("AI Agent", plan["role_axes"][0]["discovery_terms"])
        self.assertIn("Automation Engineer", plan["role_axes"][0]["discovery_terms"])
        self.assertIn("AI 자동화", plan["role_axes"][0]["discovery_terms"])
        signals = {item["signal"] for item in plan["capability_signals"]}
        self.assertIn("Python", signals)
        self.assertIn("REST API", signals)
        self.assertNotIn("Docker", signals)
        self.assertNotIn("AWS", signals)
        self.assertNotIn("SQL", signals)
        self.assertEqual(
            ["서울", "경기", "인천"],
            plan["objective_preferences"]["locations"]["normalized_values"],
        )
        self.assertEqual(
            ["정규직"],
            plan["objective_preferences"]["employment_types"]["values"],
        )
        self.assertEqual(
            {"career_years", "remote_preference"},
            {item["field"] for item in plan["unknown_constraints"]},
        )
        self.assertFalse(plan["metadata"]["git_tracking_allowed"])
        self.assertTrue(plan["metadata"]["contains_personal_data"])

    def test_plan_id_changes_with_profile_content_but_not_generation_time(self) -> None:
        profile = _profile()
        first = build_job_search_plan(profile, generated_at=GENERATED_AT)
        later = build_job_search_plan(
            profile,
            generated_at=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        changed_profile = deepcopy(profile)
        changed_profile["profile"]["basic"]["location_preference"] = ["서울"]
        changed = build_job_search_plan(changed_profile, generated_at=GENERATED_AT)

        self.assertEqual(
            first["job_search_plan"]["identity"]["plan_id"],
            later["job_search_plan"]["identity"]["plan_id"],
        )
        self.assertNotEqual(
            first["job_search_plan"]["identity"]["plan_id"],
            changed["job_search_plan"]["identity"]["plan_id"],
        )

    def test_generated_plan_is_accepted_by_discovery_ranking(self) -> None:
        plan = build_job_search_plan(_profile(), generated_at=GENERATED_AT)
        relevance = build_profile_relevance(
            {
                "title": "Workflow Engineer",
                "location_text": "Seoul",
                "employment_text": "full_time",
            },
            plan,
        )

        self.assertEqual("sample-user-001", relevance["profile_id"])
        self.assertEqual("high", relevance["priority"])
        self.assertEqual(["role-ai-automation"], relevance["related_target_role_ids"])

    def test_preserves_recall_for_current_ai_agent_discovery_titles(self) -> None:
        plan = build_job_search_plan(_profile(), generated_at=GENERATED_AT)

        current_opening = build_profile_relevance(
            {
                "title": "Software Engineer, AI Agent",
                "location_text": "Seoul",
                "employment_text": "full_time",
            },
            plan,
        )
        internship = build_profile_relevance(
            {
                "title": "AI Agent Engineer, Intern",
                "location_text": "Seoul",
                "employment_text": "internship",
            },
            plan,
        )

        self.assertEqual("high", current_opening["priority"])
        self.assertIn(
            "제목에 검색 확장어 'AI Agent'가 포함됨",
            current_opening["positive_signals"],
        )
        self.assertEqual("medium", internship["priority"])
        self.assertEqual("mismatch", internship["employment_assessment"])

    def test_unknown_role_id_uses_only_confirmed_role_text(self) -> None:
        profile = _profile()
        profile["profile"]["target_roles"] = [
            {
                "target_role_id": "role-user-confirmed-custom",
                "role": "Custom Platform / Integration Engineer",
                "priority": 1,
                "hypothesis": "사용자가 확인한 신규 탐색 직무",
            }
        ]

        plan = build_job_search_plan(profile, generated_at=GENERATED_AT)

        self.assertEqual(
            [
                "Custom Platform / Integration Engineer",
                "Custom Platform",
                "Integration Engineer",
            ],
            plan["job_search_plan"]["role_axes"][0]["discovery_terms"],
        )

    def test_rejects_missing_roles_and_naive_datetime(self) -> None:
        profile = _profile()
        profile["profile"]["target_roles"] = []
        with self.assertRaisesRegex(JobSearchPlanError, "목표 직무"):
            build_job_search_plan(profile, generated_at=GENERATED_AT)
        with self.assertRaisesRegex(JobSearchPlanError, "시간대"):
            build_job_search_plan(_profile(), generated_at=datetime(2026, 9, 22))


if __name__ == "__main__":
    unittest.main()
