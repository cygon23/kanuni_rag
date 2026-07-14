"""Ingestion worker process entry point: `python -m kanuni_ingest`."""

import asyncio

import structlog

logger = structlog.get_logger()


async def main() -> None:
    """Start the ingestion worker process and idle.

    No pipeline stages are implemented yet (see PROJECT_SPEC.md Phase 1);
    this only confirms the worker process starts and stays up.
    """
    logger.info("kanuni_ingest_worker_started")
    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
