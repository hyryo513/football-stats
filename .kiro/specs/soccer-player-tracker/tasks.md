# Implementation Plan: Soccer Player Tracker

## Overview

Implement the soccer player tracker as a FastAPI backend with OpenCV/YOLOv8/ByteTrack CV pipeline, SQLite persistence, and an HTML/JS frontend. Tasks follow the processing pipeline: project setup → data models → downloader → tracker → analyzer → report builder → persistence → API → frontend → export.

## Tasks

- [x] 1. Set up project structure, dependencies, and core data models
  - Create directory layout: `backend/`, `frontend/`, `tests/unit/`, `tests/property/`, `tests/conftest.py`
  - Create `pyproject.toml` (or `requirements.txt`) with: fastapi, uvicorn, opencv-python, ultralytics, torch, yt-dlp, sqlalchemy, reportlab, hypothesis
  - Implement all Pydantic data models in `backend/models.py`: `VideoSource`, `PlayerRef`, `Position`, `TouchEvent`, `PassEvent`, `BallLossEvent`, `CoreStats`, `GoalkeeperStats`, `DefenderStats`, `MidfielderStats`, `ForwardStats`, `StatsReport`, `SessionSummary`, `DownloadResult`, `FrameResult`
  - Implement all custom exception classes in `backend/errors.py`: `UnsupportedFormatError`, `CorruptedFileError`, `MalformedURLError`, `UnavailableSourceError`, `PlayerNotFoundError`, `TrackingLostWarning`, `ExportError`, `PersistenceError`
  - Add device-selection logic in `backend/device.py` (MPS → CUDA → CPU)
  - _Requirements: 1.1, 1.3, 2.4, 3.7_

- [x] 2. Implement the Downloader component
  - [x] 2.1 Implement `backend/downloader.py` with `download(source: str) -> DownloadResult`
    - Validate file extension (case-insensitive) against {mp4, mov, avi, mkv}; raise `UnsupportedFormatError` listing accepted formats on mismatch
    - Read video metadata (duration, width, height) via OpenCV for local files; raise `CorruptedFileError` if unreadable
    - Validate URL format (must be HTTP/HTTPS) before any network call; raise `MalformedURLError` for malformed URLs
    - Use `yt-dlp` to download remote URLs to a temp directory; raise `UnavailableSourceError` for unavailable/auth-required sources
    - Yield download progress events for SSE streaming
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [ ]* 2.2 Write property test for file format validation (Property 1)
    - **Property 1: File Format Validation Completeness**
    - **Validates: Requirements 1.1, 1.3**
    - File: `tests/property/test_format_validation.py`

  - [ ]* 2.3 Write property test for video metadata presence (Property 2)
    - **Property 2: Video Metadata Presence**
    - **Validates: Requirements 1.5, 2.6**
    - File: `tests/property/test_format_validation.py`

  - [ ]* 2.4 Write property test for malformed URL rejection (Property 3)
    - **Property 3: Malformed URL Rejection**
    - **Validates: Requirements 2.3**
    - File: `tests/property/test_format_validation.py`

  - [ ]* 2.5 Write unit tests for Downloader
    - Test valid/invalid extensions, corrupted file mock, malformed URL, unavailable remote source mock
    - File: `tests/unit/test_downloader.py`
    - _Requirements: 1.1–1.4, 2.1–2.6_

- [x] 3. Implement the Tracker component
  - [x] 3.1 Implement `backend/tracker.py` with `initialize()` and `track_frames()` iterator
    - Load YOLOv8 model on the selected device (MPS/CUDA/CPU)
    - Support `JerseyRef`: run OCR on detected jersey regions to locate the target player
    - Support `BBoxRef`: lock onto user-drawn bounding box from the selected video frame/time
    - Integrate ByteTrack for multi-object tracking across frames
    - Yield `FrameResult` per frame with `player_box`, `ball_box`, `confidence`, `all_detections`
    - Set `confidence = 0` when player is not detected in a frame
    - Emit `TrackingLostWarning` when confidence < 0.5 for 30+ consecutive frames
    - _Requirements: 3.1–3.8_

  - [ ]* 3.2 Write property test for frame confidence bounds (Property 4)
    - **Property 4: Frame Confidence Bounds**
    - **Validates: Requirements 3.7**
    - File: `tests/property/test_tracker_properties.py`

  - [ ]* 3.3 Write property test for tracking-lost alert threshold (Property 5)
    - **Property 5: Tracking-Lost Alert Threshold**
    - **Validates: Requirements 3.8**
    - File: `tests/property/test_tracker_properties.py`

  - [ ]* 3.4 Write unit tests for Tracker
    - Test bbox initialization, jersey OCR on a known test frame, confidence=0 on missing player
    - File: `tests/unit/test_tracker.py`
    - _Requirements: 3.1–3.8_

