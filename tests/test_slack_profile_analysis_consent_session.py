from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from career_agent.interfaces import (  # noqa: E402
    build_slack_profile_analysis_consent_session,
    load_slack_profile_analysis_consent_session,
    save_slack_profile_analysis_consent_session,
    select_active_slack_profile_analysis_consent_session,
)
from career_agent.profile_input import (  # noqa: E402
    build_profile_analysis_external_consent,
    save_profile_analysis_external_consent,
)
from tests.test_profile_analysis_draft import _extraction  # noqa: E402


CREATED_AT = datetime(2026, 9, 22, 10, tzinfo=timezone.utc)
PROVIDER = "google-gemini-development"
MODEL = "gemini-3.5-flash-lite"


def _consent(extraction: dict, session: dict, *, decided_at: datetime) -> dict:
    source = session["source"]
    return build_profile_analysis_external_consent(
        extraction,
        provider_name=PROVIDER,
        model_name=MODEL,
        consent_session_id=session["slack_profile_analysis_consent_session"][
            "session_id"
        ],
        team_id=source["team_id"],
        channel_id=source["channel_id"],
        user_id=source["user_id"],
        thread_ts=source["thread_ts"],
        decision="approve",
        decided_at=decided_at,
    )


class SlackProfileAnalysisConsentSessionTest(unittest.TestCase):
    def test_session_is_thread_bound_and_closes_after_decision(self) -> None:
        extraction = _extraction()
        session = build_slack_profile_analysis_consent_session(
            extraction,
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372700.000900",
            provider_name=PROVIDER,
            model_name=MODEL,
            created_at=CREATED_AT,
        )
        with tempfile.TemporaryDirectory() as root:
            session_directory = Path(root) / "sessions"
            consent_directory = Path(root) / "consents"
            path = save_slack_profile_analysis_consent_session(
                session, session_directory
            )
            loaded = load_slack_profile_analysis_consent_session(
                path.stem, session_directory
            )
            active = select_active_slack_profile_analysis_consent_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                consent_directory=consent_directory,
            )
            wrong_user = select_active_slack_profile_analysis_consent_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U11111111",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                consent_directory=consent_directory,
            )
            consent = _consent(
                extraction,
                session,
                decided_at=CREATED_AT + timedelta(minutes=1),
            )
            save_profile_analysis_external_consent(consent, consent_directory)
            completed = select_active_slack_profile_analysis_consent_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                consent_directory=consent_directory,
            )

        self.assertEqual(session, loaded)
        self.assertEqual(session, active)
        self.assertIsNone(wrong_user)
        self.assertIsNone(completed)
        self.assertFalse(session["metadata"]["contains_candidate_text"])

    def test_one_users_decision_does_not_close_another_users_session(self) -> None:
        extraction = _extraction()
        first = build_slack_profile_analysis_consent_session(
            extraction,
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372700.000900",
            provider_name=PROVIDER,
            model_name=MODEL,
            created_at=CREATED_AT,
        )
        second = build_slack_profile_analysis_consent_session(
            extraction,
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U11111111",
            thread_ts="1789372700.000900",
            provider_name=PROVIDER,
            model_name=MODEL,
            created_at=CREATED_AT,
        )
        with tempfile.TemporaryDirectory() as root:
            session_directory = Path(root) / "sessions"
            consent_directory = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(first, session_directory)
            save_slack_profile_analysis_consent_session(second, session_directory)
            save_profile_analysis_external_consent(
                _consent(
                    extraction,
                    first,
                    decided_at=CREATED_AT + timedelta(minutes=1),
                ),
                consent_directory,
            )
            first_active = select_active_slack_profile_analysis_consent_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                consent_directory=consent_directory,
            )
            second_active = select_active_slack_profile_analysis_consent_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U11111111",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                consent_directory=consent_directory,
            )

        self.assertIsNone(first_active)
        self.assertEqual(second, second_active)

    def test_latest_same_thread_session_supersedes_older_session(self) -> None:
        extraction = _extraction()
        older = build_slack_profile_analysis_consent_session(
            extraction,
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372700.000900",
            provider_name=PROVIDER,
            model_name=MODEL,
            created_at=CREATED_AT,
        )
        latest = build_slack_profile_analysis_consent_session(
            extraction,
            team_id="T01234567",
            channel_id="C01234567",
            user_id="U76543210",
            thread_ts="1789372700.000900",
            provider_name=PROVIDER,
            model_name=MODEL,
            created_at=CREATED_AT + timedelta(minutes=1),
        )
        with tempfile.TemporaryDirectory() as root:
            session_directory = Path(root) / "sessions"
            consent_directory = Path(root) / "consents"
            save_slack_profile_analysis_consent_session(older, session_directory)
            save_slack_profile_analysis_consent_session(latest, session_directory)
            save_profile_analysis_external_consent(
                _consent(
                    extraction,
                    latest,
                    decided_at=CREATED_AT + timedelta(minutes=2),
                ),
                consent_directory,
            )
            active = select_active_slack_profile_analysis_consent_session(
                team_id="T01234567",
                channel_id="C01234567",
                user_id="U76543210",
                thread_ts="1789372700.000900",
                session_directory=session_directory,
                consent_directory=consent_directory,
            )

        self.assertIsNone(active)


if __name__ == "__main__":
    unittest.main()
