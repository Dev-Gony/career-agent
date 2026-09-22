from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_draft_search_base_profile,
    build_provisional_search_profile,
    build_profile_analysis_draft,
    load_provisional_search_profile,
    save_provisional_search_profile,
    validate_provisional_search_profile,
)
from career_agent.search_plan import build_job_search_plan  # noqa: E402
from tests.test_profile_analysis_draft import _extraction, _response  # noqa: E402


PROJECTED_AT = datetime(2026, 9, 22, 14, 0, tzinfo=timezone.utc)


def _base_profile() -> dict:
    profile = json.loads(
        (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
            encoding="utf-8"
        )
    )
    profile["profile"]["skills"] = [
        skill
        for skill in profile["profile"]["skills"]
        if skill["name"] != "Python"
    ]
    profile["metadata"]["data_type"] = "private_test_fixture"
    profile["metadata"]["contains_sensitive_personal_data"] = True
    return profile


def _draft() -> dict:
    return build_profile_analysis_draft(
        _extraction(),
        _response(),
        analyzed_at=PROJECTED_AT,
        provider_name="synthetic",
        model_name="fixture-v1",
        data_boundary="local",
    )


class ProvisionalSearchProfileTest(unittest.TestCase):
    def test_builds_draft_only_base_without_public_example_facts(self) -> None:
        draft = _draft()

        base = build_draft_search_base_profile(draft)

        self.assertEqual([], base["profile"]["career_history"])
        self.assertEqual([], base["profile"]["projects"])
        self.assertEqual([], base["profile"]["skills"])
        self.assertEqual([], base["profile"]["basic"]["location_preference"])
        self.assertEqual(
            draft["analysis"]["career_evidence"][0]["role_or_context"],
            base["profile"]["target_roles"][0]["role"],
        )
        self.assertEqual("unconfirmed", base["metadata"]["evidence_status"])
        self.assertFalse(base["metadata"]["git_tracking_allowed"])

    def test_projects_unconfirmed_evidence_without_mutating_or_activating_profile(self) -> None:
        base = _base_profile()
        original = deepcopy(base)

        projection = build_provisional_search_profile(
            base,
            _draft(),
            projected_at=PROJECTED_AT,
        )
        profile_document = projection["profile_document"]
        python = next(
            skill
            for skill in profile_document["profile"]["skills"]
            if skill["name"] == "Python"
        )

        self.assertEqual(original, base)
        self.assertEqual("provisional_search_only", projection["provisional_search_profile"]["status"])
        self.assertEqual("unconfirmed", python["level"])
        self.assertEqual("unconfirmed", python["verification_status"])
        self.assertEqual(
            projection["provisional_search_profile"]["source_draft_id"],
            python["provenance"]["source_draft_id"],
        )
        self.assertEqual(
            original["profile"]["career_history"],
            profile_document["profile"]["career_history"],
        )
        self.assertEqual(
            "unconfirmed",
            profile_document["profile"]["provisional_evidence"]["status"],
        )
        self.assertFalse(profile_document["metadata"]["permanent_profile_updated"])
        self.assertFalse(projection["metadata"]["git_tracking_allowed"])

    def test_search_plan_uses_draft_skill_only_as_supporting_signal(self) -> None:
        projection = build_provisional_search_profile(
            _base_profile(),
            _draft(),
            projected_at=PROJECTED_AT,
        )

        plan = build_job_search_plan(
            projection["profile_document"],
            generated_at=PROJECTED_AT,
        )["job_search_plan"]
        python_signal = next(
            signal for signal in plan["capability_signals"] if signal["signal"] == "Python"
        )

        self.assertEqual("supporting", python_signal["importance"])
        self.assertIn("Python", plan["role_axes"][0]["supporting_terms"])
        self.assertEqual(
            "provisional_profile_derived_rule",
            plan["metadata"]["generated_by"],
        )
        self.assertIn(
            "provisional_profile_evidence",
            {item["field"] for item in plan["unknown_constraints"]},
        )

    def test_confirmed_base_skill_is_not_overwritten_by_draft(self) -> None:
        base = json.loads(
            (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
                encoding="utf-8"
            )
        )
        projection = build_provisional_search_profile(
            base,
            _draft(),
            projected_at=PROJECTED_AT,
        )
        python_skills = [
            skill
            for skill in projection["profile_document"]["profile"]["skills"]
            if skill["name"] == "Python"
        ]

        self.assertEqual(1, len(python_skills))
        self.assertEqual("project", python_skills[0]["level"])
        self.assertNotIn("verification_status", python_skills[0])
        self.assertEqual(
            1,
            len(
                projection["profile_document"]["profile"]["provisional_evidence"][
                    "technology_evidence"
                ]
            ),
        )

    def test_saves_loads_and_rejects_tampering_against_exact_sources(self) -> None:
        base = _base_profile()
        draft = _draft()
        projection = build_provisional_search_profile(
            base,
            draft,
            projected_at=PROJECTED_AT,
        )
        projection_id = projection["provisional_search_profile"]["projection_id"]

        with tempfile.TemporaryDirectory() as directory:
            path, created = save_provisional_search_profile(
                projection,
                directory,
                base_profile=base,
                draft=draft,
            )
            same_path, reused = save_provisional_search_profile(
                projection,
                directory,
                base_profile=base,
                draft=draft,
            )
            loaded = load_provisional_search_profile(
                projection_id,
                directory,
                base_profile=base,
                draft=draft,
            )
            tampered = deepcopy(projection)
            tampered["profile_document"]["profile"]["skills"][-1]["level"] = "work"

            self.assertTrue(created)
            self.assertFalse(reused)
            self.assertEqual(path, same_path)
            self.assertEqual(projection, loaded)
            with self.assertRaisesRegex(ProfileDocumentError, "일치하지 않음"):
                validate_provisional_search_profile(
                    tampered,
                    base_profile=base,
                    draft=draft,
                )

    def test_rejects_naive_projection_time(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_provisional_search_profile(
                _base_profile(),
                _draft(),
                projected_at=datetime(2026, 9, 22, 14, 0),
            )


if __name__ == "__main__":
    unittest.main()
