"""Unit tests for backend/analyzer.py."""

from __future__ import annotations

import pytest

from backend.analyzer import Analyzer
from backend.models import Detection, FrameResult, Position


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_frame(
    frame_idx: int,
    timestamp_ms: int,
    player_box=None,
    ball_box=None,
    confidence: float = 0.9,
    other_persons: list[tuple[int, int, int, int]] | None = None,
) -> FrameResult:
    """Build a minimal FrameResult for testing."""
    detections: list[Detection] = []
    if player_box is not None:
        detections.append(
            Detection(track_id=1, bbox=player_box, label="person", confidence=confidence)
        )
    if ball_box is not None:
        detections.append(
            Detection(track_id=99, bbox=ball_box, label="ball", confidence=0.95)
        )
    for i, box in enumerate(other_persons or []):
        detections.append(
            Detection(track_id=10 + i, bbox=box, label="person", confidence=0.85)
        )
    return FrameResult(
        frame_idx=frame_idx,
        timestamp_ms=timestamp_ms,
        player_box=player_box,
        ball_box=ball_box,
        confidence=confidence,
        all_detections=detections,
    )


# ---------------------------------------------------------------------------
# Touch detection tests
# ---------------------------------------------------------------------------

class TestTouchDetection:
    def test_single_touch_counted(self):
        """Ball within proximity of player registers one touch."""
        analyzer = Analyzer(touch_proximity_px=50)
        # Player at (100,100,50,50), ball at (140,120,20,20) — centers ~44px apart
        frame = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(frame)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.touch_count == 1

    def test_no_touch_when_ball_far(self):
        """Ball far from player does not register a touch."""
        analyzer = Analyzer(touch_proximity_px=50)
        frame = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(500, 500, 20, 20))
        analyzer.process_frame(frame)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.touch_count == 0

    def test_debounce_within_500ms(self):
        """Two contacts within 500ms count as one touch (Req 4.2)."""
        analyzer = Analyzer(touch_proximity_px=50)
        # First touch at t=0
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        # Second contact at t=300ms (within debounce window)
        f1 = _make_frame(9, 300, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        analyzer.process_frame(f1)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.touch_count == 1

    def test_two_touches_after_debounce(self):
        """Two contacts separated by >500ms count as two touches."""
        analyzer = Analyzer(touch_proximity_px=50)
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        f1 = _make_frame(20, 600, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        analyzer.process_frame(f1)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.touch_count == 2

    def test_touch_event_has_timestamp(self):
        """TouchEvent records the correct timestamp (Req 4.4)."""
        analyzer = Analyzer(touch_proximity_px=50)
        frame = _make_frame(5, 1500, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(frame)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert len(core.touch_events) == 1
        assert core.touch_events[0].timestamp_ms == 1500

    def test_no_touch_when_no_ball(self):
        """No ball in frame means no touch."""
        analyzer = Analyzer(touch_proximity_px=50)
        frame = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=None)
        analyzer.process_frame(frame)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.touch_count == 0

    def test_no_touch_when_no_player(self):
        """No player in frame means no touch."""
        analyzer = Analyzer(touch_proximity_px=50)
        frame = _make_frame(0, 0, player_box=None, ball_box=(140, 120, 20, 20))
        analyzer.process_frame(frame)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.touch_count == 0


# ---------------------------------------------------------------------------
# Pass detection tests
# ---------------------------------------------------------------------------

class TestPassDetection:
    def _touch_then_pass_to_teammate(self, analyzer: Analyzer) -> None:
        """Helper: player touches ball, then ball reaches a teammate."""
        # Frame 0: player touches ball
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)

        # Frame 1: ball moves well beyond adaptive proximity
        # Adaptive radius for 50x50 box = max(75, 100, 50) = 100px
        # Player center (125,125), ball center (360,310) → dist ~260px → clearly outside
        f1 = _make_frame(1, 33, player_box=(100, 100, 50, 50), ball_box=(350, 300, 20, 20))
        analyzer.process_frame(f1)

        # Frame 2: ball reaches a teammate
        teammate_box = (340, 290, 40, 40)
        f2 = _make_frame(
            2, 66,
            player_box=(100, 100, 50, 50),
            ball_box=(350, 300, 20, 20),
            other_persons=[teammate_box],
        )
        analyzer.process_frame(f2)

    def test_successful_pass_counted(self):
        """Ball reaching a teammate counts as attempted + successful pass (Req 5.1)."""
        analyzer = Analyzer(touch_proximity_px=50)
        self._touch_then_pass_to_teammate(analyzer)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.passes_attempted == 1
        assert core.passes_successful == 1

    def test_pass_completion_pct_formula(self):
        """pass_completion_pct = round(successful/attempted * 100, 1) (Req 5.4)."""
        analyzer = Analyzer(touch_proximity_px=50)
        self._touch_then_pass_to_teammate(analyzer)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.pass_completion_pct == 100.0

    def test_pass_completion_pct_none_when_no_attempts(self):
        """pass_completion_pct is None when no passes attempted (Req 5.5)."""
        analyzer = Analyzer(touch_proximity_px=50)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.pass_completion_pct is None

    def test_failed_pass_on_timeout(self):
        """Pass times out (>3s) without reaching teammate — attempted but not successful."""
        analyzer = Analyzer(touch_proximity_px=50)
        # Touch at t=0
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        # Ball moves away
        f1 = _make_frame(1, 33, player_box=(100, 100, 50, 50), ball_box=(300, 300, 20, 20))
        analyzer.process_frame(f1)
        # 3.5 seconds later — no teammate received ball
        f2 = _make_frame(100, 3500, player_box=(100, 100, 50, 50), ball_box=(300, 300, 20, 20))
        analyzer.process_frame(f2)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.passes_attempted == 1
        assert core.passes_successful == 0

    def test_failed_pass_when_ball_disappears(self):
        """Ball disappearing after a touch counts as attempted but failed pass."""
        analyzer = Analyzer(touch_proximity_px=50)
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        f1 = _make_frame(1, 33, player_box=(100, 100, 50, 50), ball_box=(300, 300, 20, 20))
        analyzer.process_frame(f1)
        # Ball disappears
        f2 = _make_frame(2, 66, player_box=(100, 100, 50, 50), ball_box=None)
        analyzer.process_frame(f2)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.passes_attempted == 1
        assert core.passes_successful == 0


# ---------------------------------------------------------------------------
# Ball loss detection tests
# ---------------------------------------------------------------------------

class TestBallLossDetection:
    def test_ball_loss_when_opponent_gains_possession(self):
        """Opponent gaining ball after player touch counts as ball loss (Req 6.1)."""
        analyzer = Analyzer(touch_proximity_px=50)
        # Touch at t=0
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        # Ball moves far away from player
        f1 = _make_frame(1, 33, player_box=(100, 100, 50, 50), ball_box=(500, 500, 20, 20))
        analyzer.process_frame(f1)
        # Opponent (far from player) gains ball — player center ~(125,125), opponent center ~(520,520)
        # distance ~560px >> 3*50=150px → treated as opponent
        opponent_box = (495, 495, 40, 40)
        f2 = _make_frame(
            2, 66,
            player_box=(100, 100, 50, 50),
            ball_box=(500, 500, 20, 20),
            other_persons=[opponent_box],
        )
        analyzer.process_frame(f2)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.ball_losses == 1

    def test_ball_loss_event_has_timestamp(self):
        """BallLossEvent records the correct timestamp (Req 6.3)."""
        analyzer = Analyzer(touch_proximity_px=50)
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        f1 = _make_frame(1, 33, player_box=(100, 100, 50, 50), ball_box=(500, 500, 20, 20))
        analyzer.process_frame(f1)
        opponent_box = (495, 495, 40, 40)
        f2 = _make_frame(
            2, 66,
            player_box=(100, 100, 50, 50),
            ball_box=(500, 500, 20, 20),
            other_persons=[opponent_box],
        )
        analyzer.process_frame(f2)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert len(core.ball_loss_events) == 1
        assert core.ball_loss_events[0].timestamp_ms == 66

    def test_ball_retention_rate_formula(self):
        """ball_retention_rate = round((touches - losses) / touches * 100, 1) (Req 6.4)."""
        analyzer = Analyzer(touch_proximity_px=50)
        f0 = _make_frame(0, 0, player_box=(100, 100, 50, 50), ball_box=(140, 120, 20, 20))
        analyzer.process_frame(f0)
        f1 = _make_frame(1, 33, player_box=(100, 100, 50, 50), ball_box=(500, 500, 20, 20))
        analyzer.process_frame(f1)
        opponent_box = (495, 495, 40, 40)
        f2 = _make_frame(
            2, 66,
            player_box=(100, 100, 50, 50),
            ball_box=(500, 500, 20, 20),
            other_persons=[opponent_box],
        )
        analyzer.process_frame(f2)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        # 1 touch, 1 loss → (1-1)/1 * 100 = 0.0
        assert core.ball_retention_rate == 0.0

    def test_ball_retention_rate_none_when_no_touches(self):
        """ball_retention_rate is None when no touches (Req 6.5)."""
        analyzer = Analyzer(touch_proximity_px=50)
        core, _ = analyzer.finalize(Position.MIDFIELDER)
        assert core.ball_retention_rate is None


# ---------------------------------------------------------------------------
# Advanced stats tests
# ---------------------------------------------------------------------------

class TestAdvancedStats:
    def test_goalkeeper_stats_returned_for_goalkeeper(self):
        """finalize(GOALKEEPER) returns GoalkeeperStats."""
        from backend.models import GoalkeeperStats
        analyzer = Analyzer()
        _, advanced = analyzer.finalize(Position.GOALKEEPER)
        assert isinstance(advanced, GoalkeeperStats)

    def test_defender_stats_returned_for_defender(self):
        """finalize(DEFENDER) returns DefenderStats."""
        from backend.models import DefenderStats
        analyzer = Analyzer()
        _, advanced = analyzer.finalize(Position.DEFENDER)
        assert isinstance(advanced, DefenderStats)

    def test_midfielder_stats_returned_for_midfielder(self):
        """finalize(MIDFIELDER) returns MidfielderStats."""
        from backend.models import MidfielderStats
        analyzer = Analyzer()
        _, advanced = analyzer.finalize(Position.MIDFIELDER)
        assert isinstance(advanced, MidfielderStats)

    def test_forward_stats_returned_for_forward(self):
        """finalize(FORWARD) returns ForwardStats."""
        from backend.models import ForwardStats
        analyzer = Analyzer()
        _, advanced = analyzer.finalize(Position.FORWARD)
        assert isinstance(advanced, ForwardStats)

    def test_midfielder_distance_covered_nonzero(self):
        """Distance covered increases as player moves across frames."""
        from backend.models import MidfielderStats
        analyzer = Analyzer(frame_width=1920, frame_height=1080)
        # Player moves from (100,100) to (200,100) — 100px movement
        f0 = _make_frame(0, 0, player_box=(75, 75, 50, 50))
        f1 = _make_frame(1, 33, player_box=(175, 75, 50, 50))
        analyzer.process_frame(f0)
        analyzer.process_frame(f1)
        _, advanced = analyzer.finalize(Position.MIDFIELDER)
        assert isinstance(advanced, MidfielderStats)
        assert advanced.distance_covered_m > 0.0

    def test_defender_interceptions_from_ball_loss_events(self):
        """Defender interceptions count comes from ball_loss events with cause=interception."""
        from backend.models import DefenderStats
        analyzer = Analyzer(touch_proximity_px=50)
        # Manually inject a ball loss event with cause=interception
        from backend.models import BallLossEvent
        analyzer._ball_loss_events.append(
            BallLossEvent(timestamp_ms=500, frame_idx=15, cause="interception")
        )
        _, advanced = analyzer.finalize(Position.DEFENDER)
        assert isinstance(advanced, DefenderStats)
        assert advanced.interceptions == 1

    def test_all_advanced_stat_fields_present(self):
        """All required fields are non-None for each position (Req 7.3–7.7)."""
        from backend.models import (
            DefenderStats,
            ForwardStats,
            GoalkeeperStats,
            MidfielderStats,
        )
        for position, expected_type in [
            (Position.GOALKEEPER, GoalkeeperStats),
            (Position.DEFENDER, DefenderStats),
            (Position.MIDFIELDER, MidfielderStats),
            (Position.FORWARD, ForwardStats),
        ]:
            analyzer = Analyzer()
            _, advanced = analyzer.finalize(position)
            assert isinstance(advanced, expected_type)
            # Check all integer/float fields are not None
            for field_name, field_info in expected_type.model_fields.items():
                val = getattr(advanced, field_name)
                # Optional fields (distribution_accuracy_pct) may be None
                annotation = str(field_info.annotation)
                if "Optional" not in annotation:
                    assert val is not None, f"{field_name} should not be None for {position}"
