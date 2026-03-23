"""Report builder: assembles StatsReport and handles PDF/JSON export."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Union

from backend.analyzer import Analyzer
from backend.errors import ExportError
from backend.models import (
    DefenderStats,
    ForwardStats,
    GoalkeeperStats,
    MidfielderStats,
    PlayerRef,
    Position,
    StatsReport,
)


class ReportBuilder:
    """Assembles StatsReport objects and exports them to JSON or PDF."""

    def build(
        self,
        session_id: str,
        video_source: str,
        player_ref: PlayerRef,
        position: Position,
        analyzer: Analyzer,
        analysis_duration_s: float,
    ) -> StatsReport:
        """Assemble a StatsReport from analyzer state and session metadata."""
        core, advanced = analyzer.finalize(position)
        return StatsReport(
            session_id=session_id,
            created_at=datetime.now(timezone.utc),
            video_source=video_source,
            player_ref=player_ref,
            position=position,
            analysis_duration_s=analysis_duration_s,
            core=core,
            advanced=advanced,
        )

    def export_json(self, report: StatsReport, path: str) -> None:
        """Serialize StatsReport to a JSON file.

        Raises:
            ExportError: if the file cannot be written.
        """
        try:
            content = report.model_dump_json(indent=2)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as exc:
            raise ExportError("json", str(exc)) from exc

    def export_pdf(self, report: StatsReport, path: str) -> None:
        """Generate a PDF report using reportlab.

        Raises:
            ExportError: if the PDF cannot be generated.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import cm
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            doc = SimpleDocTemplate(
                path,
                pagesize=A4,
                rightMargin=2 * cm,
                leftMargin=2 * cm,
                topMargin=2 * cm,
                bottomMargin=2 * cm,
            )
            styles = getSampleStyleSheet()
            story = []

            # --- Title ---
            story.append(Paragraph("Soccer Player Analysis Report", styles["Title"]))
            story.append(Spacer(1, 0.4 * cm))

            # --- Session metadata ---
            story.append(Paragraph("Session Information", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))

            player_id = _player_identifier(report.player_ref)
            meta_data = [
                ["Session ID", report.session_id],
                ["Created At", report.created_at.isoformat()],
                ["Video Source", report.video_source],
                ["Player", player_id],
                ["Position", report.position.value.capitalize()],
                ["Analysis Duration (s)", f"{report.analysis_duration_s:.2f}"],
            ]
            meta_table = Table(meta_data, colWidths=[5 * cm, 12 * cm])
            meta_table.setStyle(_table_style())
            story.append(meta_table)
            story.append(Spacer(1, 0.5 * cm))

            # --- Core stats ---
            story.append(Paragraph("Core Statistics", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))

            c = report.core
            pass_pct = f"{c.pass_completion_pct:.1f}%" if c.pass_completion_pct is not None else "N/A"
            retention = f"{c.ball_retention_rate:.1f}%" if c.ball_retention_rate is not None else "N/A"
            core_data = [
                ["Metric", "Value"],
                ["Touches", str(c.touch_count)],
                ["Passes Attempted", str(c.passes_attempted)],
                ["Passes Successful", str(c.passes_successful)],
                ["Pass Completion %", pass_pct],
                ["Ball Losses", str(c.ball_losses)],
                ["Ball Retention Rate", retention],
            ]
            core_table = Table(core_data, colWidths=[8 * cm, 9 * cm])
            core_table.setStyle(_table_style(header=True))
            story.append(core_table)
            story.append(Spacer(1, 0.5 * cm))

            # --- Advanced stats ---
            story.append(Paragraph("Advanced Statistics", styles["Heading2"]))
            story.append(Spacer(1, 0.2 * cm))

            adv_data = [["Metric", "Value"]] + _advanced_rows(report.advanced)
            adv_table = Table(adv_data, colWidths=[8 * cm, 9 * cm])
            adv_table.setStyle(_table_style(header=True))
            story.append(adv_table)
            story.append(Spacer(1, 0.8 * cm))

            # --- Footer ---
            story.append(Paragraph(
                "<i>Generated by Soccer Player Tracker</i>",
                styles["Normal"],
            ))

            doc.build(story)

        except ExportError:
            raise
        except Exception as exc:
            raise ExportError("pdf", str(exc)) from exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _player_identifier(player_ref: PlayerRef) -> str:
    if player_ref.method == "jersey" and player_ref.jersey_number is not None:
        base = f"Jersey #{player_ref.jersey_number}"
        if player_ref.jersey_color:
            return f"{base} ({player_ref.jersey_color})"
        return base
    if player_ref.method == "bbox" and player_ref.bbox is not None:
        x, y, w, h = player_ref.bbox
        if player_ref.bbox_timestamp_ms is not None:
            ts_s = player_ref.bbox_timestamp_ms / 1000.0
            return f"BBox ({x}, {y}, {w}×{h}) @ {ts_s:.2f}s"
        return f"BBox ({x}, {y}, {w}×{h})"
    return "Unknown"


