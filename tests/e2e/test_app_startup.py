"""End-to-end test: application startup per README.

Verifies that following the README instructions to start the application
results in a running server that serves the frontend and API.
"""

from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import types
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient


def _find_free_port() -> int:
    """Return a free port for the test server."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server_port() -> int:
    """Use a dynamic port to avoid conflicts with running dev servers."""
    return _find_free_port()


@pytest.fixture
def app_url(server_port: int) -> str:
    return f"http://127.0.0.1:{server_port}"


def _wait_for_server(url: str, timeout: float = 30.0) -> None:
    """Poll until the server responds or timeout."""
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        try:
            with httpx.Client(timeout=2.0) as client:
                r = client.get(url)
                if r.status_code == 200:
                    return
        except (httpx.ConnectError, httpx.ConnectTimeout):
            time.sleep(0.2)
    raise TimeoutError(f"Server at {url} did not become ready within {timeout}s")


def test_app_starts_per_readme(server_port: int, app_url: str) -> None:
    """E2E: Following the README to start the application results in a working server.

    README says to run:
      uvicorn backend.main:app --host 127.0.0.1 --port 8000

    This test spawns uvicorn, waits for it to be ready, verifies the frontend
    and API are reachable, then shuts down cleanly.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            f"--port={server_port}",
        ],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_for_server(app_url)

        with httpx.Client(timeout=5.0) as client:
            # Frontend: GET / should return HTML
            r = client.get(app_url)
            assert r.status_code == 200
            assert "text/html" in r.headers.get("content-type", "")

            # API: GET /sessions should return JSON array
            r = client.get(f"{app_url}/sessions")
            assert r.status_code == 200
            assert r.headers.get("content-type", "").startswith("application/json")

    except TimeoutError:
        proc.terminate()
        _, stderr = proc.communicate(timeout=2)
        if stderr:
            raise TimeoutError(
                f"Server did not become ready. stderr:\n{stderr}"
            ) from None
        raise
    except Exception:
        proc.terminate()
        proc.wait(timeout=2)
        raise
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


def _parse_sse_payloads(stream_text: str) -> list[dict]:
    """Extract JSON payloads from an SSE text stream."""
    payloads: list[dict] = []
    for line in stream_text.splitlines():
        if line.startswith("data: "):
            payloads.append(json.loads(line[6:]))
    return payloads


