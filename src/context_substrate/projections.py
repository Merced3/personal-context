"""Rerunnable, evidence-backed projection storage and generation framework."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from context_substrate.models import ProjectionRecord, SourceRecord

PROJECTION_VERSION = "1"
SUPPORTED_PROJECTIONS: tuple[str, ...] = (
    "current_mission",
    "time_digest",
    "open_decisions",
    "book_lenses",
)

DEFAULT_MISSION_RECENT_DAYS = 30
DEFAULT_TIME_DIGEST_DAYS = 7

_PREDICTION_RE = re.compile(r"(?im)^prediction\s*:\s*(.+)$")
_CHECK_BACK_RE = re.compile(r"(?im)^check[- ]?back(?:\s+date)?\s*:\s*(.+)$")


class ProjectionNotFoundError(KeyError):
    """Raised when an unknown projection name is requested."""


class ProjectionParameterError(ValueError):
    """Raised when invalid query parameters are supplied to a projection."""


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """Output of a projection extractor / LLM."""

    model: str
    data: dict[str, Any]
    source_record_ids: list[str]


class ProjectionExtractor(Protocol):
    """Pluggable extractor (LLM or deterministic) for distilling synced records."""

    def extract(
        self,
        projection_name: str,
        records: list[SourceRecord],
        *,
        params: dict[str, Any],
    ) -> ExtractionResult: ...


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _format_utc(dt: datetime) -> str:
    return _to_utc(dt).isoformat().replace("+00:00", "Z")


def _record_tags(record: SourceRecord) -> list[str]:
    if not record.tags_json:
        return []
    try:
        parsed = json.loads(record.tags_json)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [str(t) for t in parsed]


def _sanitize_citations(
    data: Any,
    top_level_ids: list[str],
    allowed_ids: set[str],
) -> tuple[Any, list[str]]:
    """Enforce citation integrity: strip any ID not in allowed_ids and collect union."""
    collected: list[str] = []
    seen: set[str] = set()

    def _record_valid(raw_ids: Iterable[Any]) -> list[str]:
        cleaned: list[str] = []
        local_seen: set[str] = set()
        for item in raw_ids:
            rid = str(item)
            if rid in allowed_ids and rid not in local_seen:
                cleaned.append(rid)
                local_seen.add(rid)
                if rid not in seen:
                    collected.append(rid)
                    seen.add(rid)
        return cleaned

    def _walk(node: Any) -> Any:
        if isinstance(node, dict):
            out: dict[str, Any] = {}
            for k, v in node.items():
                if k == "source_record_ids" and isinstance(v, list):
                    out[k] = _record_valid(v)
                else:
                    out[k] = _walk(v)
            return out
        if isinstance(node, list):
            return [_walk(item) for item in node]
        return node

    sanitized_data = _walk(data)
    _record_valid(top_level_ids)
    return sanitized_data, collected


class DeterministicProjectionExtractor:
    """Built-in offline extractor producing structured, cited projections without an LLM."""

    model_name: str = "deterministic-extractor-v1"

    def extract(
        self,
        projection_name: str,
        records: list[SourceRecord],
        *,
        params: dict[str, Any],
    ) -> ExtractionResult:
        if projection_name == "current_mission":
            return self._extract_current_mission(records, params=params)
        if projection_name == "time_digest":
            return self._extract_time_digest(records, params=params)
        if projection_name == "open_decisions":
            return self._extract_open_decisions(records)
        if projection_name == "book_lenses":
            return self._extract_book_lenses(records)
        raise ProjectionNotFoundError(f"Unknown projection: {projection_name}")

    def _extract_current_mission(
        self, records: list[SourceRecord], *, params: dict[str, Any]
    ) -> ExtractionResult:
        mission_statements: list[dict[str, Any]] = []
        recent_signals: list[dict[str, Any]] = []
        cited: list[str] = []

        for rec in records:
            cited.append(rec.id)
            if rec.source_name == "mission":
                mission_statements.append(
                    {
                        "text": rec.content,
                        "created_at": _format_utc(rec.created_at),
                        "source_record_ids": [rec.id],
                    }
                )
            else:
                recent_signals.append(
                    {
                        "source_name": rec.source_name or rec.source_channel_id,
                        "summary": rec.content,
                        "created_at": _format_utc(rec.created_at),
                        "source_record_ids": [rec.id],
                    }
                )

        return ExtractionResult(
            model=self.model_name,
            data={
                "window_days": params.get("days", DEFAULT_MISSION_RECENT_DAYS),
                "mission_statements": mission_statements,
                "recent_signals": recent_signals,
            },
            source_record_ids=cited,
        )

    def _extract_time_digest(
        self, records: list[SourceRecord], *, params: dict[str, Any]
    ) -> ExtractionResult:
        by_source: dict[str, dict[str, Any]] = {}
        cited: list[str] = []

        for rec in records:
            cited.append(rec.id)
            source_key = rec.source_name or rec.source_channel_id
            bucket = by_source.setdefault(source_key, {"count": 0, "highlights": []})
            bucket["count"] += 1
            bucket["highlights"].append(
                {
                    "content": rec.content,
                    "created_at": _format_utc(rec.created_at),
                    "source_record_ids": [rec.id],
                }
            )

        return ExtractionResult(
            model=self.model_name,
            data={
                "window": {
                    "since": params["since"],
                    "until": params["until"],
                    "days": params.get("days"),
                },
                "record_count": len(records),
                "by_source": by_source,
            },
            source_record_ids=cited,
        )

    def _extract_open_decisions(self, records: list[SourceRecord]) -> ExtractionResult:
        grouped: dict[str, list[SourceRecord]] = defaultdict(list)
        for rec in records:
            group_key = rec.thread_id or rec.id
            grouped[group_key].append(rec)

        decisions: list[dict[str, Any]] = []
        cited: list[str] = []

        for _group_key, group_records in grouped.items():
            ordered = sorted(group_records, key=lambda r: (_to_utc(r.created_at), r.id))
            combined_text = "\n".join(r.content for r in ordered if r.content)
            pred_match = _PREDICTION_RE.search(combined_text)
            check_match = _CHECK_BACK_RE.search(combined_text)
            first = ordered[0]
            rec_ids = [r.id for r in ordered]
            cited.extend(rec_ids)

            title = first.thread_title or (
                first.content.splitlines()[0][:120] if first.content else first.id
            )
            decisions.append(
                {
                    "title": title,
                    "status": "pending",
                    "summary": combined_text,
                    "prediction": pred_match.group(1).strip() if pred_match else None,
                    "check_back_date": check_match.group(1).strip() if check_match else None,
                    "created_at": _format_utc(first.created_at),
                    "source_record_ids": rec_ids,
                }
            )

        return ExtractionResult(
            model=self.model_name,
            data={"decisions": decisions},
            source_record_ids=cited,
        )

    def _extract_book_lenses(self, records: list[SourceRecord]) -> ExtractionResult:
        book_groups: dict[str, list[SourceRecord]] = defaultdict(list)
        quotes: list[dict[str, Any]] = []
        cited: list[str] = []

        for rec in records:
            cited.append(rec.id)
            if rec.source_name == "quotes-i-like":
                quotes.append(
                    {
                        "text": rec.content,
                        "created_at": _format_utc(rec.created_at),
                        "source_record_ids": [rec.id],
                    }
                )
            else:
                group_key = rec.thread_id or rec.id
                book_groups[group_key].append(rec)

        lenses: list[dict[str, Any]] = []
        for _group_key, group_records in book_groups.items():
            ordered = sorted(group_records, key=lambda r: (_to_utc(r.created_at), r.id))
            first = ordered[0]
            title = first.thread_title or (
                first.content.splitlines()[0][:120] if first.content else first.id
            )
            lenses.append(
                {
                    "title": title,
                    "notes": [r.content for r in ordered if r.content],
                    "source_record_ids": [r.id for r in ordered],
                }
            )

        return ExtractionResult(
            model=self.model_name,
            data={"lenses": lenses, "quotes": quotes},
            source_record_ids=cited,
        )


def invalidate_projections_citing(session: Session, record_ids: Iterable[str]) -> int:
    """Delete any stored projections that cite one or more of the given record IDs."""
    removed_set = {str(rid) for rid in record_ids if rid}
    if not removed_set:
        return 0

    projections = list(session.execute(select(ProjectionRecord)).scalars().all())
    invalidated = 0
    for proj in projections:
        try:
            cited = json.loads(proj.source_record_ids_json) if proj.source_record_ids_json else []
        except json.JSONDecodeError:
            cited = []
        if any(str(cid) in removed_set for cid in cited):
            session.delete(proj)
            invalidated += 1
    return invalidated


class ProjectionEngine:
    """Manages storage, citation integrity, invalidation, and rebuilds for projections."""

    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        extractor: ProjectionExtractor | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._extractor: ProjectionExtractor = extractor or DeterministicProjectionExtractor()

    def get_projection(
        self,
        name: str,
        *,
        days: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        refresh: bool = False,
        now: datetime | None = None,
    ) -> ProjectionRecord:
        if name not in SUPPORTED_PROJECTIONS:
            raise ProjectionNotFoundError(f"Unknown projection: {name}")

        current_time = _to_utc(now or datetime.now(UTC))
        cache_key, params = self._resolve_params(
            name, days=days, since=since, until=until, now=current_time
        )

        with self._session_factory() as session:
            existing = session.execute(
                select(ProjectionRecord).where(
                    ProjectionRecord.name == name,
                    ProjectionRecord.cache_key == cache_key,
                )
            ).scalar_one_or_none()

            if (
                existing is not None
                and not refresh
                and self._citations_are_valid(session, existing)
            ):
                return existing

            records = self._load_source_records(session, name, params=params)
            allowed_ids = {r.id for r in records}
            result = self._extractor.extract(name, records, params=params)
            sanitized_data, valid_cited_ids = _sanitize_citations(
                result.data,
                result.source_record_ids,
                allowed_ids,
            )

            if existing is None:
                existing = ProjectionRecord(
                    name=name,
                    cache_key=cache_key,
                    version=PROJECTION_VERSION,
                    generated_at=current_time,
                    model=result.model,
                    data_json=json.dumps(sanitized_data),
                    source_record_ids_json=json.dumps(valid_cited_ids),
                )
                session.add(existing)
            else:
                existing.version = PROJECTION_VERSION
                existing.generated_at = current_time
                existing.model = result.model
                existing.data_json = json.dumps(sanitized_data)
                existing.source_record_ids_json = json.dumps(valid_cited_ids)

            session.commit()
            session.refresh(existing)
            return existing

    def clear_all(self) -> int:
        """Delete all stored projections so they can be rebuilt from scratch."""
        with self._session_factory() as session:
            result = session.execute(delete(ProjectionRecord))
            session.commit()
            return int(result.rowcount or 0)

    def _resolve_params(
        self,
        name: str,
        *,
        days: int | None,
        since: datetime | None,
        until: datetime | None,
        now: datetime,
    ) -> tuple[str, dict[str, Any]]:
        if name == "time_digest":
            if days is not None and (since is not None or until is not None):
                raise ProjectionParameterError(
                    "Specify either 'days' or 'since'/'until', not both."
                )
            if since is not None or until is not None:
                resolved_until = _to_utc(until) if until is not None else now
                resolved_since = (
                    _to_utc(since)
                    if since is not None
                    else resolved_until - timedelta(days=DEFAULT_TIME_DIGEST_DAYS)
                )
                if resolved_since > resolved_until:
                    raise ProjectionParameterError("'since' must be <= 'until'.")
                since_str = _format_utc(resolved_since)
                until_str = _format_utc(resolved_until)
                return (
                    f"since={since_str}&until={until_str}",
                    {
                        "since": since_str,
                        "until": until_str,
                        "since_dt": resolved_since,
                        "until_dt": resolved_until,
                        "days": None,
                    },
                )

            resolved_days = days if days is not None else DEFAULT_TIME_DIGEST_DAYS
            resolved_until = now
            resolved_since = now - timedelta(days=resolved_days)
            return (
                f"days={resolved_days}",
                {
                    "since": _format_utc(resolved_since),
                    "until": _format_utc(resolved_until),
                    "since_dt": resolved_since,
                    "until_dt": resolved_until,
                    "days": resolved_days,
                },
            )

        if name == "current_mission":
            resolved_days = days if days is not None else DEFAULT_MISSION_RECENT_DAYS
            recent_since = now - timedelta(days=resolved_days)
            cache_key = "default" if days is None else f"days={resolved_days}"
            return (
                cache_key,
                {
                    "days": resolved_days,
                    "recent_since_dt": recent_since,
                },
            )

        return "default", {}

    def _citations_are_valid(self, session: Session, proj: ProjectionRecord) -> bool:
        try:
            cited_ids = (
                json.loads(proj.source_record_ids_json) if proj.source_record_ids_json else []
            )
        except json.JSONDecodeError:
            return False
        if not cited_ids:
            return True

        existing_ids = set(
            session.execute(
                select(SourceRecord.id).where(
                    SourceRecord.id.in_(cited_ids),
                    SourceRecord.deleted.is_(False),
                )
            )
            .scalars()
            .all()
        )
        return all(cid in existing_ids for cid in cited_ids)

    def _load_source_records(
        self,
        session: Session,
        name: str,
        *,
        params: dict[str, Any],
    ) -> list[SourceRecord]:
        base = select(SourceRecord).where(SourceRecord.deleted.is_(False))

        if name == "current_mission":
            mission_rows = list(
                session.execute(
                    base.where(SourceRecord.source_name == "mission").order_by(
                        SourceRecord.created_at.desc(), SourceRecord.id.desc()
                    )
                )
                .scalars()
                .all()
            )
            recent_rows = list(
                session.execute(
                    base.where(
                        SourceRecord.source_name.in_(["my-timeline", "reviews"]),
                        SourceRecord.created_at >= params["recent_since_dt"],
                    ).order_by(SourceRecord.created_at.desc(), SourceRecord.id.desc())
                )
                .scalars()
                .all()
            )
            return mission_rows + recent_rows

        if name == "time_digest":
            return list(
                session.execute(
                    base.where(
                        SourceRecord.created_at >= params["since_dt"],
                        SourceRecord.created_at <= params["until_dt"],
                    ).order_by(SourceRecord.created_at.desc(), SourceRecord.id.desc())
                )
                .scalars()
                .all()
            )

        if name == "open_decisions":
            decision_rows = list(
                session.execute(
                    base.where(SourceRecord.source_name == "decisions").order_by(
                        SourceRecord.created_at.desc(), SourceRecord.id.desc()
                    )
                )
                .scalars()
                .all()
            )
            # Include records in threads (or standalone posts) tagged "pending"
            pending_threads: set[str] = set()
            pending_standalone: set[str] = set()
            for rec in decision_rows:
                tags_lower = {t.lower() for t in _record_tags(rec)}
                if "pending" in tags_lower:
                    if rec.thread_id:
                        pending_threads.add(rec.thread_id)
                    else:
                        pending_standalone.add(rec.id)
            return [
                rec
                for rec in decision_rows
                if (rec.thread_id and rec.thread_id in pending_threads)
                or rec.id in pending_standalone
            ]

        if name == "book_lenses":
            return list(
                session.execute(
                    base.where(SourceRecord.source_name.in_(["books", "quotes-i-like"])).order_by(
                        SourceRecord.created_at.desc(), SourceRecord.id.desc()
                    )
                )
                .scalars()
                .all()
            )

        raise ProjectionNotFoundError(f"Unknown projection: {name}")
