from __future__ import annotations

from copy import deepcopy
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_draft,
    build_profile_analysis_review,
    build_profile_analysis_update_proposal,
    build_profile_document_import,
    build_profile_text_extraction,
    load_profile_analysis_update_proposal,
    save_profile_analysis_update_proposal,
    save_profile_analysis_draft,
    save_profile_analysis_review,
)
from scripts.build_profile_analysis_update_proposal import main  # noqa: E402


CREATED_AT = datetime(2026, 9, 21, 15, tzinfo=timezone.utc)


def _profile() -> dict:
    return json.loads(
        (REPOSITORY_ROOT / "data/user_profile.example.json").read_text(
            encoding="utf-8"
        )
    )


def _draft(model_name: str = "fixture-v1") -> dict:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.md"
        source.write_text(
            "\n".join(
                (
                    "## 경력",
                    "- QA Engineer로 API 테스트를 수행했습니다.",
                    "- 회귀 테스트 자동화로 실행 시간을 40% 단축했습니다.",
                    "## 기술",
                    "- Python으로 테스트 데이터 검증 도구를 개발했습니다.",
                    "- Playwright로 브라우저 회귀 테스트를 자동화했습니다.",
                )
            ),
            encoding="utf-8",
        )
        manifest, content = build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=CREATED_AT - timedelta(hours=3),
        )
        extraction = build_profile_text_extraction(
            manifest,
            content,
            extracted_at=CREATED_AT - timedelta(hours=2),
        )
    candidate_ids = [item["candidate_id"] for item in extraction["candidates"]]
    return build_profile_analysis_draft(
        extraction,
        {
            "career_evidence": [
                {
                    "role_or_context": "QA Engineer",
                    "period_expression": None,
                    "responsibility_evidence": "API 테스트를 수행했습니다.",
                    "candidate_ids": [candidate_ids[0]],
                    "confidence": "high",
                }
            ],
            "achievement_evidence": [
                {
                    "problem_evidence": None,
                    "action_evidence": "회귀 테스트 자동화",
                    "result_evidence": "실행 시간을 40% 단축했습니다.",
                    "candidate_ids": [candidate_ids[1]],
                    "confidence": "high",
                }
            ],
            "technology_evidence": [
                {
                    "technology_name": "Python",
                    "usage_evidence": "Python으로 테스트 데이터 검증 도구를 개발했습니다.",
                    "proficiency_status": "unconfirmed",
                    "candidate_ids": [candidate_ids[2]],
                    "confidence": "high",
                },
                {
                    "technology_name": "Playwright",
                    "usage_evidence": "Playwright로 브라우저 회귀 테스트를 자동화했습니다.",
                    "proficiency_status": "unconfirmed",
                    "candidate_ids": [candidate_ids[3]],
                    "confidence": "high",
                },
            ],
            "unknowns": [
                {
                    "question": "Playwright를 실무에서 사용했나요?",
                    "reason": "원문만으로 실무 사용 여부를 확정할 수 없습니다.",
                    "candidate_ids": [candidate_ids[3]],
                    "confidence": "medium",
                }
            ],
        },
        analyzed_at=CREATED_AT - timedelta(hours=1),
        provider_name="synthetic",
        model_name=model_name,
        data_boundary="local",
    )


def _review(
    draft: dict,
    item_type: str,
    item_position: int,
    decision: str,
    minute: int,
) -> dict:
    return build_profile_analysis_review(
        draft,
        item_type=item_type,
        item_position=item_position,
        decision=decision,
        reviewed_at=CREATED_AT + timedelta(minutes=minute),
    )


