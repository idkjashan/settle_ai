"""
reid_gallery.py
----------------
Appearance-based re-identification gallery for trackers during 360° walkarounds.
Maintains a temporal bank of lost/inactive track appearance footprints, computing cosine
similarity with optimal Hungarian bipartite assignment (scipy.optimize.linear_sum_assignment)
to re-identify lost tracks instead of spawning redundant IDs.
"""

from __future__ import annotations

from typing import Dict, List, Optional
import numpy as np
from scipy.optimize import linear_sum_assignment


class ReidGallery:
    """Temporal appearance bank of lost track embeddings."""

    def __init__(
        self,
        cosine_thresh: float = 0.60,
        max_gap: int = 150,
        max_samples_per_track: int = 5,
        debug: bool = False,
    ):
        self.cosine_thresh = cosine_thresh
        self.max_gap = max_gap
        self.max_samples_per_track = max_samples_per_track
        self.debug = debug

        # final_id -> {
        #   "embeds": (K, D) L2-unit normalized vectors,
        #   "frames_lost": int,
        #   "buried_frame": int | None
        # }
        self._bank: Dict[int, Dict] = {}

    @property
    def bank_size(self) -> int:
        """Returns the number of currently lost identities retained in the bank."""
        return len(self._bank)

    def get_lost_ids(self) -> List[int]:
        """Returns list of all lost track IDs currently in the gallery."""
        return list(self._bank.keys())

    def clear(self) -> None:
        """Clears all bank entries."""
        self._bank.clear()

    def bury(
        self,
        final_id: int,
        embeds: np.ndarray,
        frame_id: Optional[int] = None,
    ) -> None:
        """Registers the appearance footprint of an active identity that just became lost.

        Args:
            final_id: The persistent track ID being buried.
            embeds: (D,) single embedding or (K, D) multi-sample embeddings.
            frame_id: The frame index where the track was lost.
        """
        arr = np.atleast_2d(embeds).astype(np.float32)
        # Normalize each sample vector to unit L2 norm
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        arr = arr / (norms + 1e-9)

        # Cap retained representative samples to max_samples_per_track
        if arr.shape[0] > self.max_samples_per_track:
            # Subsample evenly across track lifecycle
            indices = np.linspace(0, arr.shape[0] - 1, self.max_samples_per_track, dtype=int)
            arr = arr[indices]

        self._bank[final_id] = {
            "embeds": arr,
            "frames_lost": 0,
            "buried_frame": frame_id,
        }

        if self.debug:
            print(
                f"[GALLERY] bury frame={frame_id} final_id={final_id} "
                f"n_samples={arr.shape[0]} bank_size={len(self._bank)}"
            )

    def age_and_prune(self, frame_id: Optional[int] = None) -> List[int]:
        """Ages all lost tracks in the gallery and permanently prunes entries exceeding max_gap.

        Returns:
            List of pruned track IDs.
        """
        pruned: List[int] = []
        for fid in list(self._bank.keys()):
            self._bank[fid]["frames_lost"] += 1
            if self._bank[fid]["frames_lost"] > self.max_gap:
                pruned.append(fid)
                if self.debug:
                    print(
                        f"[GALLERY] prune frame={frame_id} final_id={fid} "
                        f"frames_lost={self._bank[fid]['frames_lost']} max_gap={self.max_gap}"
                    )
                del self._bank[fid]
        return pruned

    def match_newborns(
        self,
        embeds: np.ndarray,
        candidate_ids: Optional[List[int]] = None,
        frame_id: Optional[int] = None,
    ) -> List[Optional[int]]:
        """Matches candidate embeddings of newborn detections against the gallery of lost tracks.

        Uses maximum cosine similarity across representative track samples and solves
        the global bipartite matching problem via Hungarian assignment (linear_sum_assignment).

        Args:
            embeds: (M, D) candidate newborn embeddings.
            candidate_ids: Optional raw tracker IDs for logging.
            frame_id: Current frame index.

        Returns:
            List of length M containing either matched historic final_id or None.
        """
        if embeds is None or len(embeds) == 0:
            return []

        num_cands = embeds.shape[0]
        if len(self._bank) == 0:
            return [None] * num_cands

        # Ensure candidate embeddings are 2D and unit normalized
        cands = np.atleast_2d(embeds).astype(np.float32)
        c_norms = np.linalg.norm(cands, axis=1, keepdims=True)
        cands = cands / (c_norms + 1e-9)

        bank_fids = list(self._bank.keys())
        num_gallery = len(bank_fids)

        # Build similarity matrix (M, K)
        # For each lost track in gallery, compute max cosine similarity across its stored sample embeddings
        sim_matrix = np.zeros((num_cands, num_gallery), dtype=np.float32)

        for col_idx, fid in enumerate(bank_fids):
            gallery_samples = self._bank[fid]["embeds"]  # (S_j, D)
            # Dot product: (M, D) @ (D, S_j) -> (M, S_j)
            cand_to_samples = np.matmul(cands, gallery_samples.T)
            # Max similarity for this track across stored samples
            sim_matrix[:, col_idx] = np.max(cand_to_samples, axis=1)

        # Cost matrix for Hungarian matching: cost = 1.0 - similarity
        cost_matrix = 1.0 - sim_matrix

        # Solve optimal linear sum assignment
        row_ind, col_ind = linear_sum_assignment(cost_matrix)

        matches: List[Optional[int]] = [None] * num_cands
        resurrected_fids: List[int] = []

        for r, c in zip(row_ind, col_ind):
            sim = sim_matrix[r, c]
            if sim >= self.cosine_thresh:
                matched_fid = bank_fids[c]
                matches[r] = matched_fid
                resurrected_fids.append(matched_fid)
                if self.debug:
                    buried_f = self._bank[matched_fid].get("buried_frame")
                    gap = (frame_id - buried_f) if (frame_id is not None and buried_f is not None) else None
                    cand_id_str = f" cand_raw_id={candidate_ids[r]}" if candidate_ids else ""
                    print(
                        f"[GALLERY MATCH] frame={frame_id}{cand_id_str} -> re-identified "
                        f"final_id={matched_fid} sim={sim:.4f} (gap={gap} frames)"
                    )

        # Remove resurrected tracks from the gallery (they are now active again)
        for r_fid in resurrected_fids:
            if r_fid in self._bank:
                del self._bank[r_fid]

        return matches