- [x] 4. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Implement the Analyzer component
  - [x] 5.1 Implement `backend/analyzer.py` with `process_frame()` and `finalize()` methods
    - Touch detector: ball-to-player proximity threshold (default 50px at 1080p) with 500ms debounce window
    - Pass detector: track ball trajectory after touch; classify successful pass (ball reaches teammate bbox) vs attempted pass
    - Ball loss detector: detect possession transfer to opponent bbox following a touch
    - Accumulate `TouchEvent`, `PassEvent`, `BallLossEvent` lists with timestamps
    - `finalize(position)`: compute `CoreStats` including `pass_completion_pct` (None when attempts=0) and `ball_retention_rate` (None when touches=0)
    - Compute position-specific advanced stats for the given `Position` enum value
    - _Requirements: 4.1–4.4, 5.1–5.5, 6.1–6.5, 7.1–7.7_

  - [ ]* 5.2 Write property test for touch debounce invariant (Property 6)
    - **Property 6: Touch Debounce Invariant**
    - **Validates: Requirements 4.1, 4.2**
    - File: `tests/property/test_analyzer_properties.py`

  - [ ]* 5.3 Write property test for touch event timestamps (Property 7)
    - **Property 7: Touch Event Timestamps**
    - **Validates: Requirements 4.4**
    - File: `tests/property/test_analyzer_properties.py`

  - [ ]* 5.4 Write property test for pass completion formula (Property 8)
    - **Property 8: Pass Completion Formula**
    - **Validates: Requirements 5.4, 5.5**
    - File: `tests/property/test_analyzer_properties.py`

  - [ ]* 5.5 Write property test for ball retention rate formula (Property 9)
    - **Property 9: Ball Retention Rate Formula**
    - **Validates: Requirements 6.4, 6.5**
    - File: `tests/property/test_analyzer_properties.py`

  - [ ]* 5.6 Write property test for ball loss event timestamps (Property 10)
    - **Property 10: Ball Loss Event Timestamps**
    - **Validates: Requirements 6.3**
    - File: `tests/property/test_analyzer_properties.py`

  - [ ]* 5.7 Write unit tests for Analyzer
    - Test specific touch sequences, pass sequences with known outcomes, ball loss detection
    - File: `tests/unit/test_analyzer.py`
    - _Requirements: 4.1–4.4, 5.1–5.5, 6.1–6.5_

- [x] 6. Implement the Stats Report Builder
  - [x] 6.1 Implement `backend/report_builder.py` with `build()`, `export_pdf()`, and `export_json()` methods
    - `build()`: assemble `StatsReport` from analyzer state and session metadata (video source, player ref, timestamp)
    - `export_json()`: serialize `StatsReport` to JSON file; raise `ExportError` on failure
    - `export_pdf()`: generate PDF using `reportlab` with all core and advanced stats; raise `ExportError` on failure
    - Ensure exported output contains video source reference, player identifier, and analysis timestamp
    - _Requirements: 8.1–8.5_

  - [ ]* 6.2 Write property test for position-specific advanced stats completeness (Property 11)
    - **Property 11: Position-Specific Advanced Stats Completeness**
    - **Validates: Requirements 7.3, 7.4, 7.5, 7.6, 7.7**
    - File: `tests/property/test_report_properties.py`

  - [ ]* 6.3 Write property test for JSON export round-trip (Property 12)
    - **Property 12: JSON Export Round-Trip**
    - **Validates: Requirements 8.3**
    - File: `tests/property/test_report_properties.py`

  - [ ]* 6.4 Write property test for export contains required metadata (Property 13)
    - **Property 13: Export Contains Required Metadata**
    - **Validates: Requirements 8.4**
    - File: `tests/property/test_report_properties.py`

  - [ ]* 6.5 Write property test for analysis duration recorded (Property 14)
    - **Property 14: Analysis Duration Recorded**
    - **Validates: Requirements 9.5**
    - File: `tests/property/test_report_properties.py`

  - [ ]* 6.6 Write unit tests for Report Builder
    - Test known input → expected output for each position; JSON produces valid JSON; PDF produces non-empty file
    - File: `tests/unit/test_report_builder.py`
    - _Requirements: 8.1–8.5_

