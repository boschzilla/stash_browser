"""
detector.py - Monster detection via motion + player exclusion.

Strategy:
  1. Frame diff to find moving pixels
  2. Mask out the player character (blue/cyan energy shield glow)
  3. Filter blobs by size, aspect ratio, and centroid travel distance
  4. Surviving blobs are monsters
"""

import cv2
import numpy as np
from typing import List, Tuple

# ── Tuning constants ────────────────────────────────────────────────────────

# How different a pixel must be between frames to count as motion
MOTION_THRESHOLD = 18

# Blob area bounds (display pixels).  Raise MIN to cut noise, lower MAX to cut
# huge terrain blobs (water, large particle effects).
MIN_BLOB_AREA = 300
MAX_BLOB_AREA = 18_000

# Aspect ratio filter: width / height.
# Monsters are roughly portrait or square; water waves are very wide/flat.
MAX_ASPECT_RATIO = 2.5   # skip blobs wider than 2.5× their height
MIN_ASPECT_RATIO = 0.2   # skip blobs taller than 5× their width (thin vertical streaks)

# Dilation kernel to merge nearby motion blobs into one entity
MERGE_KERNEL = (20, 20)

# HSV range for the player's blue/cyan energy shield glow
PLAYER_LO = np.array([90,  60,  80], dtype=np.uint8)
PLAYER_HI = np.array([140, 255, 255], dtype=np.uint8)

# How many pixels to expand the player mask (covers the full model)
PLAYER_DILATE = 55

# Centroid tracker — a blob must move at least this many pixels over
# TRAVEL_FRAMES frames to be considered a monster (not looping terrain).
TRAVEL_MIN_PX = 8
TRAVEL_FRAMES = 6


# ── Internal helpers ─────────────────────────────────────────────────────────

def _centroid(box: Tuple[int, int, int, int]) -> Tuple[float, float]:
    x, y, w, h = box
    return x + w / 2, y + h / 2


def _dist(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


# ── Detector ────────────────────────────────────────────────────────────────

class MonsterDetector:
    """
    Stateful detector — call detect() on each frame in order.

    Each candidate blob is tracked for TRAVEL_FRAMES frames.
    Only blobs whose centroid has moved >= TRAVEL_MIN_PX are returned as monsters.
    This filters out animated terrain that loops in place.
    """

    def __init__(self):
        self._prev_gray: np.ndarray | None = None
        # list of dicts: {cx, cy, min_cx, min_cy, max_cx, max_cy, frames, box}
        self._tracked: list = []

    def detect(self, frame: np.ndarray) -> List[Tuple[int, int, int, int]]:
        """
        frame : BGR numpy array (display-resolution)
        Returns list of (x, y, w, h) bounding boxes for confirmed monsters.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (5, 5), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return []

        # 1. Motion mask
        diff = cv2.absdiff(self._prev_gray, gray)
        _, motion = cv2.threshold(diff, MOTION_THRESHOLD, 255, cv2.THRESH_BINARY)

        # 2. Player exclusion
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        player_mask = cv2.inRange(hsv, PLAYER_LO, PLAYER_HI)
        player_mask = cv2.dilate(
            player_mask,
            np.ones((PLAYER_DILATE, PLAYER_DILATE), np.uint8),
        )
        motion = cv2.bitwise_and(motion, cv2.bitwise_not(player_mask))

        # 3. Merge nearby blobs
        motion = cv2.dilate(motion, np.ones(MERGE_KERNEL, np.uint8), iterations=2)

        # 4. Find raw candidates with size + aspect ratio filter
        contours, _ = cv2.findContours(motion, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        candidates = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < MIN_BLOB_AREA or area > MAX_BLOB_AREA:
                continue
            x, y, w, h = cv2.boundingRect(cnt)
            ratio = w / max(h, 1)
            if ratio > MAX_ASPECT_RATIO or ratio < MIN_ASPECT_RATIO:
                continue
            candidates.append((x, y, w, h))

        # 5. Update centroid tracker
        self._update_tracker(candidates)

        self._prev_gray = gray

        # 6. Return only blobs that have demonstrated real movement
        confirmed = [t["box"] for t in self._tracked
                     if t["frames"] >= TRAVEL_FRAMES
                     and t["travel"] >= TRAVEL_MIN_PX]
        return confirmed

    def _update_tracker(self, candidates: List[Tuple[int, int, int, int]]) -> None:
        """Match candidates to existing tracks, add new ones, age out stale ones."""
        MATCH_RADIUS = 60   # px — max centroid jump to link to existing track
        MAX_MISSING = 4     # frames a track can go unmatched before removal

        new_tracked = []
        matched_idx = set()

        for track in self._tracked:
            tc = (track["cx"], track["cy"])
            best_d, best_i = float("inf"), -1
            for i, box in enumerate(candidates):
                if i in matched_idx:
                    continue
                d = _dist(tc, _centroid(box))
                if d < best_d:
                    best_d, best_i = d, i

            if best_d < MATCH_RADIUS and best_i >= 0:
                matched_idx.add(best_i)
                box = candidates[best_i]
                cx, cy = _centroid(box)
                # Accumulate total travel distance
                travel = track["travel"] + _dist(tc, (cx, cy))
                new_tracked.append({
                    "cx": cx, "cy": cy,
                    "travel": travel,
                    "frames": track["frames"] + 1,
                    "missing": 0,
                    "box": box,
                })
            else:
                # Unmatched — keep for a few frames in case of occlusion
                track["missing"] = track.get("missing", 0) + 1
                if track["missing"] <= MAX_MISSING:
                    new_tracked.append(track)

        # New blobs not matched to any track
        for i, box in enumerate(candidates):
            if i not in matched_idx:
                cx, cy = _centroid(box)
                new_tracked.append({
                    "cx": cx, "cy": cy,
                    "travel": 0.0,
                    "frames": 1,
                    "missing": 0,
                    "box": box,
                })

        self._tracked = new_tracked

    def reset(self):
        """Call when the scene changes (zone transition, loading screen)."""
        self._prev_gray = None
        self._tracked = []


def draw_detections(frame: np.ndarray, boxes: List[Tuple[int, int, int, int]]) -> None:
    """Draw red bounding boxes + count label onto frame (in-place)."""
    for i, (x, y, w, h) in enumerate(boxes):
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)
        cv2.putText(frame, f"MOB {i+1}", (x, max(y - 5, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1, cv2.LINE_AA)

    if boxes:
        cv2.putText(frame, f"Monsters: {len(boxes)}", (10, frame.shape[0] - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2, cv2.LINE_AA)
