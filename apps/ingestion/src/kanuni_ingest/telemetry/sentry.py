"""Sentry error-tracking setup (§11, Phase 6) for the ingestion worker."""

import sentry_sdk


def configure_sentry(*, dsn: str, release: str) -> None:
    """Initialize the Sentry SDK, tagged with the deployed release.

    A blank ``dsn`` is Sentry's own documented way to disable the SDK
    (every call becomes a no-op) — callers never need to branch on
    whether Sentry is configured.

    Args:
        dsn: The Sentry project DSN (``Settings.sentry_dsn``), or ``""`` to disable.
        release: The deployed commit SHA (``Settings.release_sha``), for
            linking errors back to the exact code that produced them.
    """
    # GlitchTip (the default target — see docs/NEEDS.md) doesn't support
    # session tracking and explicitly asks integrators to disable it.
    sentry_sdk.init(dsn=dsn, release=release, auto_session_tracking=False)
