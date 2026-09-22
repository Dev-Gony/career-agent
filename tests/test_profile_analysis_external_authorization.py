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

from career_agent.interfaces import (  # noqa: E402
    build_slack_profile_analysis_consent_session,
    save_slack_profile_analysis_consent_session,
)
from career_agent.profile_input import (  # noqa: E402
    ProfileDocumentError,
    build_profile_analysis_external_consent,
    require_approved_profile_analysis_external_consent,
    save_profile_analysis_external_consent,
)
from tests.test_profile_analysis_draft import _extraction  # noqa: E402


CREATED_AT = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)
PROVIDER = "google-gemini-development"
MODEL = "gemini-3.5-flash-lite"
SOURCE = {
    "team_id": "T01234567",
    "channel_id": "C01234567",
    "user_id": "U76543210",
    "thread_ts": "1789372700.000900",
}


def _session(extraction: dict, *, created_at: datetime, model_name: str = MODEL) -> dict:
    return build_slack_profile_analysis_consent_session(
        extraction,
        provider_name=PROVIDER,
        model_name=model_name,
        created_at=created_at,
        **SOURCE,
    )


def _consent(
    extraction: dict,
    session: dict,
    *,
    decision: str,
    decided_at: datetime,
) -> dict:
    session_id = session["slack_profile_analysis_consent_session"]["session_id"]
    return build_profile_analysis_external_consent(
        extraction,
        provider_name=PROVIDER,
        model_name=session["target"]["model_name"],
        consent_session_id=session_id,
        decision=decision,
        decided_at=decided_at,
        **SOURCE,
    )


