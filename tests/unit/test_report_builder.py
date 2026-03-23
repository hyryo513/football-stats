"""Unit tests for backend/report_builder.py."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.analyzer import Analyzer
from backend.errors import ExportError
from backend.models import (
    BallLossEvent,
    CoreStats,
    DefenderStats,
    ForwardStats,
    GoalkeeperStats,
    MidfielderStats,
    PassEvent,
    PlayerRef,
    Position,
    StatsReport,
    TouchEvent,
)
from backend.report_builder import ReportBuilder, build_report, export_json, export_pdf


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_report(position: Position = Position.MIDFIELDER) -> StatsReport:
    core = CoreStats(
        touch_count=5,
        touch_events=[TouchEvent(timestamp_ms=1000 * i, frame_idx=30 * i, confidence=0.9) for i in range(5)],
        passes_attempted=4,
        passes_successful=3,
        pass_events=[
            PassEvent(timestamp_ms=1500, attempted=True, successful=True),
            PassEvent(timestamp_ms=3000, attempted=True, successful=True),
            PassEvent(timestamp_ms=4500, attempted=True, successful=True),
            PassEvent(timestamp_ms=6000, attempted=True, successful=False),
        ],
        pass_completion_pct=75.0,
        ball_losses=1,
        ball_loss_events=[BallLossEvent(timestamp_ms=3000, frame_idx=90, cause="tackle")],
        ball_retention_rate=80.0,
    )
    advanced: object
    if position == Position.MIDFIELDER:
        advanced = MidfielderStats(key_passes=2, through_balls=1, distance_covered_m=3200.0, ball_recoveries=3)
    elif position == Position.GOALKEEPER:
        advanced = GoalkeeperStats(saves=4, goals_conceded=1, distribution_accuracy_pct=75.0, sweeper_actions=2)
    elif position == Position.DEFENDER:
        advanced = DefenderStats(tackles_attempted=5, tackles_won=3, interceptions=2, clearances=4, aerial_duels_won=1)
    else:
        advanced = ForwardStats(shots_on_target=3, shots_off_target=2, dribbles_attempted=6, dribbles_completed=4, off_ball_runs=8)

    return StatsReport(
        session_id="unit-test-001",
        created_at=datetime(2024, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        video_source="/videos/match.mp4",
        player_ref=PlayerRef(method="jersey", jersey_number=7),
        position=position,
        analysis_duration_s=90.0,
        core=core,
        advanced=advanced,
    )


# ---------------------------------------------------------------------------
# ReportBuilder.build()
# ---------------------------------------------------------------------------

class TestBuild:
    def test_build_returns_stats_report(self):
        analyzer = Analyzer()
        rb = ReportBuilder()
        report = rb.build(
            session_id="s1",
            video_source="/tmp/video.mp4",
            player_ref=PlayerRef(method="jersey", jersey_number=9),
            position=Position.FORWARD,
            analyzer=analyzer,
            analysis_duration_s=60.0,
        )
        assert isinstance(report, StatsReport)

    def test_build_sets_session_metadata(self):
        analyzer = Analyzer()
        rb = ReportBuilder()
        report = rb.build(
            session_id="session-xyz",
            video_source="https://example.com/video.mp4",
            player_ref=PlayerRef(method="bbox", bbox=(10, 20, 50, 80)),
            position=Position.DEFENDER,
            analyzer=analyzer,
            analysis_duration_s=45.5,
        )
        assert report.session_id == "session-xyz"
        assert report.video_source == "https://example.com/video.mp4"
        assert report.player_ref.method == "bbox"
        assert report.position == Position.DEFENDER
        assert report.analysis_duration_s == 45.5

    def test_build_created_at_is_utc(self):
        analyzer = Analyzer()
        rb = ReportBuilder()
        report = rb.build(
            session_id="s2",
            video_source="/tmp/v.mp4",
            player_ref=PlayerRef(method="jersey", jersey_number=1),
            position=Position.GOALKEEPER,
            analyzer=analyzer,
            analysis_duration_s=10.0,
        )
        assert report.created_at.tzinfo is not None

    def test_build_advanced_stats_match_position(self):
        for pos, expected_type in [
            (Position.GOALKEEPER, GoalkeeperStats),
            (Position.DEFENDER, DefenderStats),
            (Position.MIDFIELDER, MidfielderStats),
            (Position.FORWARD, ForwardStats),
        ]:
            analyzer = Analyzer()
            rb = ReportBuilder()
            report = rb.build(
                session_id="s",
                video_source="/v.mp4",
                player_ref=PlayerRef(method="jersey", jersey_number=1),
                position=pos,
                analyzer=analyzer,
                analysis_duration_s=1.0,
            )
            assert isinstance(report.advanced, expected_type), f"Expected {expected_type} for {pos}"


# ---------------------------------------------------------------------------
# ReportBuilder.export_json()
# ---------------------------------------------------------------------------

class TestExportJson:
    def test_export_json_creates_file(self):
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            rb.export_json(report, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def test_export_json_valid_json(self):
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            rb.export_json(report, path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert isinstance(data, dict)
        finally:
            os.unlink(path)

    def test_export_json_contains_required_metadata(self):
        """Req 8.4 — exported JSON must contain video source, player identifier, timestamp."""
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            rb.export_json(report, path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            assert "video_source" in data
            assert "player_ref" in data
            assert "created_at" in data
            assert data["video_source"] == "/videos/match.mp4"
        finally:
            os.unlink(path)

    def test_export_json_round_trip(self):
        """Req 8.3 — JSON round-trip should preserve all fields."""
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            rb.export_json(report, path)
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            restored = StatsReport.model_validate(data)
            assert restored.session_id == report.session_id
            assert restored.video_source == report.video_source
            assert restored.core.touch_count == report.core.touch_count
            assert restored.core.passes_attempted == report.core.passes_attempted
        finally:
            os.unlink(path)

    def test_export_json_raises_export_error_on_bad_path(self):
        report = _make_report()
        rb = ReportBuilder()
        with pytest.raises(ExportError) as exc_info:
            rb.export_json(report, "/nonexistent_dir/output.json")
        assert exc_info.value.export_format == "json"

    def test_export_json_indented(self):
        """Output should be indented (pretty-printed)."""
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            rb.export_json(report, path)
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # Indented JSON has newlines
            assert "\n" in content
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# ReportBuilder.export_pdf()
# ---------------------------------------------------------------------------

class TestExportPdf:
    def test_export_pdf_creates_file(self):
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            rb.export_pdf(report, path)
            assert os.path.exists(path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def test_export_pdf_is_pdf_format(self):
        report = _make_report()
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            rb.export_pdf(report, path)
            with open(path, "rb") as f:
                header = f.read(4)
            assert header == b"%PDF"
        finally:
            os.unlink(path)

    def test_export_pdf_raises_export_error_on_bad_path(self):
        report = _make_report()
        rb = ReportBuilder()
        with pytest.raises(ExportError) as exc_info:
            rb.export_pdf(report, "/nonexistent_dir/output.pdf")
        assert exc_info.value.export_format == "pdf"

    def test_export_pdf_all_positions(self):
        """PDF export should work for all four positions."""
        rb = ReportBuilder()
        for pos in Position:
            report = _make_report(position=pos)
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                path = f.name
            try:
                rb.export_pdf(report, path)
                assert os.path.getsize(path) > 0
            finally:
                os.unlink(path)

    def test_export_pdf_bbox_player_ref(self):
        """PDF export should handle bbox player ref without error."""
        core = CoreStats(
            touch_count=0, touch_events=[], passes_attempted=0, passes_successful=0,
            pass_events=[],
            pass_completion_pct=None, ball_losses=0, ball_loss_events=[], ball_retention_rate=None,
        )
        report = StatsReport(
            session_id="bbox-test",
            created_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            video_source="/v.mp4",
            player_ref=PlayerRef(method="bbox", bbox=(0, 0, 100, 200)),
            position=Position.FORWARD,
            analysis_duration_s=5.0,
            core=core,
            advanced=ForwardStats(shots_on_target=0, shots_off_target=0, dribbles_attempted=0, dribbles_completed=0, off_ball_runs=0),
        )
        rb = ReportBuilder()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            rb.export_pdf(report, path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

class TestConvenienceFunctions:
    def test_build_report_delegates(self):
        analyzer = Analyzer()
        report = build_report(
            session_id="conv-1",
            video_source="/v.mp4",
            player_ref=PlayerRef(method="jersey", jersey_number=5),
            position=Position.MIDFIELDER,
            analyzer=analyzer,
            analysis_duration_s=30.0,
        )
        assert isinstance(report, StatsReport)
        assert report.session_id == "conv-1"

    def test_export_json_convenience(self):
        report = _make_report()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_json(report, path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)

    def test_export_pdf_convenience(self):
        report = _make_report()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name
        try:
            export_pdf(report, path)
            assert os.path.getsize(path) > 0
        finally:
            os.unlink(path)
