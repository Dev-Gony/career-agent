from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.matching import RequirementMatchError, match_job_requirements  # noqa: E402
from career_agent.profile_input import build_draft_search_base_profile, build_provisional_search_profile
from tests.test_provisional_search_profile import _draft, PROJECTED_AT


class RequirementMatchingServiceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = json.loads(
            (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
                encoding="utf-8"
            )
        )
        cls.posting = json.loads(
            (REPOSITORY_ROOT / "data/job_posting.example.json").read_text(
                encoding="utf-8"
            )
        )

    def test_combines_matches_in_original_posting_order(self) -> None:
        result = match_job_requirements(self.profile, self.posting)

        self.assertEqual(
            ["Python", "REST API integration", "automation project"],
            [item["requirement"]["name"] for item in result["required_matches"]],
        )
        self.assertEqual(
            ["strong_match", "strong_match", "strong_match"],
            [item["assessment"]["result"] for item in result["required_matches"]],
        )
        self.assertEqual(
            ["Docker", "AWS", "LLM API"],
            [item["requirement"]["name"] for item in result["preferred_matches"]],
        )
        self.assertEqual(
            ["gap", "gap", "strong_match"],
            [item["assessment"]["result"] for item in result["preferred_matches"]],
        )
        self.assertEqual(3, result["summary"]["required"]["strong_match"])
        self.assertEqual(2, result["summary"]["preferred"]["gap"])
        self.assertEqual("sample-user-001", result["inputs"]["profile_id"])
        self.assertEqual("job-001", result["inputs"]["posting_id"])
        self.assertEqual("eligible", result["eligibility"]["status"])
        self.assertEqual("sufficient", result["jd_information_level"])
        self.assertEqual("RECOMMEND", result["recommendation"])
        self.assertEqual(
            result["application_recommendation"]["recommendation_reason"],
            result["recommendation_reason"],
        )
        confirmed_names = [item["name"] for item in result["confirmed_matches"]]
        self.assertIn("Python", confirmed_names)
        self.assertIn("LLM API", confirmed_names)
        self.assertNotIn("Docker", confirmed_names)
        self.assertTrue(
            all(item["user_evidence"] for item in result["confirmed_matches"])
        )
        self.assertNotIn(
            "eligibility", result["metadata"]["incomplete_sections"]
        )
        self.assertNotIn(
            "application_recommendation",
            result["metadata"]["incomplete_sections"],
        )
        self.assertEqual(4, result["summary"]["responsibilities"]["total"])
        self.assertEqual(
            ["identity", "analysis_notes"],
            result["metadata"]["incomplete_sections"],
        )

    def test_keeps_unsupported_condition_as_unknown(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["requirements"].append(
            {
                "requirement_id": "requirement-certificate",
                "type": "certification",
                "name": "Example Certificate",
                "level": "required",
                "evidence_text": "Example Certificate 필수",
            }
        )

        result = match_job_requirements(self.profile, posting)
        match = result["required_matches"][-1]

        self.assertEqual("unknown", match["assessment"]["result"])
        self.assertEqual([], match["user_evidence"])
        self.assertEqual(4, result["summary"]["required"]["total"])

    def _provisional_profile(self) -> dict:
        draft = _draft()
        return build_provisional_search_profile(
            build_draft_search_base_profile(draft), draft, projected_at=PROJECTED_AT,
        )["profile_document"]

    def test_displays_sourced_resume_evidence_without_confirming_competence(self) -> None:
        profile = self._provisional_profile()
        original = deepcopy(profile)
        result = match_job_requirements(profile, self.posting)
        evidence = result["document_evidence"]

        self.assertEqual("unconfirmed", evidence["status"])
        self.assertEqual("QA Engineer", evidence["career_context"][0]["role_or_context"])
        self.assertEqual(["candidate-001"], evidence["career_context"][0]["candidate_ids"])
        self.assertEqual(["Python"], [item["name"] for item in evidence["requirement_links"]])
        python = evidence["requirement_links"][0]
        self.assertEqual("requirements", python["source_section"])
        self.assertEqual(["candidate-003"], python["user_evidence"][0]["candidate_ids"])
        self.assertEqual("unknown", result["required_matches"][0]["assessment"]["result"])
        self.assertEqual([], result["confirmed_matches"])
        self.assertEqual("HOLD", result["recommendation"])
        self.assertEqual(original, profile)
        self.assertTrue(result["metadata"]["contains_personal_data"])
        self.assertTrue(result["metadata"]["contains_candidate_text"])
        self.assertFalse(result["metadata"]["git_tracking_allowed"])
        profile["metadata"]["data_type"] = "user_profile"
        without_display = match_job_requirements(profile, self.posting)
        self.assertEqual(result["confirmed_matches"], without_display["confirmed_matches"])
        self.assertEqual(result["application_recommendation"], without_display["application_recommendation"])

    def test_document_summary_requires_provisional_marker_and_source_lineage(self) -> None:
        profile = self._provisional_profile()
        profile["profile"]["skills"][0]["provenance"]["source_draft_id"] = "another-draft"
        profile["profile"]["provisional_evidence"]["career_evidence"][0]["candidate_ids"] = []
        result = match_job_requirements(profile, self.posting)
        self.assertEqual([], result["document_evidence"]["requirement_links"])
        self.assertEqual([], result["document_evidence"]["career_context"])
        profile["metadata"]["data_type"] = "user_profile"
        self.assertIsNone(match_job_requirements(profile, self.posting)["document_evidence"])
        self.assertIsNone(match_job_requirements(self.profile, self.posting)["document_evidence"])

    def test_unrelated_draft_skill_is_not_a_requirement_link(self) -> None:
        profile = self._provisional_profile()
        profile["profile"]["skills"][0]["name"] = "Unrelated technology"
        result = match_job_requirements(profile, self.posting)
        self.assertEqual([], result["document_evidence"]["requirement_links"])

    def test_rejects_duplicate_source_ids_across_sections(self) -> None:
        posting = deepcopy(self.posting)
        posting["job_posting"]["preferred_qualifications"][0][
            "qualification_id"
        ] = "requirement-python"

        with self.assertRaisesRegex(RequirementMatchError, "중복 공고 항목 ID"):
            match_job_requirements(self.profile, posting)


if __name__ == "__main__":
    unittest.main()