- [x] 7. Implement the Persistence Layer
  - [x] 7.1 Implement `backend/persistence.py` with SQLAlchemy models and CRUD operations
    - Define SQLAlchemy ORM models for sessions (storing `StatsReport` as JSON blob + summary columns)
    - Implement `save_session()`, `list_sessions()`, `load_session()`, `delete_session()`
    - Raise `PersistenceError` when storage is unavailable or full
    - Database file stored at `~/.soccer-tracker/sessions.db`
    - _Requirements: 10.1–10.5_

  - [ ]* 7.2 Write property test for session persistence round-trip (Property 15)
    - **Property 15: Session Persistence Round-Trip**
    - **Validates: Requirements 10.1, 10.3**
    - File: `tests/property/test_persistence_properties.py`

  - [ ]* 7.3 Write property test for session deletion removes from list (Property 16)
    - **Property 16: Session Deletion Removes from List**
    - **Validates: Requirements 10.4**
    - File: `tests/property/test_persistence_properties.py`

  - [ ]* 7.4 Write unit tests for Persistence
    - Test save/load/delete with an in-memory SQLite test database
    - File: `tests/unit/test_persistence.py`
    - _Requirements: 10.1–10.5_

- [x] 8. Checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement the FastAPI backend and session orchestration
  - [x] 9.1 Implement `backend/main.py` with all REST endpoints and SSE progress streaming
    - `POST /sessions`: accept `VideoSource`, `PlayerRef`, `Position`; run full pipeline (download → track → analyze → build report → save); stream progress via SSE at `GET /sessions/{id}/progress`
    - `GET /sessions`: return `list[SessionSummary]` from persistence
    - `GET /sessions/{id}`: return `StatsReport` from persistence
    - `DELETE /sessions/{id}`: delete session; return 404 if not found
    - `POST /sessions/{id}/cancel`: set session status to cancelled; discard partial results within 3 seconds
    - `POST /sessions/{id}/export`: accept `format` param (pdf/json); call report builder; return file or 500 with error
    - `GET /video/metadata`: call downloader for metadata only; return `DownloadResult`
    - Map exceptions to HTTP status codes per error handling table in design
    - Serve `frontend/` as static files
    - _Requirements: 1.2–1.5, 2.3–2.8, 8.2–8.5, 9.1–9.5, 10.5_

  - [ ]* 9.2 Write unit tests for API endpoints
    - Test each endpoint with FastAPI `TestClient`; mock downloader/tracker/analyzer/persistence
    - File: `tests/unit/test_api.py`
    - _Requirements: 1.2–1.5, 2.3–2.8, 8.2–8.5, 9.1–9.5_

- [x] 10. Implement the HTML/JS frontend
  - [x] 10.1 Create `frontend/index.html` with the main single-page UI
    - Home screen: list of past sessions with load/delete actions
    - Video input section: file upload input (mp4/mov/avi/mkv) and URL text field
    - Player identification section: jersey number input and canvas for bbox selection on the currently selected video frame
    - Position selector: dropdown for Goalkeeper / Defender / Midfielder / Forward
    - Progress indicator: percentage bar during download and analysis; cancel button
    - Stats report view: display all `CoreStats` and position-specific `AdvancedStats` fields
    - Export buttons: "Export PDF" and "Export JSON"
    - _Requirements: 1.1, 2.7, 3.1–3.3, 7.1, 8.1–8.3, 9.1–9.3, 10.2–10.4_

  - [x] 10.2 Create `frontend/app.js` with all API interactions
    - Call `POST /upload` for local files and `GET /video/metadata` for URLs to display duration and resolution
    - Call `POST /sessions` to start analysis; connect to SSE endpoint for progress updates
    - Poll/stream `GET /sessions/{id}/progress` and update progress bar; wire cancel button to `POST /sessions/{id}/cancel`
    - Call `GET /sessions` on load to populate session history list
    - Call `GET /sessions/{id}` to load and render a past session
    - Call `DELETE /sessions/{id}` for session deletion with confirmation
    - Call `POST /sessions/{id}/export` for PDF/JSON export and trigger file download
    - Display error messages from API responses in the UI
    - _Requirements: 1.3–1.5, 2.4–2.8, 3.6, 3.8, 8.2–8.5, 9.1–9.5, 10.2–10.5_

