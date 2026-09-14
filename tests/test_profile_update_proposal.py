from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_candidate_review,
    build_profile_document_import,
    build_profile_text_extraction,
    build_profile_update_proposal,
    save_profile_update_proposal,
)


IMPORTED_AT = datetime(2026, 9, 14, 14, tzinfo=timezone.utc)
EXTRACTED_AT = datetime(2026, 9, 14, 15, tzinfo=timezone.utc)
REVIEWED_AT = datetime(2026, 9, 14, 16, tzinfo=timezone.utc)
CREATED_AT = datetime(2026, 9, 14, 18, tzinfo=timezone.utc)


def _profile() -> dict:
    return {
        "profile": {
            "basic": {
                "profile_id": "private-user-001",
                "locale": "ko-KR",
            }
        },
        "metadata": {"schema_version": "0.1"},
    }


def _extraction() -> dict:
    with tempfile.TemporaryDirectory() as directory:
        source = Path(directory) / "resume.md"
        source.write_text(
            "## 기술\n- Python\n- REST API\n## 희망 직무\n- AI 자동화 개발\n",
            encoding="utf-8",
        )
        manifest, content = build_profile_document_import(
            source,
            document_kind="resume",
            imported_at=IMPORTED_AT,
        )
    return build_profile_text_extraction(
        manifest,
        content,
        extracted_at=EXTRACTED_AT,
    )


def _review(
    extraction: dict,
    candidate_id: str,
    decision: str,
    reviewed_at: datetime,
) -> dict:
    return build_profile_candidate_review(
        extraction,
        candidate_id=candidate_id,
        decision=decision,
        reviewed_at=reviewed_at,
    )


