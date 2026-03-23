"""Persistence layer for Soccer Player Tracker using SQLAlchemy + SQLite."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import DateTime, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from backend.errors import PersistenceError
from backend.models import PlayerRef, Position, SessionSummary, StatsReport

# ---------------------------------------------------------------------------
# ORM model
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


class SessionRecord(Base):
    """SQLAlchemy ORM model for a persisted analysis session."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    video_source: Mapped[str] = mapped_column(String, nullable=False)
    player_ref_json: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[str] = mapped_column(String, nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)


# ---------------------------------------------------------------------------
# SessionStore
# ---------------------------------------------------------------------------

_DEFAULT_DB_URL = "sqlite:///" + str(Path("~/.soccer-tracker/sessions.db").expanduser())


class SessionStore:
    """CRUD interface for persisted analysis sessions."""

    def __init__(self, db_url: Optional[str] = None) -> None:
        url = db_url or _DEFAULT_DB_URL
        # Expand ~ in file-based SQLite URLs
        if url.startswith("sqlite:///") and "~" in url:
            expanded = str(Path(url[len("sqlite:///"):]).expanduser())
            url = "sqlite:///" + expanded

        # Ensure the directory exists for file-based databases
        if url.startswith("sqlite:///") and url != "sqlite:///:memory:":
            db_path = Path(url[len("sqlite:///"):])
            try:
                db_path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise PersistenceError(f"Cannot create storage directory: {exc}") from exc

        try:
            self._engine = create_engine(url, echo=False)
            Base.metadata.create_all(self._engine)
        except Exception as exc:
            raise PersistenceError(f"Cannot initialise database: {exc}") from exc

    # ------------------------------------------------------------------
    # Public CRUD methods
    # ------------------------------------------------------------------

    def save_session(self, report: StatsReport) -> str:
        """Persist a StatsReport and return its session_id."""
        try:
            record = SessionRecord(
                id=report.session_id,
                created_at=report.created_at,
                video_source=report.video_source,
                player_ref_json=report.player_ref.model_dump_json(),
                position=report.position.value,
                report_json=report.model_dump_json(),
            )
            with Session(self._engine) as session:
                session.merge(record)  # upsert by primary key
                session.commit()
            return report.session_id
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Failed to save session: {exc}") from exc

    def list_sessions(self) -> list[SessionSummary]:
        """Return all sessions ordered by created_at descending."""
        try:
            stmt = select(SessionRecord).order_by(SessionRecord.created_at.desc())
            with Session(self._engine) as session:
                records = session.scalars(stmt).all()
            return [_record_to_summary(r) for r in records]
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Failed to list sessions: {exc}") from exc

    def load_session(self, session_id: str) -> StatsReport:
        """Load and deserialise a StatsReport by session_id."""
        try:
            with Session(self._engine) as session:
                record = session.get(SessionRecord, session_id)
            if record is None:
                raise PersistenceError(f"Session not found: {session_id}")
            return StatsReport.model_validate_json(record.report_json)
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Failed to load session: {exc}") from exc

    def delete_session(self, session_id: str) -> None:
        """Delete a session by session_id; raises PersistenceError if not found."""
        try:
            with Session(self._engine) as session:
                record = session.get(SessionRecord, session_id)
                if record is None:
                    raise PersistenceError(f"Session not found: {session_id}")
                session.delete(record)
                session.commit()
        except PersistenceError:
            raise
        except Exception as exc:
            raise PersistenceError(f"Failed to delete session: {exc}") from exc


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _record_to_summary(record: SessionRecord) -> SessionSummary:
    player_ref = PlayerRef.model_validate_json(record.player_ref_json)
    return SessionSummary(
        session_id=record.id,
        created_at=record.created_at,
        video_source=record.video_source,
        player_ref=player_ref,
        position=Position(record.position),
    )


# ---------------------------------------------------------------------------
# Module-level convenience API (lazily-initialised default store)
# ---------------------------------------------------------------------------

_default_store: Optional[SessionStore] = None


def _get_default_store() -> SessionStore:
    global _default_store
    if _default_store is None:
        _default_store = SessionStore()
    return _default_store


def save_session(report: StatsReport) -> str:
    """Save a session using the default store."""
    return _get_default_store().save_session(report)


def list_sessions() -> list[SessionSummary]:
    """List sessions using the default store."""
    return _get_default_store().list_sessions()


def load_session(session_id: str) -> StatsReport:
    """Load a session using the default store."""
    return _get_default_store().load_session(session_id)


def delete_session(session_id: str) -> None:
    """Delete a session using the default store."""
    _get_default_store().delete_session(session_id)