def test_upload_identify_analyze_and_get_results(monkeypatch: pytest.MonkeyPatch) -> None:
    """E2E: upload root video and run deterministic full API flow to completion."""
    project_root = Path(__file__).resolve().parent.parent.parent
    video_name = "1771873660.688000iOS1508898871.mp4"
    video_path = project_root / video_name
    assert video_path.exists(), f"Required root test video is missing: {video_path}"

    class FakeTracker:
        def __init__(self, _video_path: str, _player_ref) -> None:
            pass

        def initialize(self) -> None:
            return None

        def track_frames(self):
            for idx in range(3):
                yield {"frame_idx": idx, "timestamp_ms": idx * 100}

    fake_tracker_module = types.ModuleType("backend.tracker")
    fake_tracker_module.Tracker = FakeTracker
    monkeypatch.setitem(sys.modules, "backend.tracker", fake_tracker_module)

    import backend.main as main
    from backend.models import (
        BallLossEvent,
        CoreStats,
        DownloadResult,
        MidfielderStats,
        PassEvent,
        SessionSummary,
        StatsReport,
        TouchEvent,
    )

    report_store: dict[str, StatsReport] = {}

    def fake_download(path: str, progress_cb=None) -> DownloadResult:
        if progress_cb is not None:
            progress_cb(100)
        return DownloadResult(
            local_path=str(path),
            duration_s=12.5,
            width=1280,
            height=720,
        )

    class FakeAnalyzer:
        def __init__(self, **_kwargs) -> None:
            pass

        def process_frame(self, _frame_result) -> None:
            return None

    class FakeVideoCapture:
        def __init__(self, _path: str) -> None:
            pass

        def get(self, _prop) -> int:
            return 3

        def release(self) -> None:
            return None

    class FakeReportBuilder:
        def build(
            self,
            session_id,
            video_source,
            player_ref,
            position,
            analyzer,
            analysis_duration_s,
        ) -> StatsReport:
            _ = analyzer
            core = CoreStats(
                touch_count=4,
                touch_events=[
                    TouchEvent(timestamp_ms=0, frame_idx=0, confidence=0.9),
                    TouchEvent(timestamp_ms=100, frame_idx=1, confidence=0.91),
                    TouchEvent(timestamp_ms=200, frame_idx=2, confidence=0.92),
                    TouchEvent(timestamp_ms=300, frame_idx=3, confidence=0.93),
                ],
                passes_attempted=3,
                passes_successful=2,
                pass_events=[
                    PassEvent(timestamp_ms=180, attempted=True, successful=True),
                    PassEvent(timestamp_ms=260, attempted=True, successful=True),
                    PassEvent(timestamp_ms=340, attempted=True, successful=False),
                ],
                pass_completion_pct=66.7,
                ball_losses=1,
                ball_loss_events=[
                    BallLossEvent(timestamp_ms=220, frame_idx=2, cause="tackle")
                ],
                ball_retention_rate=75.0,
            )
            advanced = MidfielderStats(
                key_passes=1,
                through_balls=1,
                distance_covered_m=3200.0,
                ball_recoveries=2,
            )
            return StatsReport(
                session_id=session_id,
                created_at=datetime.now(tz=timezone.utc),
                video_source=video_source,
                player_ref=player_ref,
                position=position,
                analysis_duration_s=analysis_duration_s,
                core=core,
                advanced=advanced,
            )

    def fake_save_session(report: StatsReport) -> None:
        report_store[report.session_id] = report

    def fake_load_session(session_id: str) -> StatsReport:
        return report_store[session_id]

    def fake_list_sessions() -> list[SessionSummary]:
        return [
            SessionSummary(
                session_id=report.session_id,
                created_at=report.created_at,
                video_source=report.video_source,
                player_ref=report.player_ref,
                position=report.position,
            )
            for report in report_store.values()
        ]

    monkeypatch.setattr(main.downloader, "download", fake_download)
    monkeypatch.setattr(main, "Tracker", FakeTracker)
    monkeypatch.setattr(main, "Analyzer", FakeAnalyzer)
    monkeypatch.setattr(main, "ReportBuilder", FakeReportBuilder)
    monkeypatch.setattr(main.persistence, "save_session", fake_save_session)
    monkeypatch.setattr(main.persistence, "load_session", fake_load_session)
    monkeypatch.setattr(main.persistence, "list_sessions", fake_list_sessions)
    monkeypatch.setitem(
        sys.modules,
        "cv2",
        types.SimpleNamespace(CAP_PROP_FRAME_COUNT=7, VideoCapture=FakeVideoCapture),
    )

    with TestClient(main.app) as client:
        # 1) App is up
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers.get("content-type", "")

        # 2) Upload root test video
        with video_path.open("rb") as f:
            upload = client.post(
                "/upload",
                files={"file": (video_path.name, f, "video/mp4")},
            )
        assert upload.status_code == 200
        uploaded = upload.json()
        assert uploaded["local_path"].endswith(video_name)
        assert uploaded["duration_s"] == 12.5
        assert uploaded["width"] == 1280
        assert uploaded["height"] == 720

        # 3) Identify player and 4) start analysis
        start = client.post(
            "/sessions",
            json={
                "video_source": {"type": "file", "path": uploaded["local_path"]},
                "player_ref": {
                    "method": "jersey",
                    "jersey_number": 9,
                    "jersey_color": "black",
                },
                "position": "midfielder",
            },
        )
        assert start.status_code == 202
        session_id = start.json()["session_id"]

        # 5) Observe terminal completion and fetch result
        progress = client.get(f"/sessions/{session_id}/progress")
        assert progress.status_code == 200
        assert progress.headers["content-type"].startswith("text/event-stream")
        payloads = _parse_sse_payloads(progress.text)
        assert payloads, "Expected at least one SSE payload"
        assert payloads[-1]["status"] == "completed"
        assert payloads[-1]["progress"] == 100

        report_res = client.get(f"/sessions/{session_id}")
        assert report_res.status_code == 200
        report = report_res.json()
        assert report["player_ref"]["method"] == "jersey"
        assert report["player_ref"]["jersey_number"] == 9
        assert report["player_ref"]["jersey_color"] == "black"
        assert report["position"] == "midfielder"
        assert report["core"]["touch_count"] > 0
        assert report["core"]["passes_attempted"] > 0
        assert "debug_clips" in report

        sessions = client.get("/sessions")
        assert sessions.status_code == 200
        assert any(s["session_id"] == session_id for s in sessions.json())

        clips_res = client.get(f"/sessions/{session_id}/clips")
        assert clips_res.status_code == 200
        clips = clips_res.json()["clips"]
        assert "touches" in clips
        assert isinstance(clips["touches"], list)

        first_clip_path = next(
            (
                p
                for group in clips.values()
                for p in group
                if isinstance(p, str) and p.endswith(".mp4")
            ),
            None,
        )
        if first_clip_path:
            clip_name = Path(first_clip_path).name
            clip_download = client.get(f"/sessions/{session_id}/clips/{clip_name}")
            assert clip_download.status_code == 200
            assert clip_download.headers["content-type"].startswith("video/mp4")


def test_real_pipeline_root_video_completes(server_port: int, app_url: str) -> None:
    """Integration: real pipeline completes for root video and jersey params."""
    project_root = Path(__file__).resolve().parent.parent.parent
    video_name = "1771873660.688000iOS1508898871.mp4"
    video_path = project_root / video_name
    assert video_path.exists(), f"Required root test video is missing: {video_path}"

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "backend.main:app",
            "--host",
            "127.0.0.1",
            f"--port={server_port}",
        ],
        cwd=project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        _wait_for_server(app_url, timeout=60.0)
        with httpx.Client(timeout=90.0) as client:
            with video_path.open("rb") as f:
                upload = client.post(
                    f"{app_url}/upload",
                    files={"file": (video_path.name, f, "video/mp4")},
                )
            assert upload.status_code == 200, upload.text
            uploaded = upload.json()

            start = client.post(
                f"{app_url}/sessions",
                json={
                    "video_source": {"type": "file", "path": uploaded["local_path"]},
                    "player_ref": {
                        "method": "jersey",
                        "jersey_number": 9,
                        "jersey_color": "black",
                    },
                    "position": "midfielder",
                },
            )
            assert start.status_code == 202, start.text
            session_id = start.json()["session_id"]

            progress = client.get(
                f"{app_url}/sessions/{session_id}/progress",
                timeout=900.0,
            )
            assert progress.status_code == 200
            payloads = _parse_sse_payloads(progress.text)
            assert payloads, "Expected at least one progress event"
            terminal = payloads[-1]
            assert terminal["status"] == "completed", terminal
            assert terminal["progress"] == 100

            report_res = client.get(f"{app_url}/sessions/{session_id}", timeout=60.0)
            assert report_res.status_code == 200
            report = report_res.json()
            assert report["player_ref"]["method"] == "jersey"
            assert report["player_ref"]["jersey_number"] == 9
            assert report["player_ref"]["jersey_color"] == "black"
            assert report["position"] == "midfielder"
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