def _table_style(header: bool = False) -> TableStyle:
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle

    cmds = [
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey if header else colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold" if header else "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    return TableStyle(cmds)


def _advanced_rows(
    advanced: Union[GoalkeeperStats, DefenderStats, MidfielderStats, ForwardStats],
) -> list[list[str]]:
    if isinstance(advanced, GoalkeeperStats):
        dist = (
            f"{advanced.distribution_accuracy_pct:.1f}%"
            if advanced.distribution_accuracy_pct is not None
            else "N/A"
        )
        return [
            ["Saves", str(advanced.saves)],
            ["Goals Conceded", str(advanced.goals_conceded)],
            ["Distribution Accuracy", dist],
            ["Sweeper Actions", str(advanced.sweeper_actions)],
        ]
    if isinstance(advanced, DefenderStats):
        return [
            ["Tackles Attempted", str(advanced.tackles_attempted)],
            ["Tackles Won", str(advanced.tackles_won)],
            ["Interceptions", str(advanced.interceptions)],
            ["Clearances", str(advanced.clearances)],
            ["Aerial Duels Won", str(advanced.aerial_duels_won)],
        ]
    if isinstance(advanced, MidfielderStats):
        return [
            ["Key Passes", str(advanced.key_passes)],
            ["Through Balls", str(advanced.through_balls)],
            ["Distance Covered (m)", f"{advanced.distance_covered_m:.2f}"],
            ["Ball Recoveries", str(advanced.ball_recoveries)],
        ]
    # ForwardStats
    return [
        ["Shots on Target", str(advanced.shots_on_target)],
        ["Shots off Target", str(advanced.shots_off_target)],
        ["Dribbles Attempted", str(advanced.dribbles_attempted)],
        ["Dribbles Completed", str(advanced.dribbles_completed)],
        ["Off-Ball Runs", str(advanced.off_ball_runs)],
    ]


# ---------------------------------------------------------------------------
# Module-level convenience functions
# ---------------------------------------------------------------------------

def build_report(
    session_id: str,
    video_source: str,
    player_ref: PlayerRef,
    position: Position,
    analyzer: Analyzer,
    analysis_duration_s: float,
) -> StatsReport:
    """Convenience wrapper around ReportBuilder.build()."""
    return ReportBuilder().build(
        session_id=session_id,
        video_source=video_source,
        player_ref=player_ref,
        position=position,
        analyzer=analyzer,
        analysis_duration_s=analysis_duration_s,
    )


def export_json(report: StatsReport, path: str) -> None:
    """Convenience wrapper around ReportBuilder.export_json()."""
    ReportBuilder().export_json(report, path)


def export_pdf(report: StatsReport, path: str) -> None:
    """Convenience wrapper around ReportBuilder.export_pdf()."""
    ReportBuilder().export_pdf(report, path)
