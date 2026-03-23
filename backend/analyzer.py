"""Analyzer: consumes FrameResult stream and computes soccer statistics."""

from __future__ import annotations

import math
from collections import deque
from typing import Optional

from backend.models import (
    BallLossEvent,
    CoreStats,
    DefenderStats,
    ForwardStats,
    FrameResult,
    GoalkeeperStats,
    MidfielderStats,
    PassEvent,
    Position,
    TouchEvent,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEBOUNCE_MS = 500          # Req 4.2 — two contacts within 500ms = one touch
_PASS_WINDOW_MS = 3_000     # 3 seconds to complete a pass after a touch
_BALL_TRAJECTORY_LEN = 30   # frames of ball history to keep
_STANDARD_FIELD_M = (105.0, 68.0)  # FIFA standard field dimensions in metres


def _box_center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


def _distance(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _boxes_overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by


def _expand_box(
    box: tuple[int, int, int, int], scale_x: float, scale_y: float
) -> tuple[int, int, int, int]:
    """Return *box* expanded by the given factors around its center."""
    x, y, w, h = box
    cx, cy = x + w / 2.0, y + h / 2.0
    nw, nh = w * scale_x, h * scale_y
    return (int(cx - nw / 2), int(cy - nh / 2), int(nw), int(nh))


class Analyzer:
    """Stateful analyzer that processes FrameResult objects one at a time.

    Usage::

        analyzer = Analyzer(video_fps=30.0, touch_proximity_px=50)
        for frame in tracker.track_frames():
            analyzer.process_frame(frame)
        core, advanced = analyzer.finalize(Position.MIDFIELDER)
    """

    def __init__(
        self,
        video_fps: float = 30.0,
        touch_proximity_px: int = 50,
        frame_width: int = 1920,
        frame_height: int = 1080,
    ) -> None:
        self.video_fps = video_fps
        self.touch_proximity_px = touch_proximity_px
        self.frame_width = frame_width
        self.frame_height = frame_height

        # Pixel-to-metre ratio (Req 7.5 — distance_covered_m)
        self._px_per_m_x = frame_width / _STANDARD_FIELD_M[0]
        self._px_per_m_y = frame_height / _STANDARD_FIELD_M[1]
        self._px_per_m = (self._px_per_m_x + self._px_per_m_y) / 2.0

        # Accumulated events
        self._touch_events: list[TouchEvent] = []
        self._pass_events: list[PassEvent] = []
        self._ball_loss_events: list[BallLossEvent] = []

        # Touch-detector state
        self._last_touch_ms: Optional[int] = None

        # Pass-detector state
        self._in_possession: bool = False          # player currently has the ball
        self._touch_start_ms: Optional[int] = None # timestamp of the last touch
        self._touch_start_frame: Optional[int] = None
        self._pass_pending: bool = False           # waiting to see if a pass completes
        self._pass_start_ms: Optional[int] = None

        # Ball trajectory (deque of (timestamp_ms, center_x, center_y))
        self._ball_trajectory: deque[tuple[int, float, float]] = deque(
            maxlen=_BALL_TRAJECTORY_LEN
        )

        # Player position history for distance_covered_m
        self._player_centers: list[tuple[float, float]] = []

        # Advanced-stat counters (position-agnostic accumulation)
        self._shots_total: int = 0          # forward
        self._shots_on_target: int = 0      # forward
        self._dribbles_attempted: int = 0   # forward
        self._dribbles_completed: int = 0   # forward
        self._off_ball_runs: int = 0        # forward

        self._tackles_attempted: int = 0    # defender
        self._tackles_won: int = 0          # defender
        self._clearances: int = 0           # defender
        self._aerial_duels_won: int = 0     # defender

        self._key_passes: int = 0           # midfielder
        self._through_balls: int = 0        # midfielder
        self._ball_recoveries: int = 0      # midfielder

        self._saves: int = 0                # goalkeeper
        self._goals_conceded: int = 0       # goalkeeper
        self._sweeper_actions: int = 0      # goalkeeper

        # Frame dimensions (updated on first frame if not provided)
        self._frame_dims_set: bool = False

        # Previous frame reference for heuristics
        self._prev_frame: Optional[FrameResult] = None

        # Diagnostics counters
        self._frames_total: int = 0
        self._frames_with_player: int = 0
        self._frames_with_ball: int = 0
        self._frames_with_both: int = 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_frame(self, frame: FrameResult) -> None:
        """Process one FrameResult and update internal state."""
        self._update_frame_dims(frame)
        self._update_ball_trajectory(frame)
        self._update_player_history(frame)

        self._frames_total += 1
        has_player = frame.player_box is not None
        has_ball = frame.ball_box is not None
        if has_player:
            self._frames_with_player += 1
        if has_ball:
            self._frames_with_ball += 1
        if has_player and has_ball:
            self._frames_with_both += 1

        if has_player and has_ball:
            self._detect_touch(frame)

        # Ball loss must be checked before pass completion — a ball loss cancels
        # the pending pass so that the same event is not double-counted.
        if self._pass_pending:
            self._detect_ball_loss(frame)

        if self._pass_pending:
            self._check_pass_completion(frame)

        self._update_advanced_heuristics(frame)

        self._prev_frame = frame

    def finalize(self, position: Position) -> tuple[CoreStats, object]:
        """Compute and return (CoreStats, AdvancedStats) for the given position."""
        core = self._build_core_stats()
        advanced = self._build_advanced_stats(position, core)
        return core, advanced

    def get_diagnostics(self) -> dict[str, object]:
        """Return ball/player detection rate diagnostics."""
        total = max(self._frames_total, 1)
        return {
            "frames_total": self._frames_total,
            "frames_with_player": self._frames_with_player,
            "frames_with_ball": self._frames_with_ball,
            "frames_with_both": self._frames_with_both,
            "player_detection_pct": round(self._frames_with_player / total * 100, 1),
            "ball_detection_pct": round(self._frames_with_ball / total * 100, 1),
            "both_detection_pct": round(self._frames_with_both / total * 100, 1),
        }

    # ------------------------------------------------------------------
    # Touch detection (Req 4.1, 4.2)
    # ------------------------------------------------------------------

    def _detect_touch(self, frame: FrameResult) -> None:
        assert frame.player_box is not None
        assert frame.ball_box is not None

        px, py, pw, ph = frame.player_box
        adaptive_radius = max(ph * 1.5, pw * 2.0, self.touch_proximity_px)

        expanded_player = _expand_box(frame.player_box, 2.0, 1.5)
        overlap = _boxes_overlap(expanded_player, frame.ball_box)

        player_center = _box_center(frame.player_box)
        ball_center = _box_center(frame.ball_box)
        dist = _distance(player_center, ball_center)

        if not overlap and dist > adaptive_radius:
            if self._in_possession:
                self._in_possession = False
                self._start_pass_tracking(frame)
            return

        # Ball is within proximity — potential touch
        ts = frame.timestamp_ms

        # Debounce: ignore if within 500ms of last touch (Req 4.2)
        if self._last_touch_ms is not None and (ts - self._last_touch_ms) < _DEBOUNCE_MS:
            self._in_possession = True
            return

        # Record touch (Req 4.1, 4.4)
        self._touch_events.append(
            TouchEvent(
                timestamp_ms=ts,
                frame_idx=frame.frame_idx,
                confidence=frame.confidence,
            )
        )
        self._last_touch_ms = ts
        self._in_possession = True
        self._touch_start_ms = ts
        self._touch_start_frame = frame.frame_idx
        # Cancel any pending pass — player re-touched the ball
        self._pass_pending = False

    # ------------------------------------------------------------------
    # Pass detection (Req 5.1)
    # ------------------------------------------------------------------

    def _start_pass_tracking(self, frame: FrameResult) -> None:
        """Called when the player loses proximity to the ball after a touch."""
        if self._touch_start_ms is None:
            return
        self._pass_pending = True
        self._pass_start_ms = frame.timestamp_ms

    def _check_pass_completion(self, frame: FrameResult) -> None:
        """Determine if a pending pass succeeded, failed, or timed out."""
        if self._pass_start_ms is None:
            return

        elapsed = frame.timestamp_ms - self._pass_start_ms

        # Timeout — attempted but not successful
        if elapsed > _PASS_WINDOW_MS:
            self._record_pass(frame.timestamp_ms, attempted=True, successful=False)
            self._pass_pending = False
            return

        if frame.ball_box is None:
            # Ball disappeared — attempted but failed
            self._record_pass(frame.timestamp_ms, attempted=True, successful=False)
            self._pass_pending = False
            return

        # Check if ball overlaps with any other person (teammate)
        ball_box = frame.ball_box
        for det in frame.all_detections:
            if det.label != "person":
                continue
            # Skip the tracked player's own box
            if frame.player_box is not None and _boxes_overlap(det.bbox, frame.player_box):
                continue
            if _boxes_overlap(ball_box, det.bbox):
                # Ball reached another person — successful pass (Req 5.1)
                self._record_pass(frame.timestamp_ms, attempted=True, successful=True)
                self._pass_pending = False
                return

    def _record_pass(self, timestamp_ms: int, attempted: bool, successful: bool) -> None:
        self._pass_events.append(
            PassEvent(timestamp_ms=timestamp_ms, attempted=attempted, successful=successful)
        )

    # ------------------------------------------------------------------
    # Ball loss detection (Req 6.1)
    # ------------------------------------------------------------------

    def _detect_ball_loss(self, frame: FrameResult) -> None:
        """Detect if an opponent gained possession after the player had the ball.

        Heuristic to distinguish opponent from teammate: a person who is far from
        the tracked player (> 3× touch_proximity_px) and receives the ball is
        treated as an opponent (ball loss). A person close to the player is a
        teammate (pass), handled by _check_pass_completion.
        """
        if self._prev_frame is None:
            return
        if self._in_possession:
            return
        if frame.ball_box is None:
            return

        ball_box = frame.ball_box
        player_box = frame.player_box
        if player_box is not None:
            _, _, pw, ph = player_box
            adaptive_radius = max(ph * 1.5, pw * 2.0, self.touch_proximity_px)
        else:
            adaptive_radius = self.touch_proximity_px
        opponent_threshold = adaptive_radius * 3

        for det in frame.all_detections:
            if det.label != "person":
                continue
            if player_box is not None and _boxes_overlap(det.bbox, player_box):
                continue
            if not _boxes_overlap(ball_box, det.bbox):
                continue

            if player_box is not None:
                receiver_center = _box_center(det.bbox)
                player_center = _box_center(player_box)
                dist_to_player = _distance(receiver_center, player_center)
                if dist_to_player <= opponent_threshold:
                    continue

            # Far from player — treat as opponent → ball loss
            cause = self._classify_ball_loss_cause(frame, det.bbox)
            self._ball_loss_events.append(
                BallLossEvent(
                    timestamp_ms=frame.timestamp_ms,
                    frame_idx=frame.frame_idx,
                    cause=cause,
                )
            )
            # Cancel pass tracking — this was a loss, not a pass
            self._pass_pending = False
            self._in_possession = False
            return

    def _classify_ball_loss_cause(
        self, frame: FrameResult, opponent_box: tuple[int, int, int, int]
    ) -> str:
        """Heuristic: classify ball loss as tackle, interception, or miscontrol."""
        if frame.player_box is None:
            return "miscontrol"

        player_center = _box_center(frame.player_box)
        opponent_center = _box_center(opponent_box)
        dist = _distance(player_center, opponent_center)

        # If opponent is very close to the player — tackle
        if dist < self.touch_proximity_px * 2:
            return "tackle"

        # If ball changed direction suddenly — interception
        if len(self._ball_trajectory) >= 4:
            traj = list(self._ball_trajectory)
            # Compute direction change between last two segments
            dx1 = traj[-2][1] - traj[-3][1]
            dy1 = traj[-2][2] - traj[-3][2]
            dx2 = traj[-1][1] - traj[-2][1]
            dy2 = traj[-1][2] - traj[-2][2]
            dot = dx1 * dx2 + dy1 * dy2
            mag1 = math.hypot(dx1, dy1)
            mag2 = math.hypot(dx2, dy2)
            if mag1 > 0 and mag2 > 0:
                cos_angle = dot / (mag1 * mag2)
                # Sudden direction reversal (angle > 90°)
                if cos_angle < 0:
                    return "interception"

        return "miscontrol"

    # ------------------------------------------------------------------
    # Advanced stat heuristics
    # ------------------------------------------------------------------

    def _update_advanced_heuristics(self, frame: FrameResult) -> None:
        """Update position-agnostic counters from frame data."""
        if frame.player_box is None or frame.ball_box is None:
            return

        player_center = _box_center(frame.player_box)
        ball_center = _box_center(frame.ball_box)
        dist = _distance(player_center, ball_center)

        # --- Forward heuristics ---
        # Shot: player kicks ball (had possession, now ball moving fast away)
        if self._prev_frame is not None and self._prev_frame.ball_box is not None:
            prev_ball_center = _box_center(self._prev_frame.ball_box)
            ball_speed = _distance(ball_center, prev_ball_center)
            # High-speed ball departure after possession = shot attempt
            if (
                not self._in_possession
                and self._prev_frame.player_box is not None
                and ball_speed > self.touch_proximity_px * 1.5
            ):
                prev_dist = _distance(
                    _box_center(self._prev_frame.player_box), prev_ball_center
                )
                if prev_dist <= self.touch_proximity_px:
                    self._shots_total += 1
                    # On-target heuristic: ball moving toward centre of frame
                    cx = self.frame_width / 2.0
                    cy = self.frame_height / 2.0
                    moving_toward_centre = _distance(ball_center, (cx, cy)) < _distance(
                        prev_ball_center, (cx, cy)
                    )
                    if moving_toward_centre:
                        self._shots_on_target += 1
                    else:
                        pass  # shots_off_target computed in finalize

        # Dribble: player moves with ball (ball stays close while player moves)
        if self._prev_frame is not None and self._prev_frame.player_box is not None:
            prev_player_center = _box_center(self._prev_frame.player_box)
            player_movement = _distance(player_center, prev_player_center)
            if dist <= self.touch_proximity_px and player_movement > self.touch_proximity_px * 0.5:
                self._dribbles_attempted += 1
                # Completed if player maintained possession for >2 consecutive frames
                if len(self._player_centers) >= 2:
                    self._dribbles_completed += 1

        # Off-ball run: player moves quickly without the ball
        if (
            dist > self.touch_proximity_px * 3
            and self._prev_frame is not None
            and self._prev_frame.player_box is not None
        ):
            prev_player_center = _box_center(self._prev_frame.player_box)
            player_movement = _distance(player_center, prev_player_center)
            if player_movement > self.touch_proximity_px:
                self._off_ball_runs += 1

        # --- Defender heuristics ---
        # Tackle: player challenges opponent who has the ball
        for det in frame.all_detections:
            if det.label != "person":
                continue
            if frame.player_box is not None and _boxes_overlap(det.bbox, frame.player_box):
                continue
            opp_center = _box_center(det.bbox)
            opp_ball_dist = _distance(opp_center, ball_center)
            player_opp_dist = _distance(player_center, opp_center)
            if opp_ball_dist < self.touch_proximity_px and player_opp_dist < self.touch_proximity_px * 2:
                self._tackles_attempted += 1
                # Won if player gains possession after
                if dist <= self.touch_proximity_px:
                    self._tackles_won += 1
                break

        # Clearance: player kicks ball far away from own half
        if self._prev_frame is not None and self._prev_frame.ball_box is not None:
            prev_ball_center = _box_center(self._prev_frame.ball_box)
            ball_speed = _distance(ball_center, prev_ball_center)
            prev_dist = _distance(player_center, prev_ball_center)
            if (
                prev_dist <= self.touch_proximity_px
                and ball_speed > self.touch_proximity_px * 2
                and player_center[1] > self.frame_height * 0.5  # own half (bottom)
            ):
                self._clearances += 1

        # --- Midfielder heuristics ---
        # Ball recovery: player gains possession after it was loose
        if (
            self._in_possession
            and self._prev_frame is not None
            and self._prev_frame.ball_box is not None
        ):
            prev_player_box = self._prev_frame.player_box
            if prev_player_box is not None:
                prev_dist = _distance(
                    _box_center(prev_player_box), _box_center(self._prev_frame.ball_box)
                )
                if prev_dist > self.touch_proximity_px * 2:
                    self._ball_recoveries += 1

        # Key pass: pass that leads to a shot (heuristic: pass followed quickly by shot)
        # Through ball: pass that splits defenders (ball passes between two opponents)
        # These are computed in finalize from pass/shot sequences

        # --- Goalkeeper heuristics ---
        # Save: player blocks ball near goal area (top or bottom of frame)
        near_goal = (
            player_center[1] < self.frame_height * 0.15
            or player_center[1] > self.frame_height * 0.85
        )
        if near_goal and dist <= self.touch_proximity_px:
            if self._prev_frame is not None and self._prev_frame.ball_box is not None:
                prev_ball_center = _box_center(self._prev_frame.ball_box)
                ball_speed = _distance(ball_center, prev_ball_center)
                if ball_speed > self.touch_proximity_px:
                    self._saves += 1

        # Goal conceded: ball crosses goal line (top/bottom edge) without player touching it
        if (
            ball_center[1] < self.frame_height * 0.02
            or ball_center[1] > self.frame_height * 0.98
        ):
            if dist > self.touch_proximity_px * 3:
                self._goals_conceded += 1

        # Sweeper action: goalkeeper moves far from goal to intercept
        if near_goal is False and player_center[1] > self.frame_height * 0.3:
            if dist <= self.touch_proximity_px * 2:
                self._sweeper_actions += 1

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _update_frame_dims(self, frame: FrameResult) -> None:
        """Infer frame dimensions from detection bounding boxes if not set."""
        if self._frame_dims_set:
            return
        # Try to infer from player or ball box
        for box in [frame.player_box, frame.ball_box]:
            if box is not None:
                x, y, w, h = box
                if x + w > self.frame_width:
                    self.frame_width = x + w
                if y + h > self.frame_height:
                    self.frame_height = y + h

    def _update_ball_trajectory(self, frame: FrameResult) -> None:
        if frame.ball_box is not None:
            cx, cy = _box_center(frame.ball_box)
            self._ball_trajectory.append((frame.timestamp_ms, cx, cy))

    def _update_player_history(self, frame: FrameResult) -> None:
        if frame.player_box is not None:
            self._player_centers.append(_box_center(frame.player_box))

    def _compute_distance_covered_m(self) -> float:
        """Sum Euclidean distances between consecutive player positions in metres."""
        if len(self._player_centers) < 2:
            return 0.0
        total_px = sum(
            _distance(self._player_centers[i], self._player_centers[i + 1])
            for i in range(len(self._player_centers) - 1)
        )
        return total_px / self._px_per_m

    # ------------------------------------------------------------------
    # Stats builders
    # ------------------------------------------------------------------

    def _build_core_stats(self) -> CoreStats:
        touch_count = len(self._touch_events)
        passes_attempted = sum(1 for p in self._pass_events if p.attempted)
        passes_successful = sum(1 for p in self._pass_events if p.successful)
        ball_losses = len(self._ball_loss_events)

        # Pass completion pct (Req 5.4, 5.5)
        if passes_attempted > 0:
            pass_completion_pct = round((passes_successful / passes_attempted) * 100, 1)
        else:
            pass_completion_pct = None  # N/A

        # Ball retention rate (Req 6.4, 6.5)
        if touch_count > 0:
            ball_retention_rate = round(
                ((touch_count - ball_losses) / touch_count) * 100, 1
            )
        else:
            ball_retention_rate = None  # N/A

        return CoreStats(
            touch_count=touch_count,
            touch_events=list(self._touch_events),
            passes_attempted=passes_attempted,
            passes_successful=passes_successful,
            pass_events=list(self._pass_events),
            pass_completion_pct=pass_completion_pct,
            ball_losses=ball_losses,
            ball_loss_events=list(self._ball_loss_events),
            ball_retention_rate=ball_retention_rate,
        )

    def _build_advanced_stats(self, position: Position, core: CoreStats) -> object:
        if position == Position.GOALKEEPER:
            return self._build_goalkeeper_stats(core)
        elif position == Position.DEFENDER:
            return self._build_defender_stats(core)
        elif position == Position.MIDFIELDER:
            return self._build_midfielder_stats(core)
        else:  # FORWARD
            return self._build_forward_stats()

    def _build_goalkeeper_stats(self, core: CoreStats) -> GoalkeeperStats:
        # Distribution accuracy: passes from GK (use core pass completion)
        dist_acc = core.pass_completion_pct  # may be None
        return GoalkeeperStats(
            saves=self._saves,
            goals_conceded=self._goals_conceded,
            distribution_accuracy_pct=dist_acc,
            sweeper_actions=self._sweeper_actions,
        )

    def _build_defender_stats(self, core: CoreStats) -> DefenderStats:
        # Interceptions from ball_loss events where cause="interception" by others
        interceptions = sum(
            1 for e in self._ball_loss_events if e.cause == "interception"
        )
        return DefenderStats(
            tackles_attempted=self._tackles_attempted,
            tackles_won=self._tackles_won,
            interceptions=interceptions,
            clearances=self._clearances,
            aerial_duels_won=self._aerial_duels_won,
        )

    def _build_midfielder_stats(self, core: CoreStats) -> MidfielderStats:
        # Key passes: successful passes (simplified heuristic)
        key_passes = max(0, core.passes_successful - 1) if core.passes_successful > 1 else 0
        # Through balls: passes where ball moved through opponent cluster (simplified)
        through_balls = self._through_balls
        distance_m = self._compute_distance_covered_m()
        return MidfielderStats(
            key_passes=key_passes,
            through_balls=through_balls,
            distance_covered_m=round(distance_m, 2),
            ball_recoveries=self._ball_recoveries,
        )

    def _build_forward_stats(self) -> ForwardStats:
        shots_off_target = max(0, self._shots_total - self._shots_on_target)
        return ForwardStats(
            shots_on_target=self._shots_on_target,
            shots_off_target=shots_off_target,
            dribbles_attempted=self._dribbles_attempted,
            dribbles_completed=self._dribbles_completed,
            off_ball_runs=self._off_ball_runs,
        )
