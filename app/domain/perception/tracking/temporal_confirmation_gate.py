"""
temporal_confirmation_gate.py
------------------------------
Temporal confirmation filter to suppress 1-2 frame false-positive specular reflection
flickers and transient noise during 360° vehicle walkarounds. Enforces that a damage
track must persist for at least K frames within a sliding window of W frames before
being confirmed and passed downstream to Set-of-Marks and Actuarial Pricing.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Deque, Dict, List, Set


class TemporalConfirmationGate:
    """Sliding-window confirmation filter for persistent damage tracking."""

    def __init__(
        self,
        min_hits: int = 3,
        window_size: int = 20,
        max_inactive_frames: int = 60,
    ):
        self.min_hits = min_hits
        self.window_size = window_size
        self.max_inactive_frames = max_inactive_frames

        # track_id -> deque of recent frame indices within sliding window
        self._window_history: Dict[int, Deque[int]] = defaultdict(deque)
        # track_id -> total lifetime detection occurrences
        self._total_hits: Dict[int, int] = defaultdict(int)
        # track_id -> last observed frame index
        self._last_seen_frame: Dict[int, int] = {}
        # Set of permanently confirmed track IDs
        self._confirmed_ids: Set[int] = set()

    def update(self, frame_idx: int, active_track_ids: List[int]) -> Set[int]:
        """Updates temporal histories with tracks detected at the current frame.

        Args:
            frame_idx: Current video frame index.
            active_track_ids: List of track IDs detected in this frame.

        Returns:
            Set of newly confirmed track IDs that reached min_hits at this frame.
        """
        newly_confirmed: Set[int] = set()
        window_start = frame_idx - self.window_size + 1

        for tid in active_track_ids:
            self._total_hits[tid] += 1
            self._last_seen_frame[tid] = frame_idx

            dq = self._window_history[tid]
            dq.append(frame_idx)

            # Evict frames outside sliding window
            while dq and dq[0] < window_start:
                dq.popleft()

            # Check confirmation condition
            if tid not in self._confirmed_ids and len(dq) >= self.min_hits:
                self._confirmed_ids.add(tid)
                newly_confirmed.add(tid)

        # Evict stale entries from unconfirmed tracks
        for tid in list(self._window_history.keys()):
            if tid not in active_track_ids:
                dq = self._window_history[tid]
                while dq and dq[0] < window_start:
                    dq.popleft()

                # Clean up memory if unconfirmed and inactive
                last_seen = self._last_seen_frame.get(tid, 0)
                if tid not in self._confirmed_ids and (frame_idx - last_seen) > self.max_inactive_frames:
                    del self._window_history[tid]
                    self._last_seen_frame.pop(tid, None)
                    self._total_hits.pop(tid, None)

        return newly_confirmed

    def is_confirmed(self, track_id: int) -> bool:
        """Returns True if the track ID has met the temporal persistence threshold."""
        return track_id in self._confirmed_ids

    def get_hit_count_in_window(self, track_id: int) -> int:
        """Returns the number of hits in the current active window for the track ID."""
        return len(self._window_history.get(track_id, []))

    def get_total_hits(self, track_id: int) -> int:
        """Returns total lifetime occurrences for this track ID."""
        return self._total_hits.get(track_id, 0)

    def get_confirmed_ids(self) -> Set[int]:
        """Returns a copy of the set of all confirmed track IDs."""
        return set(self._confirmed_ids)

    def clear(self) -> None:
        """Resets all filter state."""
        self._window_history.clear()
        self._total_hits.clear()
        self._last_seen_frame.clear()
        self._confirmed_ids.clear()
