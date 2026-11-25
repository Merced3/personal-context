"""automation-harness runtime integration (lock, graceful shutdown, scheduled sync, HTTP API)."""

from __future__ import annotations

import asyncio
import logging

import uvicorn
from automation_harness import Harness, HarnessConfig, JobContext, ServiceContext
from sqlalchemy.orm import Session, sessionmaker

from context_substrate.api.app import create_app
from context_substrate.config import Settings
from context_substrate.db import build_engine, build_session_factory
from context_substrate.search import TextEmbedder
from context_substrate.sync.discord_hub import ArchiveSyncer, DiscordHubArchiveClient

logger = logging.getLogger(__name__)


def build_harness(
    settings: Settings,
    session_factory: sessionmaker[Session] | None = None,
    *,
    syncer: ArchiveSyncer | None = None,
    embedder: TextEmbedder | None = None,
    name: str = "context-substrate",
) -> Harness:
    """Build an automation-harness instance hosting both the HTTP API and background sync."""
    if session_factory is None:
        engine = build_engine(settings.database_url)
        session_factory = build_session_factory(engine)

    sync_lock = asyncio.Lock()
    app = create_app(
        settings,
        session_factory,
        syncer=syncer,
        embedder=embedder,
        sync_lock=sync_lock,
    )

    harness_config = HarnessConfig(
        data_dir=settings.harness_data_dir,
        database_url=settings.harness_database_url,
    )
    harness = Harness(harness_config, name=name)

    async def archive_sync_job(ctx: JobContext) -> None:
        async with sync_lock:
            if syncer is not None:
                result = await syncer.sync_all(channel_ids=settings.sync_channel_ids or None)
            else:
                async with DiscordHubArchiveClient(
                    settings.discord_hub_url,
                    settings.discord_hub_token,
                ) as client:
                    job_syncer = ArchiveSyncer(
                        client,
                        session_factory,
                        channel_names=settings.sync_channel_names,
                        messages_page_size=settings.sync_messages_page_size,
                        events_page_size=settings.sync_events_page_size,
                    )
                    result = await job_syncer.sync_all(
                        channel_ids=settings.sync_channel_ids or None
                    )

        summary = {
            "synced_messages": result.synced_messages,
            "synced_events": result.synced_events,
            "removed_locked": result.removed_locked,
        }
        ctx.set_state("last_sync_summary", summary)
        logger.info("Scheduled archive sync completed: %s", summary)

    async def http_api_service(ctx: ServiceContext) -> None:
        config = uvicorn.Config(
            app=app,
            host=settings.api_host,
            port=settings.api_port,
            log_config=None,
            access_log=False,
        )
        server = uvicorn.Server(config)
        # Let automation-harness own SIGINT/SIGTERM handling.
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

        serve_task = asyncio.create_task(server.serve())
        stop_task = asyncio.create_task(ctx.stop_event.wait())
        try:
            done, _ = await asyncio.wait(
                {serve_task, stop_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done:
                server.should_exit = True
                await serve_task
            else:
                stop_task.cancel()
                # Propagate any server startup/runtime error to the harness supervisor.
                await serve_task
        finally:
            if not stop_task.done():
                stop_task.cancel()

    harness.add_job(
        "archive_sync",
        archive_sync_job,
        every_s=settings.sync_interval_seconds,
        run_immediately=True,
    )
    harness.add_service(
        "http_api",
        http_api_service,
        backoff_max_s=60,
    )
    return harness


def run_service(settings: Settings | None = None) -> None:
    """Entry point: load settings, build harness, and run until SIGINT/SIGTERM."""
    active_settings = settings or Settings()
    harness = build_harness(active_settings)
    harness.run()
