"""FastAPI application for the consumer-agnostic context substrate HTTP API."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from context_substrate.api.auth import build_auth_dependency
from context_substrate.api.schemas import (
    HealthResponse,
    ProjectionResponse,
    RecordItem,
    RecordsResponse,
    SearchHit,
    SearchRequest,
    SearchResponse,
    SyncResponse,
    format_utc,
)
from context_substrate.config import Settings
from context_substrate.models import SourceRecord, SyncCursor
from context_substrate.projections import (
    ProjectionEngine,
    ProjectionExtractor,
    ProjectionNotFoundError,
    ProjectionParameterError,
)
from context_substrate.search import TextEmbedder, hybrid_rank
from context_substrate.sync.discord_hub import ArchiveSyncer, DiscordHubArchiveClient

logger = logging.getLogger(__name__)


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _encode_cursor(created_at: datetime, record_id: str) -> str:
    payload = {
        "created_at": format_utc(created_at),
        "id": record_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        created_at_str = payload["created_at"]
        record_id = payload["id"]
        if not isinstance(created_at_str, str) or not isinstance(record_id, str):
            raise ValueError("Invalid cursor payload types")
        created_at = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
        return _to_utc(created_at), record_id
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid pagination cursor",
        ) from exc


def _apply_source_filter(
    stmt: Select[tuple[SourceRecord]], sources: list[str] | None
) -> Select[tuple[SourceRecord]]:
    if not sources:
        return stmt
    cleaned = [s.strip() for s in sources if s and s.strip()]
    if not cleaned:
        return stmt
    return stmt.where(
        or_(
            SourceRecord.source_name.in_(cleaned),
            SourceRecord.source_channel_id.in_(cleaned),
            SourceRecord.parent_channel_id.in_(cleaned),
        )
    )


def create_app(
    settings: Settings,
    session_factory: sessionmaker[Session],
    *,
    syncer: ArchiveSyncer | None = None,
    embedder: TextEmbedder | None = None,
    projection_extractor: ProjectionExtractor | None = None,
    projection_engine: ProjectionEngine | None = None,
    sync_lock: asyncio.Lock | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Context Substrate API",
        version="0.1.0",
    )

    require_consumer = build_auth_dependency(settings.consumer_tokens)
    active_sync_lock = sync_lock or asyncio.Lock()
    active_projection_engine = projection_engine or ProjectionEngine(
        session_factory,
        extractor=projection_extractor,
    )

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        with session_factory() as session:
            last_sync_at = session.execute(select(func.max(SyncCursor.last_synced_at))).scalar()
            record_count = session.execute(select(func.count(SourceRecord.id))).scalar() or 0
        return HealthResponse(
            status="ok",
            last_sync_at=format_utc(last_sync_at),
            record_count=int(record_count),
        )

    @app.get("/records", response_model=RecordsResponse)
    def list_records(
        _consumer: str = Depends(require_consumer),  # noqa: B008
        source: list[str] | None = Query(default=None),  # noqa: B008
        since: datetime | None = None,
        until: datetime | None = None,
        thread_id: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),  # noqa: B008
        cursor: str | None = None,
    ) -> RecordsResponse:
        stmt = select(SourceRecord)
        stmt = _apply_source_filter(stmt, source)

        if since is not None:
            stmt = stmt.where(SourceRecord.created_at >= _to_utc(since))
        if until is not None:
            stmt = stmt.where(SourceRecord.created_at <= _to_utc(until))
        if thread_id is not None:
            stmt = stmt.where(SourceRecord.thread_id == thread_id)

        if cursor is not None:
            cursor_dt, cursor_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    SourceRecord.created_at < cursor_dt,
                    and_(
                        SourceRecord.created_at == cursor_dt,
                        SourceRecord.id < cursor_id,
                    ),
                )
            )

        stmt = stmt.order_by(SourceRecord.created_at.desc(), SourceRecord.id.desc()).limit(
            limit + 1
        )

        with session_factory() as session:
            rows = list(session.execute(stmt).scalars().all())

        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = (
            _encode_cursor(page_rows[-1].created_at, page_rows[-1].id)
            if has_more and page_rows
            else None
        )

        return RecordsResponse(
            items=[RecordItem.from_orm_record(row) for row in page_rows],
            next_cursor=next_cursor,
        )

    @app.post("/search", response_model=SearchResponse)
    def search_records(
        body: SearchRequest,
        _consumer: str = Depends(require_consumer),  # noqa: B008
    ) -> SearchResponse:
        stmt = select(SourceRecord).where(SourceRecord.deleted.is_(False))
        stmt = _apply_source_filter(stmt, body.sources)

        if body.since is not None:
            stmt = stmt.where(SourceRecord.created_at >= _to_utc(body.since))
        if body.until is not None:
            stmt = stmt.where(SourceRecord.created_at <= _to_utc(body.until))

        with session_factory() as session:
            candidates = list(session.execute(stmt).scalars().all())

        ranked = hybrid_rank(
            body.query,
            candidates,
            embedder=embedder,
            semantic_weight=settings.search_semantic_weight,
            limit=body.limit,
        )
        return SearchResponse(
            hits=[
                SearchHit(score=hit.score, record=RecordItem.from_orm_record(hit.record))
                for hit in ranked
            ]
        )

    @app.post("/sync", response_model=SyncResponse)
    async def trigger_sync(
        consumer: str = Depends(require_consumer),  # noqa: B008
    ) -> SyncResponse:
        logger.info("Manual sync triggered by consumer=%s", consumer)
        async with active_sync_lock:
            if syncer is not None:
                result = await syncer.sync_all(channel_ids=settings.sync_channel_ids or None)
            else:
                async with DiscordHubArchiveClient(
                    settings.discord_hub_url,
                    settings.discord_hub_token,
                ) as client:
                    ephemeral_syncer = ArchiveSyncer(
                        client,
                        session_factory,
                        channel_names=settings.sync_channel_names,
                        messages_page_size=settings.sync_messages_page_size,
                        events_page_size=settings.sync_events_page_size,
                    )
                    result = await ephemeral_syncer.sync_all(
                        channel_ids=settings.sync_channel_ids or None
                    )

        return SyncResponse(
            synced_messages=result.synced_messages,
            synced_events=result.synced_events,
        )

    @app.get("/projections/{name}", response_model=ProjectionResponse)
    def get_projection(
        name: str,
        _consumer: str = Depends(require_consumer),  # noqa: B008
        days: int | None = Query(default=None, ge=1, le=3650),  # noqa: B008
        since: datetime | None = None,
        until: datetime | None = None,
        refresh: bool = False,
    ) -> ProjectionResponse:
        try:
            proj = active_projection_engine.get_projection(
                name,
                days=days,
                since=since,
                until=until,
                refresh=refresh,
            )
        except ProjectionNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
        except ProjectionParameterError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        return ProjectionResponse.from_orm_projection(proj)

    return app
