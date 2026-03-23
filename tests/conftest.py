"""Shared pytest fixtures for the Soccer Player Tracker test suite."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from hypothesis import HealthCheck, settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ---------------------------------------------------------------------------
# Hypothesis profiles
# ---------------------------------------------------------------------------

settings.register_profile(
    "ci",
    max_examples=100,
    suppress_health_check=[HealthCheck.too_slow],
)
settings.load_profile("ci")


# ---------------------------------------------------------------------------
# In-memory SQLite database fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def db_engine():
    """Provide a fresh in-memory SQLite engine for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Provide a SQLAlchemy session bound to the in-memory engine."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


# ---------------------------------------------------------------------------
# Sample StatsReport factory
# ---------------------------------------------------------------------------

def make_stats_report(
    session_id: str = "test-session-001",
    position: str = "midfielder",
    passes_attempted: int = 10,
    passes_successful: int = 8,
    touch_count: int = 20,
    ball_losses: int = 3,
) -> dict:
    """Return a minimal StatsReport-compatible dict for testing."""
    from backend.models import (
        BallLossEvent,
        CoreStats,
        MidfielderStats,
        PassEvent,
        PlayerRef,
        Position,
        StatsReport,
        TouchEvent,
    )

    pass_pct = round((passes_successful / passes_attempted) * 100, 1) if passes_attempted > 0 else None
    retention = round(((touch_count - ball_losses) / touch_count) * 100, 1) if touch_count > 0 else None

    core = CoreStats(
        touch_count=touch_count,
        touch_events=[
            TouchEvent(timestamp_ms=i * 1000, frame_idx=i * 30, confidence=0.9)
            for i in range(touch_count)
        ],
        passes_attempted=passes_attempted,
        passes_successful=passes_successful,
        pass_events=[
            PassEvent(timestamp_ms=i * 1500, attempted=True, successful=i < passes_successful)
            for i in range(passes_attempted)
        ],
        pass_completion_pct=pass_pct,
        ball_losses=ball_losses,
        ball_loss_events=[
            BallLossEvent(timestamp_ms=i * 2000, frame_idx=i * 60, cause="tackle")
            for i in range(ball_losses)
        ],
        ball_retention_rate=retention,
    )

    advanced = MidfielderStats(
        key_passes=3,
        through_balls=1,
        distance_covered_m=4500.0,
        ball_recoveries=5,
    )

    return StatsReport(
        session_id=session_id,
        created_at=datetime.now(tz=timezone.utc),
        video_source="/tmp/test_match.mp4",
        player_ref=PlayerRef(method="jersey", jersey_number=10),
        position=Position(position),
        analysis_duration_s=120.5,
        core=core,
        advanced=advanced,
    )


@pytest.fixture
def sample_stats_report():
    """Provide a sample StatsReport instance."""
    return make_stats_report()


@pytest.fixture
def stats_report_factory():
    """Provide the make_stats_report factory function."""
    return make_stats_report
