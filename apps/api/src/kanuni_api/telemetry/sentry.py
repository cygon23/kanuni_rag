"""Sentry error-tracking setup (§11, Phase 6): API errors, tagged with the deployed release."""

import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from kanuni_api.config import Environment


def configure_sentry(*, dsn: str, environment: Environment, release: str) -> None:
    """Initialize the Sentry SDK, tagged with environment and release.

    A blank ``dsn`` is Sentry's own documented way to disable the SDK
    (every call becomes a no-op) — callers never need to branch on
    whether Sentry is configured.

    Args:
        dsn: The Sentry project DSN (``Settings.sentry_dsn``), or ``""`` to disable.
        environment: The deployment environment, for filtering in Sentry's UI.
        release: The deployed commit SHA (``Settings.release_sha``), for
            linking errors back to the exact code that produced them.
    """
    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        # GlitchTip (the default target — see docs/NEEDS.md) doesn't
        # support session tracking and explicitly asks integrators to
        # disable it. A low traces_sample_rate gives free baseline
        # latency data from the two integrations above without the cost
        # of tracing every request.
        auto_session_tracking=False,
        traces_sample_rate=0.01,
    )