class ProfileUpdateProposalTest(unittest.TestCase):
    def test_includes_only_latest_approved_candidates(self) -> None:
        profile = _profile()
        original_profile = deepcopy(profile)
        extraction = _extraction()
        reviews = [
            _review(extraction, "candidate-001", "reject", REVIEWED_AT),
            _review(
                extraction,
                "candidate-001",
                "approve",
                REVIEWED_AT + timedelta(minutes=1),
            ),
            _review(extraction, "candidate-002", "reject", REVIEWED_AT),
        ]

        proposal = build_profile_update_proposal(
            profile,
            extraction,
            reviews,
            created_at=CREATED_AT,
        )

        self.assertEqual(profile, original_profile)
        self.assertEqual("needs_mapping", proposal["profile_update_proposal"]["status"])
        self.assertEqual(
            {
                "candidate_count": 3,
                "reviewed_count": 2,
                "approved_count": 1,
                "rejected_count": 1,
                "unreviewed_count": 1,
            },
            proposal["summary"],
        )
        self.assertEqual(1, len(proposal["proposed_additions"]))
        addition = proposal["proposed_additions"][0]
        self.assertEqual("Python", addition["candidate_text"])
        self.assertEqual("skills", addition["profile_section"])
        self.assertEqual("needs_mapping", addition["mapping_status"])
        self.assertEqual("approve", addition["approval"]["decision"])
        self.assertEqual(2, addition["source_evidence"]["line_start"])
        self.assertFalse(proposal["metadata"]["profile_updated"])
        self.assertEqual(
            64,
            len(
                proposal["profile_update_proposal"][
                    "base_profile_content_sha256"
                ]
            ),
        )

    def test_latest_rejection_overrides_earlier_approval(self) -> None:
        extraction = _extraction()
        reviews = [
            _review(extraction, "candidate-001", "approve", REVIEWED_AT),
            _review(
                extraction,
                "candidate-001",
                "reject",
                REVIEWED_AT + timedelta(minutes=1),
            ),
        ]

        proposal = build_profile_update_proposal(
            _profile(),
            extraction,
            reviews,
            created_at=CREATED_AT,
        )

        self.assertEqual(
            "no_approved_candidates",
            proposal["profile_update_proposal"]["status"],
        )
        self.assertEqual([], proposal["proposed_additions"])
        self.assertEqual(1, proposal["summary"]["rejected_count"])

    def test_rejects_review_with_changed_source_evidence(self) -> None:
        extraction = _extraction()
        review = _review(
            extraction,
            "candidate-001",
            "approve",
            REVIEWED_AT,
        )
        review["source"]["line_start"] = 999

        with self.assertRaisesRegex(ProfileDocumentError, "근거"):
            build_profile_update_proposal(
                _profile(),
                extraction,
                [review],
                created_at=CREATED_AT,
            )

    def test_rejects_review_with_changed_identity(self) -> None:
        extraction = _extraction()
        review = _review(
            extraction,
            "candidate-001",
            "approve",
            REVIEWED_AT,
        )
        review["candidate_review"]["review_id"] = "changed-review-id"

        with self.assertRaisesRegex(ProfileDocumentError, "검토 ID"):
            build_profile_update_proposal(
                _profile(),
                extraction,
                [review],
                created_at=CREATED_AT,
            )

    def test_ignores_valid_review_for_another_extraction(self) -> None:
        extraction = _extraction()
        other = deepcopy(extraction)
        other["profile_extraction"]["extraction_id"] = "other-extraction-id"
        review = _review(other, "candidate-001", "approve", REVIEWED_AT)

        proposal = build_profile_update_proposal(
            _profile(),
            extraction,
            [review],
            created_at=CREATED_AT,
        )

        self.assertEqual(0, proposal["summary"]["reviewed_count"])
        self.assertEqual(3, proposal["summary"]["unreviewed_count"])

    def test_profile_change_produces_different_proposal_identity(self) -> None:
        extraction = _extraction()
        review = _review(extraction, "candidate-001", "approve", REVIEWED_AT)
        first_profile = _profile()
        second_profile = _profile()
        second_profile["profile"]["basic"]["locale"] = "en-US"

        first = build_profile_update_proposal(
            first_profile,
            extraction,
            [review],
            created_at=CREATED_AT,
        )
        second = build_profile_update_proposal(
            second_profile,
            extraction,
            [review],
            created_at=CREATED_AT,
        )

        self.assertNotEqual(
            first["profile_update_proposal"]["proposal_id"],
            second["profile_update_proposal"]["proposal_id"],
        )
        self.assertNotEqual(
            first["profile_update_proposal"]["base_profile_content_sha256"],
            second["profile_update_proposal"]["base_profile_content_sha256"],
        )

    def test_saves_and_reuses_identical_proposal(self) -> None:
        extraction = _extraction()
        review = _review(extraction, "candidate-001", "approve", REVIEWED_AT)
        first = build_profile_update_proposal(
            _profile(),
            extraction,
            [review],
            created_at=CREATED_AT,
        )
        second = build_profile_update_proposal(
            _profile(),
            extraction,
            [review],
            created_at=CREATED_AT + timedelta(days=1),
        )

        with tempfile.TemporaryDirectory() as directory:
            first_path, first_created = save_profile_update_proposal(first, directory)
            second_path, second_created = save_profile_update_proposal(second, directory)

        self.assertTrue(first_created)
        self.assertFalse(second_created)
        self.assertEqual(first_path, second_path)

    def test_rejects_tampered_existing_proposal(self) -> None:
        extraction = _extraction()
        review = _review(extraction, "candidate-001", "approve", REVIEWED_AT)
        proposal = build_profile_update_proposal(
            _profile(),
            extraction,
            [review],
            created_at=CREATED_AT,
        )

        with tempfile.TemporaryDirectory() as directory:
            path, _ = save_profile_update_proposal(proposal, directory)
            tampered = json.loads(path.read_text(encoding="utf-8"))
            tampered["proposed_additions"][0]["candidate_text"] = "변조"
            path.write_text(
                json.dumps(tampered, ensure_ascii=False),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ProfileDocumentError, "proposed_additions"):
                save_profile_update_proposal(proposal, directory)

    def test_rejects_naive_created_at(self) -> None:
        with self.assertRaisesRegex(ProfileDocumentError, "시간대"):
            build_profile_update_proposal(
                _profile(),
                _extraction(),
                [],
                created_at=datetime(2026, 9, 14, 18),
            )


if __name__ == "__main__":
    unittest.main()
