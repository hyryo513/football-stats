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


def _center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    """Return the centre (cx, cy) of an (x, y, w, h) box."""
    x, y, w, h = box
    return x + w / 2.0, y + h / 2.0


def _center_distance(box_a: tuple[int, int, int, int], box_b: tuple[int, int, int, int]) -> float:
    """Euclidean distance between centres of two (x, y, w, h) boxes."""
    cx_a, cy_a = _center(box_a)
    cx_b, cy_b = _center(box_b)
    return ((cx_a - cx_b) ** 2 + (cy_a - cy_b) ** 2) ** 0.5


def _compute_appearance_histogram(frame: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
    """Compute a multi-channel HSV histogram for the torso region of a player crop.

    Focusing on the torso (middle 60% vertically, central 80% horizontally)
    reduces noise from background, legs, and head, giving a more stable jersey
    colour signature.  Returns a concatenated [H, S] histogram (180+256 bins).
    """
    x, y, w, h = bbox
    x, y = max(0, x), max(0, y)
    crop = frame[y : y + h, x : x + w]
    if crop.size == 0:
        return np.zeros((180 + 256,), dtype=np.float32)

    # Extract torso region
    ch, cw = crop.shape[:2]
    ty = int(ch * 0.2)
    by = int(ch * 0.8)
    tx = int(cw * 0.1)
    bx = int(cw * 0.9)
    torso = crop[ty:by, tx:bx]
    if torso.size == 0:
        torso = crop

    hsv = cv2.cvtColor(torso, cv2.COLOR_BGR2HSV)
    h_hist = cv2.calcHist([hsv], [0], None, [180], [0, 180])
    s_hist = cv2.calcHist([hsv], [1], None, [256], [0, 256])
    cv2.normalize(h_hist, h_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    cv2.normalize(s_hist, s_hist, alpha=0, beta=1, norm_type=cv2.NORM_MINMAX)
    return np.concatenate([h_hist.flatten(), s_hist.flatten()]).astype(np.float32)


def _appearance_similarity(hist_a: np.ndarray, hist_b: np.ndarray) -> float:
    """Compare two appearance histograms. Returns similarity in [0, 1]."""
    if hist_a.size == 0 or hist_b.size == 0:
        return 0.0
    # Split into H and S portions and average their correlations
    h_a, s_a = hist_a[:180], hist_a[180:]
    h_b, s_b = hist_b[:180], hist_b[180:]

    h_corr = cv2.compareHist(
        h_a.reshape(-1, 1).astype(np.float32),
        h_b.reshape(-1, 1).astype(np.float32),
        cv2.HISTCMP_CORREL,
    )
    s_corr = cv2.compareHist(
        s_a.reshape(-1, 1).astype(np.float32),
        s_b.reshape(-1, 1).astype(np.float32),
        cv2.HISTCMP_CORREL,
    )
    # Weight hue more heavily than saturation
    correl = 0.7 * h_corr + 0.3 * s_corr
    return float(np.clip((correl + 1) / 2, 0.0, 1.0))


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
        # Appearance model: captured when the target player is first identified
        self._target_appearance: Optional[np.ndarray] = None

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
        """Scan frames sequentially until the target can be identified.

        For bbox mode, uses multi-frame confirmation: once a candidate is found,
        checks subsequent frames to verify the same track_id persists, reducing
        false matches from transient overlaps.
        """
        frame_idx = start_frame_idx
        confirmation_needed = 3 if self.player_ref.method == "bbox" else 1
        candidate_track_id: Optional[int] = None
        candidate_frame_idx: Optional[int] = None
        candidate_frame: Optional[np.ndarray] = None
        confirm_count = 0

        while True:
            ok, frame = self._cap.read()
            if not ok:
                # If we had a partial confirmation, accept it
                if candidate_track_id is not None and confirm_count > 0:
                    self._capture_appearance(candidate_frame, candidate_track_id, None)
                    return candidate_frame_idx, candidate_track_id
                return None

            results = self._model.track(
                frame, tracker="bytetrack.yaml", persist=True, verbose=False, imgsz=1280
            )
            result = results[0]

            if candidate_track_id is None:
                # Still searching for initial match
                track_id = self._find_player_in_frame(frame, result)
                if track_id is not None:
                    candidate_track_id = track_id
                    candidate_frame_idx = frame_idx
                    candidate_frame = frame.copy()
                    confirm_count = 1
                    if confirm_count >= confirmation_needed:
                        self._capture_appearance(frame, track_id, result)
                        return frame_idx, track_id
            else:
                # Confirming candidate across subsequent frames
                if self._track_id_present(result, candidate_track_id):
                    confirm_count += 1
                    if confirm_count >= confirmation_needed:
                        self._capture_appearance(candidate_frame, candidate_track_id, None)
                        return candidate_frame_idx, candidate_track_id
                else:
                    # Candidate disappeared — reset and keep searching
                    logger.debug(
                        "Candidate track_id=%s lost during confirmation at frame=%s",
                        candidate_track_id,
                        frame_idx,
                    )
                    candidate_track_id = None
                    candidate_frame_idx = None
                    candidate_frame = None
                    confirm_count = 0
                    # Try this frame as a fresh start
                    track_id = self._find_player_in_frame(frame, result)
                    if track_id is not None:
                        candidate_track_id = track_id
                        candidate_frame_idx = frame_idx
                        candidate_frame = frame.copy()
                        confirm_count = 1

            frame_idx += 1

    @staticmethod
    def _track_id_present(result, track_id: int) -> bool:
        """Check whether a given track_id appears in a YOLO result."""
        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return False
        ids = boxes.id.cpu().numpy().astype(int).tolist()
        return track_id in ids

    def _capture_appearance(
        self, frame: np.ndarray, track_id: int, result
    ) -> None:
        """Store the appearance histogram of the matched player."""
        bbox = None
        if result is not None:
            boxes = result.boxes
            if boxes is not None and boxes.id is not None:
                for i, cls_tensor in enumerate(boxes.cls):
                    if int(cls_tensor.item()) != _PERSON_CLASS:
                        continue
                    if int(boxes.id[i].item()) == track_id:
                        xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
                        bbox = (xyxy[0], xyxy[1], xyxy[2] - xyxy[0], xyxy[3] - xyxy[1])
                        break
        if bbox is None and self.player_ref.method == "bbox" and self.player_ref.bbox is not None:
            bbox = self.player_ref.bbox
        if bbox is not None:
            self._target_appearance = _compute_appearance_histogram(frame, bbox)
            logger.debug("Captured appearance histogram for track_id=%s", track_id)

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
                # Refresh appearance model every ~90 frames during confident tracking
                if (
                    self._target_appearance is not None
                    and player_box is not None
                    and self._frames_total % 90 == 0
                ):
                    new_hist = _compute_appearance_histogram(frame, player_box)
                    sim = _appearance_similarity(self._target_appearance, new_hist)
                    if sim > 0.7:
                        self._target_appearance = (
                            0.9 * self._target_appearance + 0.1 * new_hist
                        )

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
            return self._find_by_bbox(frame, result)

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

    def _find_by_bbox(self, frame: np.ndarray, result) -> Optional[int]:
        """Match user-drawn bbox to detected persons using combined scoring.

        Uses a weighted combination of:
        - IoU overlap (primary signal when the drawn box is precise)
        - Centre-point distance (fallback when the drawn box is imprecise)
        - Relative size similarity (penalises wildly different-sized detections)

        This replaces the previous IoU-only approach which failed when users
        drew imprecise boxes or when YOLO detection boxes didn't align well.
        """
        ref_bbox = self.player_ref.bbox  # (x, y, w, h)
        if ref_bbox is None:
            return None

        boxes = result.boxes
        if boxes is None or boxes.id is None:
            return None

        ref_cx, ref_cy = _center(ref_bbox)
        ref_area = ref_bbox[2] * ref_bbox[3]
        # Use the diagonal of the reference box as normalisation for distance
        ref_diag = max(1.0, (ref_bbox[2] ** 2 + ref_bbox[3] ** 2) ** 0.5)

        best_score = -1.0
        best_track_id: Optional[int] = None

        for i, cls_tensor in enumerate(boxes.cls):
            if int(cls_tensor.item()) != _PERSON_CLASS:
                continue

            xyxy = boxes.xyxy[i].cpu().numpy().astype(int)
            x1, y1, x2, y2 = xyxy
            det_bbox = (x1, y1, x2 - x1, y2 - y1)

            # IoU component [0, 1]
            iou = _iou(ref_bbox, det_bbox)

            # Centre-distance component: convert distance to a [0, 1] similarity
            dist = _center_distance(ref_bbox, det_bbox)
            dist_sim = max(0.0, 1.0 - dist / (ref_diag * 3.0))

            # Size similarity: ratio of smaller area to larger area [0, 1]
            det_area = det_bbox[2] * det_bbox[3]
            if ref_area > 0 and det_area > 0:
                size_sim = min(ref_area, det_area) / max(ref_area, det_area)
            else:
                size_sim = 0.0

            # Combined score: IoU dominates when overlap exists, distance helps
            # when the user-drawn box is offset from the detection
            score = 0.5 * iou + 0.35 * dist_sim + 0.15 * size_sim

            if score > best_score:
                best_score = score
                best_track_id = int(boxes.id[i].item())

        # Require a minimum combined score to avoid matching distant players
        return best_track_id if best_score > 0.15 else None

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
        """Pick the best fallback candidate when current target id disappears.

        Uses a combined scoring approach:
        - Spatial continuity (IoU with last known position)
        - Appearance similarity (histogram match with captured target appearance)
        - Detection confidence

        For bbox mode, the appearance signal is especially important because
        the original user-drawn box becomes stale as the player moves.
        """
        if not candidates:
            return None

        def _score(candidate: tuple[int, tuple[int, int, int, int], float]) -> float:
            _track_id, bbox, conf = candidate
            score = 0.0

            # Spatial continuity with last known position
            if self._last_player_box is not None:
                iou = _iou(self._last_player_box, bbox)
                dist = _center_distance(self._last_player_box, bbox)
                last_diag = max(
                    1.0,
                    (self._last_player_box[2] ** 2 + self._last_player_box[3] ** 2) ** 0.5,
                )
                dist_sim = max(0.0, 1.0 - dist / (last_diag * 4.0))
                spatial = 0.6 * iou + 0.4 * dist_sim
                score += 0.45 * spatial

            # Appearance similarity (bbox mode or when appearance is captured)
            if self._target_appearance is not None:
                cand_appearance = _compute_appearance_histogram(frame, bbox)
                app_sim = _appearance_similarity(self._target_appearance, cand_appearance)
                score += 0.40 * app_sim

            # Anchor to original user-drawn box (bbox mode only, decayed weight)
            if self.player_ref.method == "bbox" and self.player_ref.bbox is not None:
                anchor_iou = _iou(self.player_ref.bbox, bbox)
                score += 0.05 * anchor_iou

            # Detection confidence as tiebreaker
            score += 0.10 * conf

            return score

        # For jersey mode with color hint but no appearance, fall back to color matching
        jersey_color = (self.player_ref.jersey_color or "").strip()
        if self.player_ref.method == "jersey" and jersey_color and self._target_appearance is None:
            ref_hist = _get_reference_histogram(jersey_color)

            def _sim(candidate: tuple[int, tuple[int, int, int, int], float]) -> float:
                _track_id, bbox, _conf = candidate
                x, y, w, h = bbox
                x, y = max(0, x), max(0, y)
                crop = frame[y : y + h, x : x + w]
                return _color_similarity(_compute_hsv_histogram(crop), ref_hist)

            return max(candidates, key=_sim)

        best = max(candidates, key=_score)

        # Update appearance model periodically during confident tracking
        if self._target_appearance is not None:
            best_appearance = _compute_appearance_histogram(frame, best[1])
            sim = _appearance_similarity(self._target_appearance, best_appearance)
            if sim > 0.7:
                # Exponential moving average to adapt to lighting changes
                self._target_appearance = (
                    0.9 * self._target_appearance + 0.1 * best_appearance
                )

        return best

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