- [x] 11. Final checkpoint — Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 12. Jersey color identification
  - [x] 12.1 Update `backend/models.py`: add `jersey_color: Optional[str]` field to `PlayerRef`
  - [x] 12.2 Update `backend/tracker.py`: implement `_compute_hsv_histogram(crop)` helper and `_color_similarity(hist_a, hist_b) -> float` using OpenCV `calcHist` + `compareHist`; use color similarity as a tiebreaker in `_find_by_jersey` when `player_ref.jersey_color` is set
  - [x] 12.3 Update `frontend/index.html`: add a "Jersey Color" optional input (text field or color picker) in the Jersey Number tab of the player identification card
  - [x] 12.4 Update `frontend/app.js`: include `jersey_color` in the `playerRef` payload when the field is filled in
  - _Requirements: 3.4, 3.6_

- [x] 13. Upload storage cleanup
  - [x] 13.1 Update `backend/main.py`: add `DELETE /uploads` endpoint that deletes all files in `~/.soccer-tracker/uploads/`, returns `{"deleted": <count>}`; return 200 with `{"deleted": 0}` if directory is empty
  - [x] 13.2 Update `frontend/index.html`: add a "Clear Uploads" button in the sidebar footer area
  - [x] 13.3 Update `frontend/app.js`: wire "Clear Uploads" button to call `DELETE /uploads` with a confirmation dialog; display success/error feedback
  - _Requirements: 11.1–11.6_

- [x] 14. YouTube Google OAuth integration
  - [x] 14.1 Create `backend/youtube_auth.py`: implement `YouTubeAuthManager` with `get_auth_url()`, `exchange_code(code)`, `get_credentials()`, `revoke()`, `is_connected()` using `google-auth-oauthlib` and `google-auth`; store token at `~/.soccer-tracker/auth.json`
  - [x] 14.2 Update `backend/errors.py`: add `AuthenticationError(Exception)` with a `reason: str` attribute
  - [x] 14.3 Update `backend/main.py`: add `GET /auth/youtube` (redirect to OAuth consent URL), `GET /auth/youtube/callback` (exchange code, store token, redirect to frontend), `DELETE /auth/youtube` (revoke token), `GET /auth/youtube/status` (return `{"connected": bool}`) endpoints; map `AuthenticationError` to HTTP 401
  - [x] 14.4 Update `backend/downloader.py`: check `YouTubeAuthManager.is_connected()` before downloading YouTube URLs; if connected, pass credentials/cookies to `yt-dlp`; if not connected and URL appears to require auth, raise `UnavailableSourceError` with reason "authentication required"
  - [x] 14.5 Update `frontend/index.html`: add a "Connect YouTube" / "Disconnect" button in the sidebar or URL card; show connected status indicator
  - [x] 14.6 Update `frontend/app.js`: on load call `GET /auth/youtube/status` and update the connect button state; wire connect button to navigate to `GET /auth/youtube`; wire disconnect button to call `DELETE /auth/youtube`
  - [x] 14.7 Update `requirements.txt`: add `google-auth-oauthlib` and `google-api-python-client`
  - _Requirements: 2.9–2.13_

## Notes

- Tasks marked with `*` are optional and can be skipped for a faster MVP
- Each task references specific requirements for traceability
- Property tests use Hypothesis with `max_examples=100` per the design testing strategy
- The `conftest.py` should set up shared fixtures: in-memory SQLite DB, sample `StatsReport` factory, Hypothesis settings profile
- Tasks 12–14 have been implemented: jersey color identification, upload cleanup, and YouTube OAuth
