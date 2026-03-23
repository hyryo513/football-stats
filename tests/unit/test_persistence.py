"""Unit tests for backend/persistence.py."""

from __future__ import annotations

import pytest

from backend.errors import PersistenceError
from backend.models import Position, StatsReport
from backend.persistence import SessionStore


@pytest.fixture
def store(db_engine):
    """SessionStore backed by the in-memory SQLite fixture."""
    return SessionStore(db_url="sqlite:///:memory:")


# ---------------------------------------------------------------------------
# save_session / load_session
# ---------------------------------------------------------------------------


def test_save_and_load_round_trip(store, sample_stats_report):
    session_id = store.save_session(sample_stats_report)
    assert session_id == sample_stats_report.session_id

    loaded = store.load_session(session_id)
    assert loaded.session_id == sample_stats_report.session_id
    assert loaded.video_source == sample_stats_report.video_source
    assert loaded.position == sample_stats_report.position
    assert loaded.core.touch_count == sample_stats_report.core.touch_count


def test_load_nonexistent_raises(store):
    with pytest.raises(PersistenceError, match="not found"):
        store.load_session("does-not-exist")


def test_save_upserts_existing(store, sample_stats_report):
    store.save_session(sample_stats_report)
    # Save again (same session_id) — should not raise
    store.save_session(sample_stats_report)
    assert len(store.list_sessions()) == 1


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------


def test_list_sessions_empty(store):
    assert store.list_sessions() == []


def test_list_sessions_returns_summaries(store, stats_report_factory):
    r1 = stats_report_factory(session_id="s1")
    r2 = stats_report_factory(session_id="s2")
    store.save_session(r1)
    store.save_session(r2)

    summaries = store.list_sessions()
    ids = [s.session_id for s in summaries]
    assert "s1" in ids
    assert "s2" in ids


def test_list_sessions_ordered_by_created_at_desc(store, stats_report_factory):
    from datetime import datetime, timedelta, timezone

    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    r_old = stats_report_factory(session_id="old")
    r_new = stats_report_factory(session_id="new")
    # Patch created_at so we have a deterministic order
    object.__setattr__(r_old, "created_at", base)
    object.__setattr__(r_new, "created_at", base + timedelta(hours=1))

    store.save_session(r_old)
    store.save_session(r_new)

    summaries = store.list_sessions()
    assert summaries[0].session_id == "new"
    assert summaries[1].session_id == "old"


# ---------------------------------------------------------------------------
# delete_session
# ---------------------------------------------------------------------------


def test_delete_removes_session(store, sample_stats_report):
    store.save_session(sample_stats_report)
    store.delete_session(sample_stats_report.session_id)
    assert store.list_sessions() == []


def test_delete_nonexistent_raises(store):
    with pytest.raises(PersistenceError, match="not found"):
        store.delete_session("ghost-session")


def test_load_after_delete_raises(store, sample_stats_report):
    store.save_session(sample_stats_report)
    store.delete_session(sample_stats_report.session_id)
    with pytest.raises(PersistenceError, match="not found"):
        store.load_session(sample_stats_report.session_id)


# ---------------------------------------------------------------------------
# Summary fields
# ---------------------------------------------------------------------------


def test_summary_fields_match_report(store, sample_stats_report):
    store.save_session(sample_stats_report)
    summaries = store.list_sessions()
    assert len(summaries) == 1
    s = summaries[0]
    assert s.session_id == sample_stats_report.session_id
    assert s.video_source == sample_stats_report.video_source
    assert s.position == sample_stats_report.position
    assert s.player_ref == sample_stats_report.player_ref
