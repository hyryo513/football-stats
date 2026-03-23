"""Downloader component for the Soccer Player Tracker.

Resolves a video source (local file path or URL) to a local file path,
validates format and metadata, and returns a DownloadResult.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import cv2

from backend.errors import (
    CorruptedFileError,
    MalformedURLError,
    UnavailableSourceError,
    UnsupportedFormatError,
)
from backend.models import DownloadResult

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ACCEPTED_FORMATS: list[str] = ["mp4", "mov", "avi", "mkv"]
CACHE_DIR = Path.home() / ".soccer-tracker" / "cache"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_extension(path: str) -> None:
    """Raise UnsupportedFormatError if the file extension is not supported."""
    ext = Path(path).suffix.lstrip(".").lower()
    if ext not in ACCEPTED_FORMATS:
        raise UnsupportedFormatError(accepted_formats=ACCEPTED_FORMATS)


def _read_metadata(local_path: str) -> tuple[float, int, int]:
    """Open a local video with OpenCV and return (duration_s, width, height).

    Raises CorruptedFileError if the file cannot be read.
    """
    cap = cv2.VideoCapture(local_path)
    try:
        if not cap.isOpened():
            raise CorruptedFileError(file_path=local_path)

        fps = cap.get(cv2.CAP_PROP_FPS)
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        if fps <= 0 or frame_count <= 0 or width <= 0 or height <= 0:
            raise CorruptedFileError(file_path=local_path)

        duration_s = frame_count / fps
        return duration_s, width, height
    finally:
        cap.release()


def _is_url(source: str) -> bool:
    """Return True if source looks like an HTTP/HTTPS URL."""
    try:
        result = urlparse(source)
        return result.scheme in ("http", "https") and bool(result.netloc)
    except Exception:
        return False


def _validate_url(source: str) -> None:
    """Raise MalformedURLError if source is not a valid HTTP/HTTPS URL."""
    try:
        result = urlparse(source)
        if result.scheme not in ("http", "https") or not result.netloc:
            raise MalformedURLError(url=source)
    except MalformedURLError:
        raise
    except Exception:
        raise MalformedURLError(url=source)


def _make_progress_hook(
    progress_callback: Optional[Callable[[int], None]],
) -> Callable[[dict], None]:
    """Return a yt-dlp progress hook that forwards percentage to progress_callback."""

    def hook(d: dict) -> None:
        if progress_callback is None:
            return
        status = d.get("status")
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes", 0)
            if total and total > 0:
                pct = int(downloaded / total * 100)
                progress_callback(min(pct, 99))
        elif status == "finished":
            progress_callback(100)

    return hook


def _is_youtube_url(source: str) -> bool:
    """Return True if source appears to be a YouTube URL."""
    return "youtube.com" in source or "youtu.be" in source


def _download_url(
    source: str,
    progress_callback: Optional[Callable[[int], None]],
) -> str:
    """Download a remote URL with yt-dlp and return the local file path.

    Raises:
        UnavailableSourceError: if the video is unavailable, private, or
            requires authentication.
    """
    import yt_dlp  # imported lazily so the module loads without yt-dlp installed

    from backend.youtube_auth import YouTubeAuthManager

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    ydl_opts: dict = {
        "outtmpl": str(CACHE_DIR / "%(id)s.%(ext)s"),
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_make_progress_hook(progress_callback)],
        "merge_output_format": "mp4",
    }

    # For YouTube, add OAuth credentials if user has connected their account
    if _is_youtube_url(source):
        auth = YouTubeAuthManager()
        refresh_token = auth.get_refresh_token()
        if refresh_token:
            ydl_opts["username"] = "oauth"
            ydl_opts["password"] = refresh_token

    def _run_download(opts: dict) -> str:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(source, download=True)
            filename = ydl.prepare_filename(info)
            if not os.path.exists(filename):
                for ext in ("mp4", "mkv", "webm"):
                    candidate = str(Path(filename).with_suffix(f".{ext}"))
                    if os.path.exists(candidate):
                        filename = candidate
                        break
            return filename

    try:
        return _run_download(ydl_opts)
    except yt_dlp.utils.DownloadError as exc:
        msg = str(exc).lower()
        # Fallback when ffmpeg is unavailable: use single progressive stream.
        if "ffmpeg is not installed" in msg or "requested merging of multiple formats" in msg:
            fallback_opts = dict(ydl_opts)
            fallback_opts["format"] = "best[ext=mp4]/best"
            fallback_opts.pop("merge_output_format", None)
            try:
                return _run_download(fallback_opts)
            except yt_dlp.utils.DownloadError as fallback_exc:
                msg = str(fallback_exc).lower()
                exc = fallback_exc

        auth_required = "login" in msg or "private" in msg or "sign in" in msg or "members only" in msg
        if auth_required and _is_youtube_url(source):
            auth = YouTubeAuthManager()
            if not auth.is_connected():
                raise UnavailableSourceError(
                    url=source,
                    reason="authentication required",
                ) from exc
        if auth_required:
            raise UnavailableSourceError(
                url=source,
                reason="Private or login-required videos require YouTube connection",
            ) from exc
        raise UnavailableSourceError(
            url=source,
            reason=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def download(
    source: str,
    progress_callback: Optional[Callable[[int], None]] = None,
) -> DownloadResult:
    """Resolve *source* to a local video file and return its metadata.

    Parameters
    ----------
    source:
        A local file path or an HTTP/HTTPS URL.
    progress_callback:
        Optional callable that receives an integer percentage (0–100) during
        remote downloads.  Used to stream SSE progress events to the frontend.

    Returns
    -------
    DownloadResult
        ``local_path``, ``duration_s``, ``width``, ``height``.

    Raises
    ------
    UnsupportedFormatError
        The file extension is not in {mp4, mov, avi, mkv}.
    CorruptedFileError
        The local file cannot be opened or has invalid metadata.
    MalformedURLError
        The source string is not a valid HTTP/HTTPS URL (URL path only).
    UnavailableSourceError
        The remote video is unavailable, private, or requires authentication.
    """
    # Determine whether source is a URL or a local path
    if _is_url(source):
        # Full URL validation (raises MalformedURLError for bad URLs)
        _validate_url(source)
        # Validate extension from URL path if present
        url_path = urlparse(source).path
        if url_path and "." in Path(url_path).suffix:
            _validate_extension(url_path)
        # Download
        local_path = _download_url(source, progress_callback)
    else:
        # Local file — validate extension first, then read metadata
        _validate_extension(source)
        local_path = source

    # Read metadata via OpenCV
    duration_s, width, height = _read_metadata(local_path)

    return DownloadResult(
        local_path=local_path,
        duration_s=duration_s,
        width=width,
        height=height,
    )
