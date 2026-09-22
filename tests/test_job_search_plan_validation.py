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
    validate_job_search_plan,
    validate_job_search_plan_for_profile,
)


GENERATED_AT = datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc)


def _profile() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
            encoding="utf-8"
        )
    )


class JobSearchPlanValidationTest(unittest.TestCase):
    def test_accepts_public_example_for_exact_public_profile(self) -> None:
        example = json.loads(
            (REPOSITORY_ROOT / "data/job_search_plan.example.json").read_text(
                encoding="utf-8"
            )
        )

        validated = validate_job_search_plan_for_profile(example, _profile())

        self.assertTrue(validated["job_search_plan"]["metadata"]["is_example"])

    def test_accepts_generated_plan_for_exact_profile_without_mutating_inputs(self) -> None:
        profile = _profile()
        plan = build_job_search_plan(profile, generated_at=GENERATED_AT)
        original_profile = deepcopy(profile)
        original_plan = deepcopy(plan)

        validated = validate_job_search_plan_for_profile(plan, profile)
        validated["job_search_plan"]["identity"]["version"] = 99

        self.assertEqual(original_profile, profile)
        self.assertEqual(original_plan, plan)

    def test_accepts_unwrapped_current_plan_and_returns_wrapped_copy(self) -> None:
        profile = _profile()
        wrapped = build_job_search_plan(profile, generated_at=GENERATED_AT)

        validated = validate_job_search_plan(wrapped["job_search_plan"])

        self.assertEqual(wrapped, validated)

    def test_rejects_plan_for_different_profile_id(self) -> None:
        profile = _profile()
        plan = build_job_search_plan(profile, generated_at=GENERATED_AT)
        plan["job_search_plan"]["identity"]["profile_id"] = "other-user"

        with self.assertRaisesRegex(JobSearchPlanError, "profile_id"):
            validate_job_search_plan_for_profile(plan, profile)

    def test_rejects_plan_after_selected_profile_content_changes(self) -> None:
        profile = _profile()
        plan = build_job_search_plan(profile, generated_at=GENERATED_AT)
        changed_profile = deepcopy(profile)
        changed_profile["profile"]["basic"]["location_preference"] = ["서울"]

        with self.assertRaisesRegex(JobSearchPlanError, "내용 지문"):
            validate_job_search_plan_for_profile(plan, changed_profile)

    def test_rejects_missing_profile_hash_as_safe_domain_error(self) -> None:
        plan = build_job_search_plan(_profile(), generated_at=GENERATED_AT)
        del plan["job_search_plan"]["identity"]["profile_content_sha256"]

        with self.assertRaisesRegex(JobSearchPlanError, "필수 필드 누락"):
            validate_job_search_plan_for_profile(plan, _profile())

    def test_rejects_damaged_nested_schema_as_safe_domain_error(self) -> None:
        plan = build_job_search_plan(_profile(), generated_at=GENERATED_AT)
        del plan["job_search_plan"]["role_axes"][0]["discovery_terms"]

        with self.assertRaisesRegex(JobSearchPlanError, "discovery_terms"):
            validate_job_search_plan_for_profile(plan, _profile())

    def test_rejects_stale_schema_and_invalid_hash_format(self) -> None:
        stale = build_job_search_plan(_profile(), generated_at=GENERATED_AT)
        stale["job_search_plan"]["metadata"]["schema_version"] = "0.9"
        with self.assertRaisesRegex(JobSearchPlanError, "스키마 버전"):
            validate_job_search_plan(stale)

        invalid_hash = build_job_search_plan(_profile(), generated_at=GENERATED_AT)
        invalid_hash["job_search_plan"]["identity"]["profile_content_sha256"] = "bad"
        with self.assertRaisesRegex(JobSearchPlanError, "형식"):
            validate_job_search_plan(invalid_hash)


if __name__ == "__main__":
    unittest.main()
