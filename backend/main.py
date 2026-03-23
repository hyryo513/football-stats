"""FastAPI application for the Soccer Player Tracker.

Exposes REST endpoints and SSE progress streaming for the analysis pipeline.
Run with: uvicorn backend.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os

# Enable MPS fallback for ops not implemented on Apple Silicon (e.g. torchvision::nms)
if "PYTORCH_ENABLE_MPS_FALLBACK" not in os.environ:
    os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"

import asyncio
import json
import logging
import mimetypes
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import AsyncIterator, Literal, Optional

import shutil

import cv2
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import downloader, persistence
from backend.analyzer import Analyzer
from backend.errors import (
    AuthenticationError,
    CorruptedFileError,
    ExportError,
    MalformedURLError,
    PersistenceError,
    PlayerNotFoundError,
    UnavailableSourceError,
    UnsupportedFormatError,
)
from backend.models import PlayerRef, Position, VideoSource
from backend.report_builder import ReportBuilder
from backend.tracker import Tracker
from backend.youtube_auth import YouTubeAuthManager

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_LOG_DIR = Path.home() / ".soccer-tracker"
_LOG_DIR.mkdir(parents=True, exist_ok=True)
_DEBUG_EXPORT_DIR = _LOG_DIR / "exports" / "debug"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(_LOG_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------

_STATUS_PENDING = "pending"
_STATUS_RUNNING = "running"
_STATUS_COMPLETED = "completed"
_STATUS_CANCELLED = "cancelled"
_STATUS_FAILED = "failed"


@dataclass
class SessionState:
    session_id: str
    status: str = _STATUS_PENDING
    progress: int = 0
    report: Optional[object] = None
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    error: Optional[str] = None


# In-memory session registry
_sessions: dict[str, SessionState] = {}

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartSessionRequest(BaseModel):
    video_source: VideoSource
    player_ref: PlayerRef
    position: Position


class ExportRequest(BaseModel):
    format: Literal["pdf", "json"]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="Soccer Player Tracker")

# ---------------------------------------------------------------------------
# Error → HTTP status helper
# ---------------------------------------------------------------------------


def _http_error_for(exc: Exception) -> HTTPException:
    """Map domain exceptions to appropriate HTTP status codes."""
    if isinstance(exc, (UnsupportedFormatError, CorruptedFileError, MalformedURLError, PlayerNotFoundError)):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, UnavailableSourceError):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, AuthenticationError):
        return HTTPException(status_code=401, detail=str(exc))
    if isinstance(exc, ExportError):
        return HTTPException(status_code=500, detail=str(exc))
    if isinstance(exc, PersistenceError):
        msg = exc.reason.lower()
        if "not found" in msg:
            return HTTPException(status_code=404, detail=str(exc))
        return HTTPException(status_code=507, detail=str(exc))
    return HTTPException(status_code=500, detail=str(exc))

# ---------------------------------------------------------------------------
# Background pipeline
# ---------------------------------------------------------------------------


async def _run_pipeline(
    session_id: str,
    video_source: VideoSource,
    player_ref: PlayerRef,
    position: Position,
) -> None:
    """Full analysis pipeline executed as an asyncio background task."""
    state = _sessions[session_id]
    state.status = _STATUS_RUNNING

    try:
        # --- 1. Download (progress 0-50) ---
        def _download_progress(pct: int) -> None:
            if not state.cancel_event.is_set():
                state.progress = int(pct * 0.5)  # scale to 0-50

        loop = asyncio.get_event_loop()
        download_result = await loop.run_in_executor(
            None,
            lambda: downloader.download(video_source.path, _download_progress),
        )

        if state.cancel_event.is_set():
            state.status = _STATUS_CANCELLED
            return

        state.progress = 50

        # --- 2. Initialize tracker ---
        tracker = Tracker(download_result.local_path, player_ref)
        await loop.run_in_executor(None, tracker.initialize)

        if state.cancel_event.is_set():
            state.status = _STATUS_CANCELLED
            return

        # --- 3. Track frames + analyze (progress 50-95) ---
        analyzer = Analyzer(
            video_fps=download_result.duration_s and 30.0,
            frame_width=download_result.width,
            frame_height=download_result.height,
        )

        import cv2
        cap_check = cv2.VideoCapture(download_result.local_path)
        total_frames = int(cap_check.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
        cap_check.release()

        analysis_start = time.monotonic()
        frame_count = 0

        def _process_frames() -> None:
            nonlocal frame_count
            for frame_result in tracker.track_frames():
                if state.cancel_event.is_set():
                    break
                analyzer.process_frame(frame_result)
                frame_count += 1
                # Update progress 50-95
                pct = 50 + int((frame_count / total_frames) * 45)
                state.progress = min(pct, 95)

        await loop.run_in_executor(None, _process_frames)

        if state.cancel_event.is_set():
            state.status = _STATUS_CANCELLED
            return

        analysis_duration = time.monotonic() - analysis_start

        # --- 4. Build report ---
        report_builder = ReportBuilder()
        report = report_builder.build(
            session_id=session_id,
            video_source=video_source.path,
            player_ref=player_ref,
            position=position,
            analyzer=analyzer,
            analysis_duration_s=analysis_duration,
        )
        if hasattr(tracker, "get_tracking_summary"):
            tracking_summary = tracker.get_tracking_summary()
        else:
            tracking_summary = {
                "total_reacquires": 0,
                "unique_track_ids_used": [],
                "frames_total": frame_count,
                "frames_confident": 0,
                "confident_frame_pct": 0.0,
            }
        if hasattr(analyzer, "get_diagnostics"):
            analyzer_diagnostics = analyzer.get_diagnostics()
        else:
            analyzer_diagnostics = {}
        logger.info(
            "Tracking summary session=%s reacquires=%s unique_ids=%s confident_pct=%.2f",
            session_id,
            tracking_summary.get("total_reacquires"),
            tracking_summary.get("unique_track_ids_used"),
            tracking_summary.get("confident_frame_pct", 0.0),
        )
        logger.info(
            "Analyzer diagnostics session=%s ball_detect=%.1f%% player_detect=%.1f%% both=%.1f%%",
            session_id,
            analyzer_diagnostics.get("ball_detection_pct", 0.0),
            analyzer_diagnostics.get("player_detection_pct", 0.0),
            analyzer_diagnostics.get("both_detection_pct", 0.0),
        )

        # --- 4b. Generate debug clips (touch/pass/loss event windows) ---
        debug_clips = await loop.run_in_executor(
            None,
            lambda: _generate_debug_clips(
                session_id=session_id,
                local_video_path=download_result.local_path,
                report=report,
            ),
        )
        report = report.model_copy(
            update={
                "debug_clips": debug_clips,
                "tracking_summary": tracking_summary,
                "analyzer_diagnostics": analyzer_diagnostics,
            }
        )

        # --- 5. Save to persistence ---
        await loop.run_in_executor(None, lambda: persistence.save_session(report))

        state.report = report
        state.progress = 100
        state.status = _STATUS_COMPLETED

    except Exception as exc:
        logger.exception("Pipeline failed for session %s", session_id)
        state.status = _STATUS_FAILED
        state.error = str(exc)


def _format_ms_for_filename(timestamp_ms: int) -> str:
    secs = max(0, int(timestamp_ms)) // 1000
    m, s = divmod(secs, 60)
    return f"{m:02d}m{s:02d}s"


def _clip_path_for(session_id: str, filename: str) -> Path:
    clip_dir = _DEBUG_EXPORT_DIR / session_id
    clip_dir.mkdir(parents=True, exist_ok=True)
    return clip_dir / filename


def _write_event_clip(
    cap: cv2.VideoCapture,
    fps: float,
    width: int,
    height: int,
    out_path: Path,
    event_timestamp_ms: int,
    pre_s: float = 2.0,
    post_s: float = 2.0,
) -> bool:
    """Write a short mp4 clip around an event timestamp using a shared capture."""
    try:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(out_path), fourcc, fps, (width, height))
        if not writer.isOpened():
            return False

        start_ms = max(0, int(event_timestamp_ms - (pre_s * 1000)))
        end_ms = max(start_ms + 1, int(event_timestamp_ms + (post_s * 1000)))
        cap.set(cv2.CAP_PROP_POS_MSEC, start_ms)

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            current_ms = int(cap.get(cv2.CAP_PROP_POS_MSEC))
            if current_ms > end_ms:
                break
            writer.write(frame)
        writer.release()
        return out_path.exists() and out_path.stat().st_size > 0
    except Exception:
        return False


def _generate_debug_clips(session_id: str, local_video_path: str, report) -> dict[str, list[str]]:
    """Generate per-event debug clips and return manifest paths."""
    manifest: dict[str, list[str]] = {
        "touches": [],
        "passes_attempted": [],
        "passes_successful": [],
        "ball_losses": [],
        "tracking_samples": [],
    }
    if not Path(local_video_path).exists():
        return manifest

    # Open source video once and reuse for all clips.
    cap = cv2.VideoCapture(local_video_path)
    if not cap.isOpened():
        logger.warning("Clip generation: cannot open source video %s", local_video_path)
        return manifest

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
    total_requested = 0
    total_ok = 0

    try:
        # Redirect stderr to suppress noisy ffmpeg/OpenCV warnings during seeks.
        import os as _os, contextlib as _ctx

        devnull_fd = _os.open(_os.devnull, _os.O_WRONLY)
        saved_stderr_fd = _os.dup(2)
        _os.dup2(devnull_fd, 2)

        try:
            for i, evt in enumerate(report.core.touch_events):
                filename = f"touch_{i:03d}_{_format_ms_for_filename(evt.timestamp_ms)}.mp4"
                out_path = _clip_path_for(session_id, filename)
                total_requested += 1
                if _write_event_clip(cap, fps, width, height, out_path, evt.timestamp_ms):
                    manifest["touches"].append(str(out_path))
                    total_ok += 1

            for i, evt in enumerate(report.core.pass_events):
                suffix = "success" if evt.successful else "attempt"
                filename = f"pass_{i:03d}_{suffix}_{_format_ms_for_filename(evt.timestamp_ms)}.mp4"
                out_path = _clip_path_for(session_id, filename)
                total_requested += 1
                if _write_event_clip(cap, fps, width, height, out_path, evt.timestamp_ms):
                    manifest["passes_attempted"].append(str(out_path))
                    total_ok += 1
                    if evt.successful:
                        manifest["passes_successful"].append(str(out_path))

            for i, evt in enumerate(report.core.ball_loss_events):
                filename = (
                    f"ball_loss_{i:03d}_{evt.cause}_{_format_ms_for_filename(evt.timestamp_ms)}.mp4"
                )
                out_path = _clip_path_for(session_id, filename)
                total_requested += 1
                if _write_event_clip(cap, fps, width, height, out_path, evt.timestamp_ms):
                    manifest["ball_losses"].append(str(out_path))
                    total_ok += 1

            duration_ms = max(0, int(report.analysis_duration_s * 1000))
            sample_points = [0]
            if duration_ms > 0:
                sample_points.extend([duration_ms // 2, max(0, duration_ms - 1000)])
            for i, ts_ms in enumerate(sorted(set(sample_points))):
                filename = f"sample_{i:03d}_{_format_ms_for_filename(ts_ms)}.mp4"
                out_path = _clip_path_for(session_id, filename)
                total_requested += 1
                if _write_event_clip(cap, fps, width, height, out_path, ts_ms, pre_s=1.5, post_s=1.5):
                    manifest["tracking_samples"].append(str(out_path))
                    total_ok += 1
        finally:
            _os.dup2(saved_stderr_fd, 2)
            _os.close(saved_stderr_fd)
            _os.close(devnull_fd)
    finally:
        cap.release()

    logger.info(
        "Clip generation session=%s: %d/%d clips written successfully",
        session_id, total_ok, total_requested,
    )
    return manifest


def _list_debug_clips_from_fs(session_id: str) -> dict[str, list[str]]:
    clip_dir = _DEBUG_EXPORT_DIR / session_id
    if not clip_dir.exists():
        return {}
    manifest: dict[str, list[str]] = {}
    for clip in sorted(clip_dir.glob("*.mp4")):
        key = clip.name.split("_", 1)[0]
        manifest.setdefault(key, []).append(str(clip))
    return manifest

# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.post("/sessions", status_code=202)
async def start_session(body: StartSessionRequest) -> dict:
    """Start a new analysis session and return immediately."""
    session_id = str(uuid.uuid4())
    state = SessionState(session_id=session_id)
    _sessions[session_id] = state

    asyncio.create_task(
        _run_pipeline(session_id, body.video_source, body.player_ref, body.position)
    )

    return {"session_id": session_id, "status": _STATUS_PENDING}


@app.get("/sessions")
async def list_sessions() -> list:
    """Return list of SessionSummary from persistence."""
    try:
        summaries = persistence.list_sessions()
        return [s.model_dump(mode="json") for s in summaries]
    except PersistenceError as exc:
        raise _http_error_for(exc)


@app.get("/sessions/{session_id}")
async def get_session(session_id: str) -> dict:
    """Return StatsReport for a completed session from persistence."""
    try:
        report = persistence.load_session(session_id)
        return report.model_dump(mode="json")
    except PersistenceError as exc:
        raise _http_error_for(exc)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str) -> None:
    """Delete a session; returns 404 if not found."""
    try:
        persistence.delete_session(session_id)
        _sessions.pop(session_id, None)
    except PersistenceError as exc:
        raise _http_error_for(exc)


@app.post("/sessions/{session_id}/cancel")
async def cancel_session(session_id: str) -> dict:
    """Cancel a running session; discards partial results within 3 seconds."""
    state = _sessions.get(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    state.cancel_event.set()

    # Wait up to 3 seconds for the pipeline to acknowledge cancellation
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if state.status in (_STATUS_CANCELLED, _STATUS_COMPLETED, _STATUS_FAILED):
            break
        await asyncio.sleep(0.1)

    # Force status to cancelled if pipeline hasn't updated yet
    if state.status not in (_STATUS_COMPLETED, _STATUS_FAILED):
        state.status = _STATUS_CANCELLED

    return {"session_id": session_id, "status": state.status}


@app.post("/sessions/{session_id}/export")
async def export_session(session_id: str, body: ExportRequest) -> FileResponse:
    """Export a session report as PDF or JSON; returns the file or 500 on error."""
    try:
        report = persistence.load_session(session_id)
    except PersistenceError as exc:
        raise _http_error_for(exc)

    export_dir = _LOG_DIR / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)

    builder = ReportBuilder()
    try:
        if body.format == "json":
            out_path = str(export_dir / f"{session_id}.json")
            builder.export_json(report, out_path)
            return FileResponse(
                out_path,
                media_type="application/json",
                filename=f"session_{session_id}.json",
            )
        else:  # pdf
            out_path = str(export_dir / f"{session_id}.pdf")
            builder.export_pdf(report, out_path)
            return FileResponse(
                out_path,
                media_type="application/pdf",
                filename=f"session_{session_id}.pdf",
            )
    except ExportError as exc:
        logger.exception("Export failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/sessions/{session_id}/clips")
async def list_session_clips(session_id: str) -> dict:
    """List generated debug clips for a session."""
    try:
        report = persistence.load_session(session_id)
        clips = report.debug_clips or _list_debug_clips_from_fs(session_id)
        return {"session_id": session_id, "clips": clips}
    except PersistenceError as exc:
        raise _http_error_for(exc)


@app.get("/sessions/{session_id}/clips/{clip_name}")
async def download_session_clip(session_id: str, clip_name: str) -> FileResponse:
    """Download a single generated debug clip by filename."""
    if "/" in clip_name or ".." in clip_name or not clip_name.endswith(".mp4"):
        raise HTTPException(status_code=400, detail="Invalid clip name")

    clip_path = (_DEBUG_EXPORT_DIR / session_id / clip_name).resolve()
    expected_root = (_DEBUG_EXPORT_DIR / session_id).resolve()
    if expected_root not in clip_path.parents:
        raise HTTPException(status_code=400, detail="Invalid clip path")
    if not clip_path.exists():
        raise HTTPException(status_code=404, detail=f"Clip not found: {clip_name}")

    return FileResponse(
        path=str(clip_path),
        media_type="video/mp4",
        filename=clip_name,
    )


@app.get("/sessions/{session_id}/progress")
async def session_progress(session_id: str) -> StreamingResponse:
    """SSE stream of progress events for a session."""
    if session_id not in _sessions:
        raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

    async def _event_generator() -> AsyncIterator[str]:
        while True:
            state = _sessions.get(session_id)
            if state is None:
                break

            payload = json.dumps({
                "session_id": session_id,
                "status": state.status,
                "progress": state.progress,
                "error": state.error,
            })
            yield f"data: {payload}\n\n"

            if state.status in (_STATUS_COMPLETED, _STATUS_CANCELLED, _STATUS_FAILED):
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        _event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)) -> dict:
    """Accept a video file upload, save it server-side, return the local path."""
    upload_dir = _LOG_DIR / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "upload"
    ext = Path(filename).suffix.lstrip(".").lower()
    allowed = {"mp4", "mov", "avi", "mkv"}
    if ext not in allowed:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported format '.{ext}'. Accepted: {', '.join(sorted(allowed))}",
        )

    dest = upload_dir / filename
    try:
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}")
    finally:
        await file.close()

    # Read metadata immediately so the frontend can display it
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None, lambda: downloader.download(str(dest))
        )
        return {"local_path": str(dest), **result.model_dump(mode="json")}
    except (UnsupportedFormatError, CorruptedFileError) as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        logger.exception("upload metadata read failed for %s", dest)
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/uploads")
async def clear_uploads() -> dict:
    """Delete all files in the UploadStore (~/.soccer-tracker/uploads/)."""
    upload_dir = _LOG_DIR / "uploads"
    if not upload_dir.exists():
        return {"deleted": 0}
    count = 0
    for f in upload_dir.iterdir():
        if f.is_file():
            f.unlink()
            count += 1
    return {"deleted": count}


@app.get("/uploads")
async def list_uploads() -> list[dict]:
    """List uploaded local videos for quick reuse in the frontend."""
    upload_dir = _LOG_DIR / "uploads"
    if not upload_dir.exists():
        return []
    rows: list[dict] = []
    for f in upload_dir.iterdir():
        if not f.is_file():
            continue
        ext = f.suffix.lower().lstrip(".")
        if ext not in {"mp4", "mov", "avi", "mkv"}:
            continue
        stat = f.stat()
        rows.append(
            {
                "name": f.name,
                "path": str(f),
                "size_bytes": stat.st_size,
                "modified_at": stat.st_mtime,
            }
        )
    rows.sort(key=lambda x: x["modified_at"], reverse=True)
    return rows


@app.get("/uploads/stream/{file_name}")
async def stream_uploaded_video(file_name: str) -> FileResponse:
    """Stream a previously uploaded video by filename."""
    if "/" in file_name or ".." in file_name:
        raise HTTPException(status_code=400, detail="Invalid upload filename")
    upload_dir = _LOG_DIR / "uploads"
    path = (upload_dir / file_name).resolve()
    if upload_dir.resolve() not in path.parents:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Upload not found: {file_name}")
    if path.suffix.lower().lstrip(".") not in {"mp4", "mov", "avi", "mkv"}:
        raise HTTPException(status_code=422, detail="Unsupported upload format")
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path=str(path),
        media_type=media_type or "video/mp4",
        filename=path.name,
        content_disposition_type="inline",
    )


@app.get("/video/metadata")
async def video_metadata(source: str) -> dict:
    """Return metadata for a video source (URL only; local files use /upload)."""
    try:
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, lambda: downloader.download(source))
        return result.model_dump(mode="json")
    except (UnsupportedFormatError, CorruptedFileError, MalformedURLError, PlayerNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnavailableSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("video/metadata failed for source %s", source)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/video/frame0")
async def video_frame0(source: str) -> Response:
    """Return the first frame of a video source as JPEG."""
    try:
        loop = asyncio.get_event_loop()
        local_path = source
        if source.startswith("http://") or source.startswith("https://"):
            result = await loop.run_in_executor(None, lambda: downloader.download(source))
            local_path = result.local_path

        def _read_first_frame(path: str) -> bytes:
            cap = cv2.VideoCapture(path)
            try:
                if not cap.isOpened():
                    raise CorruptedFileError(file_path=path)
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise CorruptedFileError(file_path=path)
                ok, encoded = cv2.imencode(".jpg", frame)
                if not ok:
                    raise CorruptedFileError(file_path=path)
                return bytes(encoded)
            finally:
                cap.release()

        frame_bytes = await loop.run_in_executor(None, lambda: _read_first_frame(local_path))
        return Response(content=frame_bytes, media_type="image/jpeg")
    except (UnsupportedFormatError, CorruptedFileError, MalformedURLError, PlayerNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnavailableSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("video/frame0 failed for source %s", source)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/video/frame")
async def video_frame(source: str, timestamp_ms: int = 0) -> Response:
    """Return a frame at a given timestamp (ms) as JPEG."""
    try:
        loop = asyncio.get_event_loop()
        local_path = source
        if source.startswith("http://") or source.startswith("https://"):
            result = await loop.run_in_executor(None, lambda: downloader.download(source))
            local_path = result.local_path

        def _read_frame_at(path: str, ts_ms: int) -> bytes:
            cap = cv2.VideoCapture(path)
            try:
                if not cap.isOpened():
                    raise CorruptedFileError(file_path=path)
                cap.set(cv2.CAP_PROP_POS_MSEC, max(0, int(ts_ms)))
                ok, frame = cap.read()
                if not ok or frame is None:
                    raise CorruptedFileError(file_path=path)
                ok, encoded = cv2.imencode(".jpg", frame)
                if not ok:
                    raise CorruptedFileError(file_path=path)
                return bytes(encoded)
            finally:
                cap.release()

        frame_bytes = await loop.run_in_executor(
            None, lambda: _read_frame_at(local_path, timestamp_ms)
        )
        return Response(content=frame_bytes, media_type="image/jpeg")
    except (UnsupportedFormatError, CorruptedFileError, MalformedURLError, PlayerNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnavailableSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("video/frame failed for source %s @ %sms", source, timestamp_ms)
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/video/stream")
async def video_stream(source: str) -> FileResponse:
    """Return a playable local video file for preview/seek in the frontend."""
    try:
        loop = asyncio.get_event_loop()
        local_path = source
        if source.startswith("http://") or source.startswith("https://"):
            # Resolve remote source to a local cached/downloaded file first.
            result = await loop.run_in_executor(None, lambda: downloader.download(source))
            local_path = result.local_path

        path = Path(local_path).expanduser().resolve()
        if not path.exists() or not path.is_file():
            raise CorruptedFileError(file_path=str(path))
        if path.suffix.lower().lstrip(".") not in {"mp4", "mov", "avi", "mkv"}:
            raise UnsupportedFormatError(accepted_formats=["mp4", "mov", "avi", "mkv"])

        media_type, _ = mimetypes.guess_type(str(path))
        return FileResponse(
            path=str(path),
            media_type=media_type or "video/mp4",
            filename=path.name,
            content_disposition_type="inline",
        )
    except (UnsupportedFormatError, CorruptedFileError, MalformedURLError, PlayerNotFoundError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except UnavailableSourceError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    except Exception as exc:
        logger.exception("video/stream failed for source %s", source)
        raise HTTPException(status_code=500, detail=str(exc))


# ---------------------------------------------------------------------------
# Static frontend (must be mounted last so API routes take priority)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# YouTube OAuth
# ---------------------------------------------------------------------------

_youtube_auth = YouTubeAuthManager()


@app.get("/auth/youtube")
async def auth_youtube_start() -> RedirectResponse:
    """Redirect to Google OAuth2 consent screen."""
    try:
        auth_url = _youtube_auth.get_auth_url()
        return RedirectResponse(url=auth_url)
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.get("/auth/youtube/callback")
async def auth_youtube_callback(code: str) -> RedirectResponse:
    """OAuth2 callback; exchange code for token and redirect to frontend."""
    try:
        _youtube_auth.exchange_code(code)
        return RedirectResponse(url="/?youtube=connected")
    except AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=str(exc))


@app.delete("/auth/youtube", status_code=204)
async def auth_youtube_revoke() -> None:
    """Disconnect YouTube account; delete stored token."""
    _youtube_auth.revoke()


@app.get("/auth/youtube/status")
async def auth_youtube_status() -> dict:
    """Return current auth state."""
    return {"connected": _youtube_auth.is_connected()}


# ---------------------------------------------------------------------------
# Static frontend (must be mounted last so API routes take priority)
# ---------------------------------------------------------------------------

_FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
if _FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIR), html=True), name="frontend")
