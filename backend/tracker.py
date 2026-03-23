"""Tracker: YOLO11 + ByteTrack-based player and ball tracking."""

from __future__ import annotations

import logging
from typing import Iterator, Optional

import cv2
import numpy as np
import pytesseract

from backend.device import device
from backend.errors import PlayerNotFoundError
from backend.models import Detection, FrameResult, PlayerRef

# COCO class IDs
_PERSON_CLASS = 0
_BALL_CLASS = 32  # sports ball in COCO

logger = logging.getLogger(__name__)


def _format_timestamp_ms(timestamp_ms: int) -> str:
    """Format milliseconds as mm:ss.mmm for logs."""
    total_seconds, ms = divmod(max(0, int(timestamp_ms)), 1000)
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}.{ms:03d}"


def _iou(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    """Compute Intersection over Union between two (x, y, w, h) boxes."""
    ax, ay, aw, ah = box_a
    bx, by, bw, bh = box_b

    ax2, ay2 = ax + aw, ay + ah
    bx2, by2 = bx + bw, by + bh

    ix = max(0, min(ax2, bx2) - max(ax, bx))
    iy = max(0, min(ay2, by2) - max(ay, by))
    intersection = ix * iy

    union = aw * ah + bw * bh - intersection
    return intersection / union if union > 0 else 0.0


# Mapping of common jersey color names to OpenCV HSV (H in [0,180], S,V in [0,255])
_COLOR_TO_HSV: dict[str, tuple[int, int, int]] = {
    "red": (0, 180, 200),       # Hue 0 (or 170 for red-orange), high sat/val
    "blue": (120, 200, 180),
    "white": (0, 0, 255),
    "black": (0, 0, 30),
    "green": (60, 180, 150),
    "yellow": (30, 200, 220),
    "orange": (15, 220, 220),
    "navy": (120, 220, 100),
    "maroon": (0, 200, 100),
    "pink": (170, 100, 220),
}


def _compute_hsv_histogram(crop: np.ndarray) -> np.ndarray:
    """Compute normalized HSV histogram for a BGR image crop. Returns H-channel histogram."""
    if crop.size == 0:
        return np.zeros((180,), dtype=np.float32)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
    cv2.normalize(hist, hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return hist.astype(np.float32)


def _color_similarity(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """Return similarity in [0, 1]. 1 = perfect match."""
    if hist_a.size == 0 or hist_b.size == 0:
        return 0.0
    # HISTCMP_CORREL returns [-1, 1]; map to [0, 1]
    correl = cv2.compareHist(hist_a, hist_b, cv2.HISTCMP_CORREL)
    return float(np.clip((correl + 1) / 2, 0.0, 1.0))


def _get_reference_histogram(color_name: str) -> np.ndarray:
    """Get reference HSV histogram for a named color."""
    hsv_val = _COLOR_TO_HSV.get(color_name.lower(), (0, 128, 200))
    h, s, v = hsv_val
    patch = np.zeros((50, 50, 3), dtype=np.uint8)
    patch[:, :] = (h, s, v)
    return _compute_hsv_histogram(cv2.cvtColor(patch, cv2.COLOR_HSV2BGR))


def _ocr_jersey_number(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> Optional[str]:
    """Crop a person bbox from the frame and OCR for a jersey number."""
    x, y, w, h = bbox
    x, y = max(0, x), max(0, y)
    crop = frame[y : y + h, x : x + w]
    if crop.size == 0:
        return None
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    # Upscale for better OCR accuracy
    scale = max(1, 64 // max(gray.shape[0], gray.shape[1], 1))
    if scale > 1:
        gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(
        gray, config="--psm 8 --oem 3 -c tessedit_char_whitelist=0123456789"
    )
    return text.strip() or None


class Tracker:
    """Wraps YOLOv8 + ByteTrack for player and ball tracking."""

    def __init__(self, video_path: str, player_ref: PlayerRef) -> None:
        self.video_path = video_path
        self.player_ref = player_ref

        self._model = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._target_track_id: Optional[int] = None
        self._fps: float = 30.0
        self._initialized = False
        self._last_player_box: Optional[tuple[int, int, int, int]] = None
        self._start_frame_idx: int = 0
        self._reacquire_count: int = 0
        self._unique_track_ids: set[int] = set()
        self._frames_total: int = 0
        self._frames_confident: int = 0
        self._last_reacquire_log_frame: int = -10_000

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def initialize(self) -> None:
        """Load YOLO11 model, open video, and locate the player across frames."""
        from ultralytics import YOLO  # lazy import to avoid slow startup elsewhere

        self._model = YOLO("yolo11m.pt")
        self._model.to(device)

        self._cap = cv2.VideoCapture(self.video_path)
        if not self._cap.isOpened():
            raise OSError(f"Cannot open video: {self.video_path}")

        fps = self._cap.get(cv2.CAP_PROP_FPS)
        self._fps = fps if fps and fps > 0 else 30.0

        # BBox mode can start from a user-selected timestamp instead of frame 0.
        if (
            self.player_ref.method == "bbox"
            and self.player_ref.bbox_timestamp_ms is not None
            and self.player_ref.bbox_timestamp_ms > 0
        ):
            self._start_frame_idx = int((self.player_ref.bbox_timestamp_ms / 1000.0) * self._fps)
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._start_frame_idx)
        else:
            self._start_frame_idx = 0

        found = self._find_target_across_frames(self._start_frame_idx)
        if found is None:
            raise PlayerNotFoundError(self.player_ref)
        found_frame_idx, found_track_id = found
        self._start_frame_idx = found_frame_idx
        self._target_track_id = found_track_id
        self._unique_track_ids.add(found_track_id)

        logger.info(
            "Tracking target found at frame=%s ts=%s track_id=%s method=%s",
            self._start_frame_idx,
            _format_timestamp_ms(int((self._start_frame_idx / self._fps) * 1000)),
            self._target_track_id,
            self.player_ref.method,
        )

        # Start tracking from selected frame (or frame 0 by default).
        self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._start_frame_idx)
        self._initialized = True

    def _find_target_across_frames(self, start_frame_idx: int) -> Optional[tuple[int, int]]:
        """Scan frames sequentially until the target can be identified."""
        frame_idx = start_frame_idx
        while True:
            ok, frame = self._cap.read()
            if not ok:
                return None
            results = self._model.track(
                frame, tracker="bytetrack.yaml", persist=True, verbose=False, imgsz=1280
            )
            track_id = self._find_player_in_frame(frame, results[0])
            if track_id is not None:
                return frame_idx, track_id
            frame_idx += 1

    def track_frames(self) -> Iterator[FrameResult]:
        """Yield a FrameResult for every frame in the video."""
        if not self._initialized:
            raise RuntimeError("Call initialize() before track_frames()")

        low_conf_streak = 0
        frame_idx = self._start_frame_idx

        while True:
            ok, frame = self._cap.read()
            if not ok:
                break

            timestamp_ms = int((frame_idx / self._fps) * 1000)

            results = self._model.track(
                frame, tracker="bytetrack.yaml", persist=True, verbose=False, imgsz=1280
            )
            result = results[0]

            player_box, player_conf, ball_box, all_detections = self._parse_result(
                frame,
                result,
                frame_idx,
                timestamp_ms,
            )

            confidence = player_conf if player_box is not None else 0.0
            confidence = float(np.clip(confidence, 0.0, 1.0))
            self._frames_total += 1
            if confidence >= 0.5:
                self._frames_confident += 1
            if player_box is not None and self._target_track_id is not None:
                self._unique_track_ids.add(self._target_track_id)

            # Tracking-lost streak logic
            if confidence < 0.5:
                low_conf_streak += 1
            else:
                if low_conf_streak >= 30:
                    logger.info(
                        "Tracking recovered: frame=%s ts=%s track_id=%s confidence=%.3f",
                        frame_idx,
                        _format_timestamp_ms(timestamp_ms),
                        self._target_track_id,
                        confidence,
                    )
                low_conf_streak = 0
                self._last_player_box = player_box

            yield FrameResult(
                frame_idx=frame_idx,
                timestamp_ms=timestamp_ms,
                player_box=player_box,
                ball_box=ball_box,
                confidence=confidence,
                all_detections=all_detections,
            )

            frame_idx += 1

        self._cap.release()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _find_player_in_frame(self, frame: np.ndarray, result) -> Optional[int]:
        """Return the track_id of the target player detected in frame 0."""
        if self.player_ref.method == "jersey":
            return self._find_by_jersey(frame, result)
        else:  # bbox
            return self._find_by_bbox(result)

    def _find_by_jersey(self, frame: np.ndarray, result) -> Optional[int]:
        """OCR each detected person bbox; return track_id of the matching jersey.
        When jersey_color is set, use HSV histogram similarity as tiebreaker.
        """
        target_number = str(self.player_ref.jersey_number)
        jersey_color = (self.player_ref.jersey_color or "").strip()
        boxes = result.boxes

        if boxes is None or boxes.id is None:
            return None

        candidates: list[tuple[int, np.ndarray]] = []  # (track_id, crop)

        for i, cls_tensor in enumerate(boxes.cls):
            if int(cls_tensor.item()) != _PERSON_CLASS:
                continue

            xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
            x1, y1, x2, y2 = xyxy
            bbox = (x1, y1, x2 - x1, y2 - y1)

            ocr_text = _ocr_jersey_number(frame, bbox)
            if ocr_text and target_number in ocr_text:
                track_id = int(boxes.id[i].item())
                x, y, w, h = bbox
                x, y = max(0, x), max(0, y)
                crop = frame[y : y + h, x : x + w]
                candidates.append((track_id, crop))

        if not candidates:
            # OCR can fail on blurry/small jerseys. If a jersey color hint is provided,
            # fall back to selecting the most color-similar detected player.
            if jersey_color:
                ref_hist = _get_reference_histogram(jersey_color)
                best_track_id: Optional[int] = None
                best_sim = -1.0

                for i, cls_tensor in enumerate(boxes.cls):
                    if int(cls_tensor.item()) != _PERSON_CLASS:
                        continue
                    if boxes.id is None:
                        continue
                    xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                    x1, y1, x2, y2 = xyxy
                    x, y = max(0, x1), max(0, y1)
                    w, h = x2 - x1, y2 - y1
                    crop = frame[y : y + h, x : x + w]
                    sim = _color_similarity(_compute_hsv_histogram(crop), ref_hist)
                    if sim > best_sim:
                        best_sim = sim
                        best_track_id = int(boxes.id[i].item())

                return best_track_id

            return None

        if len(candidates) == 1 and not jersey_color:
            return candidates[0][0]

        if jersey_color:
            ref_hist = _get_reference_histogram(jersey_color)
            best_track_id: Optional[int] = None
            best_sim = -1.0
            for track_id, crop in candidates:
                crop_hist = _compute_hsv_histogram(crop)
                sim = _color_similarity(crop_hist, ref_hist)
                if sim > best_sim:
                    best_sim = sim
                    best_track_id = track_id
            return best_track_id

        return candidates[0][0]

    def _find_by_bbox(self, result) -> Optional[int]:
        """Match user-drawn bbox (frame 0) to detected persons via IoU."""
        ref_bbox = self.player_ref.bbox  # (x, y, w, h)
        if ref_bbox is None:
            return None

        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return None

        best_iou = 0.0
        best_track_id: Optional[int] = None

        for i, cls_tensor in enumerate(boxes.cls):
            if int(cls_tensor.item()) != _PERSON_CLASS:
                continue

            xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
            x1, y1, x2, y2 = xyxy
            det_bbox = (x1, y1, x2 - x1, y2 - y1)

            iou = _iou(ref_bbox, det_bbox)
            if iou > best_iou:
                best_iou = iou
                best_track_id = int(boxes.id[i].item())

        return best_track_id if best_iou > 0.0 else None

    def _parse_result(
        self,
        frame: np.ndarray,
        result,
        frame_idx: int,
        timestamp_ms: int,
    ) -> tuple[
        Optional[tuple[int, int, int, int]],
        float,
        Optional[tuple[int, int, int, int]],
        list[Detection],
    ]:
        """Extract player box, player confidence, ball box, and all detections."""
        player_box: Optional[tuple[int, int, int, int]] = None
        player_conf: float = 0.0
        ball_box: Optional[tuple[int, int, int, int]] = None
        all_detections: list[Detection] = []

        boxes = result.boxes
        if boxes is None:
            return player_box, player_conf, ball_box, all_detections

        has_ids = boxes.id is not None
        person_candidates: list[tuple[int, tuple[int, int, int, int], float]] = []

        for i, cls_tensor in enumerate(boxes.cls):
            cls = int(cls_tensor.item())
            conf = float(boxes.conf[i].item())
            xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
            x1, y1, x2, y2 = xyxy
            bbox = (x1, y1, x2 - x1, y2 - y1)

            track_id = int(boxes.id[i].item()) if has_ids else -1
            label = "person" if cls == _PERSON_CLASS else "ball" if cls == _BALL_CLASS else str(cls)

            all_detections.append(
                Detection(track_id=track_id, bbox=bbox, label=label, confidence=conf)
            )

            if cls == _PERSON_CLASS and track_id == self._target_track_id:
                player_box = bbox
                player_conf = conf
            if cls == _PERSON_CLASS and track_id >= 0:
                person_candidates.append((track_id, bbox, conf))

            if cls == _BALL_CLASS and ball_box is None:
                ball_box = bbox

        if player_box is None and person_candidates:
            reacquired = self._reacquire_player(frame, person_candidates)
            if reacquired is not None:
                reacq_track_id, reacq_box, reacq_conf = reacquired
                if reacq_track_id != self._target_track_id:
                    self._reacquire_count += 1
                    self._unique_track_ids.add(reacq_track_id)
                    if frame_idx - self._last_reacquire_log_frame >= 90:
                        logger.info(
                            "Tracking reacquired: frame=%s ts=%s track_id %s -> %s confidence=%.3f",
                            frame_idx,
                            _format_timestamp_ms(timestamp_ms),
                            self._target_track_id,
                            reacq_track_id,
                            reacq_conf,
                        )
                        self._last_reacquire_log_frame = frame_idx
                self._target_track_id = reacq_track_id
                player_box = reacq_box
                player_conf = reacq_conf

        return player_box, player_conf, ball_box, all_detections

    def _reacquire_player(
        self,
        frame: np.ndarray,
        candidates: list[tuple[int, tuple[int, int, int, int], float]],
    ) -> Optional[tuple[int, tuple[int, int, int, int], float]]:
        """Pick the best fallback candidate when current target id disappears."""
        if not candidates:
            return None

        # 1) Prefer spatial continuity with last known player box.
        if self._last_player_box is not None:
            best = max(candidates, key=lambda c: _iou(self._last_player_box, c[1]))
            if _iou(self._last_player_box, best[1]) > 0:
                return best

        # 2) For bbox mode, anchor to user-drawn box.
        if self.player_ref.method == "bbox" and self.player_ref.bbox is not None:
            best = max(candidates, key=lambda c: _iou(self.player_ref.bbox, c[1]))
            if _iou(self.player_ref.bbox, best[1]) > 0:
                return best

        # 3) For jersey mode with color hint, prefer nearest color match.
        jersey_color = (self.player_ref.jersey_color or "").strip()
        if self.player_ref.method == "jersey" and jersey_color:
            ref_hist = _get_reference_histogram(jersey_color)

            def _sim(candidate: tuple[int, tuple[int, int, int, int], float]) -> float:
                _track_id, bbox, _conf = candidate
                x, y, w, h = bbox
                x, y = max(0, x), max(0, y)
                crop = frame[y : y + h, x : x + w]
                return _color_similarity(_compute_hsv_histogram(crop), ref_hist)

            return max(candidates, key=_sim)

        # 4) Final fallback: highest-confidence detected person.
        return max(candidates, key=lambda c: c[2])

    def get_tracking_summary(self) -> dict[str, object]:
        """Return per-session tracking quality diagnostics."""
        confident_pct = (
            round((self._frames_confident / self._frames_total) * 100, 2)
            if self._frames_total > 0
            else 0.0
        )
        return {
            "total_reacquires": self._reacquire_count,
            "unique_track_ids_used": sorted(self._unique_track_ids),
            "frames_total": self._frames_total,
            "frames_confident": self._frames_confident,
            "confident_frame_pct": confident_pct,
        }
