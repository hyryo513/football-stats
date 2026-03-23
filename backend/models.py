"""Pydantic v2 data models for the Soccer Player Tracker."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional, Union

from pydantic import BaseModel, Field


class VideoSource(BaseModel):
    type: Literal["file", "url"]
    path: str  # local path or URL string


class PlayerRef(BaseModel):
    method: Literal["jersey", "bbox"]
    jersey_number: Optional[int] = None
    jersey_color: Optional[str] = None  # e.g. "red", "blue" — supplementary HSV color hint
    bbox: Optional[tuple[int, int, int, int]] = None  # x, y, w, h in frame-0 pixels
    bbox_timestamp_ms: Optional[int] = None  # selected frame timestamp for bbox mode


class Position(str, Enum):
    GOALKEEPER = "goalkeeper"
    DEFENDER = "defender"
    MIDFIELDER = "midfielder"
    FORWARD = "forward"


class TouchEvent(BaseModel):
    timestamp_ms: int
    frame_idx: int
    confidence: float


class PassEvent(BaseModel):
    timestamp_ms: int
    attempted: bool
    successful: bool


class BallLossEvent(BaseModel):
    timestamp_ms: int
    frame_idx: int
    cause: Literal["tackle", "interception", "miscontrol"]


class CoreStats(BaseModel):
    touch_count: int
    touch_events: list[TouchEvent]
    passes_attempted: int
    passes_successful: int
    pass_events: list[PassEvent]
    pass_completion_pct: Optional[float] = None  # None → "N/A"
    ball_losses: int
    ball_loss_events: list[BallLossEvent]
    ball_retention_rate: Optional[float] = None  # None → "N/A"


class GoalkeeperStats(BaseModel):
    saves: int
    goals_conceded: int
    distribution_accuracy_pct: Optional[float] = None
    sweeper_actions: int


class DefenderStats(BaseModel):
    tackles_attempted: int
    tackles_won: int
    interceptions: int
    clearances: int
    aerial_duels_won: int


class MidfielderStats(BaseModel):
    key_passes: int
    through_balls: int
    distance_covered_m: float
    ball_recoveries: int


class ForwardStats(BaseModel):
    shots_on_target: int
    shots_off_target: int
    dribbles_attempted: int
    dribbles_completed: int
    off_ball_runs: int


class StatsReport(BaseModel):
    session_id: str
    created_at: datetime
    video_source: str  # path or URL
    player_ref: PlayerRef
    position: Position
    analysis_duration_s: float
    core: CoreStats
    advanced: Union[GoalkeeperStats, DefenderStats, MidfielderStats, ForwardStats]
    debug_clips: dict[str, list[str]] = Field(default_factory=dict)
    tracking_summary: dict[str, object] = Field(default_factory=dict)
    analyzer_diagnostics: dict[str, object] = Field(default_factory=dict)


class SessionSummary(BaseModel):
    session_id: str
    created_at: datetime
    video_source: str
    player_ref: PlayerRef
    position: Position


class DownloadResult(BaseModel):
    local_path: str
    duration_s: float
    width: int
    height: int


class Detection(BaseModel):
    track_id: int
    bbox: tuple[int, int, int, int]
    label: str
    confidence: float


class FrameResult(BaseModel):
    frame_idx: int
    timestamp_ms: int
    player_box: Optional[tuple[int, int, int, int]] = None
    ball_box: Optional[tuple[int, int, int, int]] = None
    confidence: float
    all_detections: list[Detection]
