# Soccer Player Tracker

A local web application (FastAPI backend + browser UI) that enables soccer coaches, analysts, and enthusiasts to analyze individual player performance from raw game footage. Upload a video or provide a URL, identify a player to track, and receive automatically generated statistics including touches, passes, ball losses, and position-based advanced metrics.

The system runs entirely on your machine. On Apple Silicon Macs, PyTorch with Metal/MPS acceleration is used for GPU-accelerated inference.

---

## Features

- **Video input**
  - Local file upload (MP4, MOV, AVI, MKV)
  - URL import (YouTube, Veo, and other platforms)
  - YouTube OAuth for unlisted and private videos

- **Player identification**
  - By jersey number
  - Optional jersey color (red, blue, white, etc.) to improve accuracy when multiple players share a number
  - Visual selection (draw a bounding box on the currently displayed video frame)

- **Statistics**
  - Core: touches, passes attempted/successful, pass completion %, ball losses, ball retention %
  - Position-specific advanced stats (Goalkeeper, Defender, Midfielder, Forward)

- **Export**
  - PDF and JSON reports
  - Session history with load/delete

- **Storage management**
  - Clear all uploaded videos to free disk space

---

## Prerequisites

- **Python 3.10+**
- **ffmpeg** (for merging video/audio when downloading from YouTube)
- **Tesseract OCR** (for jersey number detection)
- **~2GB disk space** for models and dependencies

### Optional: YouTube OAuth

To download unlisted or private YouTube videos, you need Google OAuth credentials:

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project (or use an existing one)
3. Enable the YouTube Data API v3
4. Create OAuth 2.0 credentials (Web application)
5. Add redirect URI: `http://127.0.0.1:8000/auth/youtube/callback`
6. Copy Client ID and Client Secret for configuration below

---

## Installation

1. Clone or download this repository.

2. Create and activate a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate   # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:

   ```bash
   pip install .
   ```

   For development tooling (pytest, ruff, mypy, pre-commit):

   ```bash
   pip install ".[dev]"
   ```

   Run this again after pulling updates when dependencies are changed in `pyproject.toml`.

4. (Optional) Install Tesseract if not already installed:

   - **macOS:** `brew install tesseract`
   - **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
   - **Windows:** Download from [GitHub](https://github.com/UB-Mannheim/tesseract/wiki)

5. (Optional) Install ffmpeg for YouTube downloads:

   - **macOS:** `brew install ffmpeg`
   - **Ubuntu/Debian:** `sudo apt install ffmpeg`
   - **Windows:** Download from [ffmpeg.org](https://ffmpeg.org/download.html)

### Updating

After pulling new changes (e.g. when `pyproject.toml` is updated):

```bash
source venv/bin/activate
pip install .
pip install ".[dev]"
```

### Code quality framework

This project uses a modern Python quality stack:

- `ruff` for linting and formatting
- `mypy` for static type checking
- `pre-commit` to run checks automatically before commits

Run checks manually:

```bash
ruff check .
ruff format .
mypy backend tests
```

Enable Git hooks:

```bash
pre-commit install
pre-commit run --all-files
```

---

## Configuration

### YouTube OAuth (optional)

Set environment variables before starting the app:

```bash
export GOOGLE_CLIENT_ID="your-client-id.apps.googleusercontent.com"
export GOOGLE_CLIENT_SECRET="your-client-secret"
```

Or add them to your shell profile (e.g. `~/.bashrc` or `~/.zshrc`).

---

## Start the Application

From the project root:

```bash
source venv/bin/activate   # If not already activated
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

You should see output like:

```
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8000
```

Open a browser and go to: **http://127.0.0.1:8000**

### API behavior (quick reference)

- `POST /sessions` starts analysis asynchronously and returns `202` with a `session_id`.
- `GET /sessions/{session_id}/progress` provides live progress updates via Server-Sent Events (SSE).
- `GET /sessions/{session_id}` returns the completed report JSON.

---

## Using the Application

### 1. Load video

- **Local file:** Click "Choose file" and select an MP4, MOV, AVI, or MKV file.
- **URL:** Enter a YouTube, Veo, or other video URL and click "Load URL".

Local file metadata (duration/resolution) is returned by the upload flow (`POST /upload`). URL metadata is retrieved through `GET /video/metadata`.

For unlisted or private YouTube videos, click "Connect YouTube" first and complete the Google sign-in.

### 2. Identify player

- **Jersey number:** Enter the number and optionally a jersey color (e.g. "red", "blue").
- **Visual selection:** Switch to the "Visual Selection" tab, play/pause the video to the desired moment, and draw a box around the player on the current frame.

### 3. Select position

Choose the player’s tactical position (Goalkeeper, Defender, Midfielder, Forward).

### 4. Start analysis

Click "Start Analysis". The server creates an async session and processes download + frame analysis in the background. Progress is shown during download and frame processing. You can cancel at any time.

### 5. View and export results

- View core and advanced statistics on the results screen.
- Use "Export PDF" or "Export JSON" to save the report.
- Past sessions appear in the sidebar; click "Load" to open them.

### 6. Storage management

- Use "Clear Uploads" in the sidebar to delete all cached uploads and free disk space.
- Debug clips for completed sessions can be viewed/downloaded from the session results screen.

---

## Stop the Application

In the terminal where the app is running, press **Ctrl+C**.

The server will shut down cleanly. Session data, exports, and configuration remain in `~/.soccer-tracker/`.

---

## Data Storage

All data is stored locally under `~/.soccer-tracker/`:

| Path                    | Contents                          |
|-------------------------|-----------------------------------|
| `uploads/`              | Uploaded video files              |
| `cache/`                | Downloaded remote videos (e.g. YouTube) |
| `sessions.db`           | SQLite database (session history) |
| `auth.json`             | YouTube OAuth token (if connected)|
| `exports/`              | Exported PDF and JSON reports     |
| `exports/debug/<session_id>/` | Per-session debug event clips (`.mp4`) |
| `app.log`               | Application log                   |

### Additional endpoints used by UI/debug workflows

- `GET /uploads` and `GET /uploads/stream/{file_name}` for uploaded file browsing/streaming.
- `GET /video/frame0`, `GET /video/frame`, and `GET /video/stream` for video preview and seeking.
- `GET /sessions/{session_id}/clips` and `GET /sessions/{session_id}/clips/{clip_name}` for debug clip manifests/downloads.

---

## Troubleshooting

- **"Player not found in video"** — The tracker could not locate the player. Try a different identification method (e.g. add jersey color, or use visual selection).
- **"authentication required"** — For unlisted/private YouTube videos, connect your YouTube account first.
- **Slow analysis** — Processing runs on CPU by default. On Apple Silicon or CUDA GPUs, acceleration is used automatically when available.
- **Tesseract errors** — Ensure Tesseract is installed and on your PATH (`tesseract --version`).

---

## License

See project documentation for license information.
