"""Custom exception classes for the Soccer Player Tracker."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.models import PlayerRef


class UnsupportedFormatError(Exception):
    """Raised when a file has an unsupported video format."""

    def __init__(self, accepted_formats: list[str], message: str = "") -> None:
        self.accepted_formats = accepted_formats
        super().__init__(
            message or f"Unsupported format. Accepted formats: {', '.join(accepted_formats)}"
        )


class CorruptedFileError(Exception):
    """Raised when a file cannot be read or is corrupted."""

    def __init__(self, file_path: str, message: str = "") -> None:
        self.file_path = file_path
        super().__init__(message or f"File is corrupted or unreadable: {file_path}")


class MalformedURLError(Exception):
    """Raised when a URL is malformed or points to an unsupported platform."""

    def __init__(self, url: str, message: str = "") -> None:
        self.url = url
        super().__init__(message or f"Malformed or unsupported URL: {url}")


class UnavailableSourceError(Exception):
    """Raised when a remote video is unavailable or access is restricted."""

    def __init__(self, url: str, reason: str) -> None:
        self.url = url
        self.reason = reason
        super().__init__(f"Source unavailable: {url}. Reason: {reason}")


class PlayerNotFoundError(Exception):
    """Raised when the tracker cannot locate the identified player in the video."""

    def __init__(self, player_ref: "PlayerRef", message: str = "") -> None:
        self.player_ref = player_ref
        super().__init__(message or f"Player not found in video: {player_ref}")


class TrackingLostWarning(Warning):
    """Emitted when tracker confidence drops below 0.5 for 30+ consecutive frames."""

    def __init__(self, frame_idx: int, consecutive_low_confidence_frames: int) -> None:
        self.frame_idx = frame_idx
        self.consecutive_low_confidence_frames = consecutive_low_confidence_frames
        super().__init__(
            f"Tracking may have been lost at frame {frame_idx} "
            f"({consecutive_low_confidence_frames} consecutive low-confidence frames)"
        )


class ExportError(Exception):
    """Raised when a report export operation fails."""

    def __init__(self, export_format: str, reason: str) -> None:
        self.export_format = export_format
        self.reason = reason
        super().__init__(f"Export failed for format '{export_format}': {reason}")


class PersistenceError(Exception):
    """Raised when local storage is unavailable or an operation fails."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Persistence error: {reason}")


class AuthenticationError(Exception):
    """Raised when OAuth flow fails or token cannot be refreshed."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Authentication error: {reason}")