class ProfileAnalysisExternalAuthorizationTest(unittest.TestCase):
    def test_selects_latest_approval_within_exact_slack_actor_scope(self) -> None:
        extraction = _extraction()
        own_session = _session(extraction, created_at=CREATED_AT)
        own_consent = _consent(
            extraction,
            own_session,
            decision="approve",
            decided_at=CREATED_AT + timedelta(minutes=1),
        )
        other_source = {
            **SOURCE,
            "channel_id": "C99999999",
            "user_id": "U99999999",
        }
        other_session = build_slack_profile_analysis_consent_session(
            extraction,
            provider_name=PROVIDER,
            model_name=MODEL,
            created_at=CREATED_AT + timedelta(minutes=2),
            **other_source,
        )
        other_consent = build_profile_analysis_external_consent(
            extraction,
            provider_name=PROVIDER,
            model_name=MODEL,
            consent_session_id=other_session[
                "slack_profile_analysis_consent_session"
            ]["session_id"],
            decision="approve",
            decided_at=CREATED_AT + timedelta(minutes=3),
            **other_source,
        )
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(own_session, sessions)
            save_slack_profile_analysis_consent_session(other_session, sessions)
            save_profile_analysis_external_consent(own_consent, consents)
            save_profile_analysis_external_consent(other_consent, consents)

            selected = require_approved_profile_analysis_external_consent(
                extraction,
                provider_name=PROVIDER,
                model_name=MODEL,
                session_directory=sessions,
                consent_directory=consents,
                team_id=SOURCE["team_id"],
                channel_id=SOURCE["channel_id"],
                user_id=SOURCE["user_id"],
            )

        self.assertEqual(own_consent, selected)

    def test_returns_exact_latest_session_approval_without_candidate_text(self) -> None:
        extraction = _extraction()
        session = _session(extraction, created_at=CREATED_AT)
        consent = _consent(
            extraction,
            session,
            decision="approve",
            decided_at=CREATED_AT + timedelta(minutes=1),
        )
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(session, sessions)
            save_profile_analysis_external_consent(consent, consents)

            selected = require_approved_profile_analysis_external_consent(
                extraction,
                provider_name=PROVIDER,
                model_name=MODEL,
                session_directory=sessions,
                consent_directory=consents,
            )

        serialized = json.dumps(selected, ensure_ascii=False)
        self.assertEqual(consent, selected)
        self.assertNotIn(extraction["candidates"][0]["text"], serialized)
        self.assertFalse(selected["metadata"]["contains_candidate_text"])

    def test_rejects_latest_explicit_rejection(self) -> None:
        extraction = _extraction()
        session = _session(extraction, created_at=CREATED_AT)
        rejection = _consent(
            extraction,
            session,
            decision="reject",
            decided_at=CREATED_AT + timedelta(minutes=1),
        )
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(session, sessions)
            save_profile_analysis_external_consent(rejection, consents)
            with self.assertRaisesRegex(ProfileDocumentError, "승인이 아님"):
                require_approved_profile_analysis_external_consent(
                    extraction,
                    provider_name=PROVIDER,
                    model_name=MODEL,
                    session_directory=sessions,
                    consent_directory=consents,
                )

    def test_rejects_pending_latest_session_even_when_older_session_was_approved(self) -> None:
        extraction = _extraction()
        approved_session = _session(extraction, created_at=CREATED_AT)
        pending_session = _session(
            extraction, created_at=CREATED_AT + timedelta(minutes=2)
        )
        approval = _consent(
            extraction,
            approved_session,
            decision="approve",
            decided_at=CREATED_AT + timedelta(minutes=1),
        )
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(approved_session, sessions)
            save_slack_profile_analysis_consent_session(pending_session, sessions)
            save_profile_analysis_external_consent(approval, consents)
            with self.assertRaisesRegex(ProfileDocumentError, "사용자 결정이 없음"):
                require_approved_profile_analysis_external_consent(
                    extraction,
                    provider_name=PROVIDER,
                    model_name=MODEL,
                    session_directory=sessions,
                    consent_directory=consents,
                )

    def test_rejects_approval_for_different_model_or_request(self) -> None:
        extraction = _extraction()
        other_model_session = _session(
            extraction,
            created_at=CREATED_AT,
            model_name="gemini-2.5-flash-lite",
        )
        other_model_approval = _consent(
            extraction,
            other_model_session,
            decision="approve",
            decided_at=CREATED_AT + timedelta(minutes=1),
        )
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(other_model_session, sessions)
            save_profile_analysis_external_consent(other_model_approval, consents)
            with self.assertRaisesRegex(ProfileDocumentError, "맞는.*세션이 없음"):
                require_approved_profile_analysis_external_consent(
                    extraction,
                    provider_name=PROVIDER,
                    model_name=MODEL,
                    session_directory=sessions,
                    consent_directory=consents,
                )

        changed = deepcopy(extraction)
        changed["candidates"][0]["text"] += " 변경"
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            session = _session(extraction, created_at=CREATED_AT)
            approval = _consent(
                extraction,
                session,
                decision="approve",
                decided_at=CREATED_AT + timedelta(minutes=1),
            )
            save_slack_profile_analysis_consent_session(session, sessions)
            save_profile_analysis_external_consent(approval, consents)
            with self.assertRaisesRegex(ProfileDocumentError, "맞는.*세션이 없음"):
                require_approved_profile_analysis_external_consent(
                    changed,
                    provider_name=PROVIDER,
                    model_name=MODEL,
                    session_directory=sessions,
                    consent_directory=consents,
                )

    def test_rejects_tampered_session_before_reading_approval(self) -> None:
        extraction = _extraction()
        session = _session(extraction, created_at=CREATED_AT)
        with tempfile.TemporaryDirectory() as root:
            sessions = Path(root) / "sessions"
            consents = Path(root) / "consents"
            path = save_slack_profile_analysis_consent_session(session, sessions)
            tampered = deepcopy(session)
            tampered["target"]["request_sha256"] = "0" * 64
            path.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaisesRegex(ProfileDocumentError, "지문"):
                require_approved_profile_analysis_external_consent(
                    extraction,
                    provider_name=PROVIDER,
                    model_name=MODEL,
                    session_directory=sessions,
                    consent_directory=consents,
                )


if __name__ == "__main__":
    unittest.main()