class ProfileAnalysisUpdateProposalTest(unittest.TestCase):
    def test_builds_conservative_proposal_without_mutating_profile(self) -> None:
        profile = _profile()
        original = deepcopy(profile)
        draft = _draft()
        reviews = [
            _review(draft, "career_evidence", 1, "approve", 1),
            _review(draft, "achievement_evidence", 1, "approve", 2),
            _review(draft, "technology_evidence", 1, "approve", 3),
            _review(draft, "technology_evidence", 2, "approve", 4),
            _review(draft, "unknowns", 1, "approve", 5),
        ]

        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            reviews,
            created_at=CREATED_AT,
        )

        self.assertEqual(original, profile)
        self.assertEqual("needs_mapping", proposal["profile_analysis_update_proposal"]["status"])
        self.assertEqual(5, proposal["summary"]["approved_count"])
        self.assertEqual(4, proposal["summary"]["approved_profile_fact_count"])
        self.assertEqual(4, proposal["summary"]["proposed_change_count"])
        self.assertEqual(1, proposal["excluded"]["approved_unknown_count"])
        career = proposal["proposed_changes"][0]
        python = proposal["proposed_changes"][2]
        playwright = proposal["proposed_changes"][3]
        self.assertEqual("needs_career_selection", career["target"]["mapping_status"])
        self.assertEqual("skill-python", python["target"]["record_id"])
        self.assertEqual("ready_for_final_review", python["target"]["mapping_status"])
        self.assertIsNone(python["proposed_value"]["proposed_level"])
        self.assertIsNone(playwright["target"]["record_id"])
        self.assertEqual(
            "needs_skill_level_confirmation",
            playwright["target"]["mapping_status"],
        )
        serialized = json.dumps(proposal, ensure_ascii=False)
        self.assertNotIn("candidate-", serialized)
        self.assertFalse(proposal["metadata"]["profile_updated"])

    def test_latest_rejection_overrides_earlier_approval(self) -> None:
        draft = _draft()
        proposal = build_profile_analysis_update_proposal(
            _profile(),
            draft,
            [
                _review(draft, "career_evidence", 1, "approve", 1),
                _review(draft, "career_evidence", 1, "reject", 2),
            ],
            created_at=CREATED_AT,
        )

        self.assertEqual(
            "no_approved_profile_facts",
            proposal["profile_analysis_update_proposal"]["status"],
        )
        self.assertEqual(1, proposal["summary"]["reviewed_count"])
        self.assertEqual(0, proposal["summary"]["approved_count"])
        self.assertEqual(1, proposal["summary"]["rejected_count"])
        self.assertEqual([], proposal["proposed_changes"])

    def test_ignores_reviews_for_another_draft(self) -> None:
        draft = _draft()
        other = _draft("fixture-v2")
        proposal = build_profile_analysis_update_proposal(
            _profile(),
            draft,
            [_review(other, "career_evidence", 1, "approve", 1)],
            created_at=CREATED_AT,
        )

        self.assertEqual(0, proposal["summary"]["reviewed_count"])
        self.assertEqual([], proposal["proposed_changes"])

    def test_skips_duplicate_existing_skill_evidence(self) -> None:
        profile = _profile()
        profile["profile"]["skills"][0]["evidence"].append(
            "Python으로 테스트 데이터 검증 도구를 개발했습니다."
        )
        draft = _draft()
        proposal = build_profile_analysis_update_proposal(
            profile,
            draft,
            [_review(draft, "technology_evidence", 1, "approve", 1)],
            created_at=CREATED_AT,
        )

        self.assertEqual("no_changes", proposal["profile_analysis_update_proposal"]["status"])
        self.assertEqual(1, proposal["excluded"]["duplicate_skill_evidence_count"])
        self.assertEqual([], proposal["proposed_changes"])

    def test_saves_reuses_and_rejects_tampered_proposal(self) -> None:
        draft = _draft()
        proposal = build_profile_analysis_update_proposal(
            _profile(),
            draft,
            [_review(draft, "technology_evidence", 1, "approve", 1)],
            created_at=CREATED_AT,
        )
        with tempfile.TemporaryDirectory() as directory:
            path, created = save_profile_analysis_update_proposal(proposal, directory)
            loaded = load_profile_analysis_update_proposal(
                proposal["profile_analysis_update_proposal"]["proposal_id"],
                directory,
            )
            _, reused = save_profile_analysis_update_proposal(proposal, directory)
            tampered = deepcopy(proposal)
            tampered["proposed_changes"][0]["proposed_value"]["usage_evidence"] = (
                "변조된 근거"
            )
            with self.assertRaisesRegex(ProfileDocumentError, "내용 지문"):
                save_profile_analysis_update_proposal(tampered, directory)

        self.assertTrue(created)
        self.assertFalse(reused)
        self.assertEqual(proposal, loaded)
        self.assertTrue(path.name.startswith("profile-analysis-update-proposal-"))

    def test_cli_builds_private_proposal_without_updating_profile(self) -> None:
        draft = _draft()
        review = _review(draft, "technology_evidence", 1, "approve", 1)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            draft_directory = root / "drafts"
            review_directory = root / "reviews"
            proposal_directory = root / "proposals"
            profile_path = root / "profile.json"
            profile_path.write_text(
                json.dumps(_profile(), ensure_ascii=False),
                encoding="utf-8",
            )
            save_profile_analysis_draft(draft, draft_directory)
            save_profile_analysis_review(review, review_directory)
            output = StringIO()
            with patch(
                "sys.argv",
                [
                    "build_profile_analysis_update_proposal.py",
                    "--draft-id",
                    draft["profile_analysis_draft"]["draft_id"],
                    "--profile",
                    str(profile_path),
                    "--draft-directory",
                    str(draft_directory),
                    "--review-directory",
                    str(review_directory),
                    "--proposal-directory",
                    str(proposal_directory),
                ],
            ), redirect_stdout(output):
                result = main()
            saved = list(proposal_directory.glob("*.json"))

        self.assertEqual(0, result)
        self.assertEqual(1, len(saved))
        self.assertIn("기존 사용자 프로필은 변경하지 않았습니다", output.getvalue())


if __name__ == "__main__":
    unittest.main()
