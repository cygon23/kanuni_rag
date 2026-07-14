"""Structlog configuration producing JSON log lines enriched with request-scoped context."""

import logging
import sys

import structlog

from kanuni_api.config import LogLevel


def configure_logging(log_level: LogLevel) -> None:
    """Configure structlog (and the stdlib logging root logger) to emit JSON log lines.

    Every log line is enriched with any context bound via
    ``structlog.contextvars`` (notably ``request_id``, bound by
    :class:`kanuni_api.middleware.request_id.RequestIDMiddleware`).

    Args:
        log_level: Minimum level to log at, e.g. ``"info"``.
    """
    numeric_level = getattr(logging, log_level.upper())
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=numeric_level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
