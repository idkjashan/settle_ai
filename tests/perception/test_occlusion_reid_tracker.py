"""
tests/perception/test_occlusion_reid_tracker.py
-----------------------------------------------
Comprehensive unit and integration test suite for the Auto-Settle AI
occlusion-robust vehicle damage tracking pipeline:
1. C4FeatureExtractor (hook attachment, RoIAlign pooling, L2 unit norm, empty boxes)
2. ReidGallery (bury, age_and_prune, Hungarian matching, threshold acceptance/rejection,
   multi-sample footprint, max_gap pruning)
3. TemporalConfirmationGate (sliding window K-of-W persistence, 1-2 frame reflection
   flicker suppression, inactive memory cleanup)
4. OcclusionReIDTracker (end-to-end frame tracking, video tracking on simple/difficult
   video cohorts with cardd-yolov8s-seg.pt, ID switch reduction, confirmed track output)
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple
import cv2
import numpy as np
import pytest
import torch
import torch.nn as nn
from ultralytics import YOLO

from app.domain.perception.tracking.feature_extractor import C4FeatureExtractor
from app.domain.perception.tracking.reid_gallery import ReidGallery
from app.domain.perception.tracking.temporal_confirmation_gate import (
    TemporalConfirmationGate,
)
from app.domain.perception.tracking.occlusion_reid_tracker import (
    OcclusionReIDTracker,
    TrackedDamage,
    TrackedDamageSummary,
    VideoTrackingResult,
)

WORKSPACE_ROOT = Path("/home/jashan/settleai")
CARDD_WEIGHTS = WORKSPACE_ROOT / "weights" / "cardd-yolov8s-seg.pt"
SIMPLE_VIDEO_CAR001 = WORKSPACE_ROOT / "test_assets" / "videos" / "simple" / "car_001.mp4"
SIMPLE_VIDEO_AVEO = WORKSPACE_ROOT / "test_assets" / "videos" / "simple" / "aveo.mp4"
DIFFICULT_VIDEO_COLLISION = (
    WORKSPACE_ROOT
    / "test_assets"
    / "videos"
    / "difficult"
    / "scenario_01_damaged_collision.mp4"
)
RTDETR_VD_AVEO = (
    WORKSPACE_ROOT / "test_assets" / "rtdetr_vd" / "dataset" / "test" / "aveo" / "aveo.mp4"
)


# ==============================================================================
# Helper Mock Modules & Fixtures
# ==============================================================================


class MockBackboneDetector(nn.Module):
    """Synthetic multi-layer CNN mimicking YOLO backbone layers for unit tests."""

    def __init__(self, in_channels: int = 3, num_layers: int = 8, feat_channels: int = 64):
        super().__init__()
        layers = []
        c_in = in_channels
        for i in range(num_layers):
            c_out = feat_channels if i >= 4 else 32
            layers.append(nn.Conv2d(c_in, c_out, kernel_size=3, stride=2 if i % 2 == 1 else 1, padding=1))
            c_in = c_out
        self.model = nn.Module()
        self.model.model = nn.Sequential(*layers)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.model.model(x)


@pytest.fixture
def mock_detector() -> MockBackboneDetector:
    return MockBackboneDetector(in_channels=3, num_layers=8, feat_channels=64)


@pytest.fixture
def feature_extractor_mock(mock_detector: MockBackboneDetector) -> C4FeatureExtractor:
    return C4FeatureExtractor(model=mock_detector, layer_idx=6, spatial_stride=16)


# ==============================================================================
# 1. Unit Tests: C4FeatureExtractor
# ==============================================================================


class TestC4FeatureExtractor:
    """Unit tests verifying hook attachment, intermediate feature capture,
    RoIAlign feature pooling, L2 normalization, and empty box handling.
    """

    def test_hook_attachment_and_feature_capture(
        self, mock_detector: MockBackboneDetector, feature_extractor_mock: C4FeatureExtractor
    ):
        """Verifies PyTorch hook registers onto target layer and captures feature maps during forward pass."""
        assert feature_extractor_mock._hook_handle is not None
        assert feature_extractor_mock.captured_feature_map is None

        # Execute forward pass through mock detector
        dummy_input = torch.randn(1, 3, 256, 256)
        _ = mock_detector(dummy_input)

        captured = feature_extractor_mock.captured_feature_map
        assert captured is not None
        assert isinstance(captured, torch.Tensor)
        assert captured.ndim == 4
        assert captured.shape[0] == 1
        assert captured.shape[1] == 64  # feat_channels at layer 6

    def test_hook_removal(
        self, mock_detector: MockBackboneDetector, feature_extractor_mock: C4FeatureExtractor
    ):
        """Verifies hook can be cleanly detached and no longer captures outputs."""
        feature_extractor_mock.remove_hook()
        assert feature_extractor_mock._hook_handle is None

        feature_extractor_mock.captured_feature_map = None
        dummy_input = torch.randn(1, 3, 256, 256)
        _ = mock_detector(dummy_input)
        assert feature_extractor_mock.captured_feature_map is None

    def test_attach_hook_invalid_model_raises_value_error(self):
        """Verifies ValueError when provided model structure is unrecognized or layer cannot be located."""
        class DummyNonModule:
            pass

        with pytest.raises(ValueError, match="Could not locate layer index"):
            C4FeatureExtractor(model=DummyNonModule(), layer_idx=10)

    def test_roialign_output_shape_and_l2_unit_norm(self):
        """Verifies RoIAlign extracts (N, C) feature embeddings and normalizes each to unit L2 norm."""
        extractor = C4FeatureExtractor(spatial_stride=16, roi_output_size=(7, 7))

        # Synthetic feature map: 1 batch, 128 channels, 20x20 feature map
        c_channels = 128
        feature_map = torch.randn(1, c_channels, 20, 20)
        extractor.captured_feature_map = feature_map

        # 4 bounding boxes in xyxy format
        boxes = [
            [10.0, 15.0, 50.0, 65.0],
            [30.0, 40.0, 120.0, 160.0],
            [100.0, 80.0, 200.0, 220.0],
            [0.0, 0.0, 320.0, 320.0],
        ]

        # Extract embeddings
        embeds = extractor.extract_roi_embeddings(boxes)

        assert isinstance(embeds, np.ndarray)
        assert embeds.shape == (4, c_channels)
        assert embeds.dtype == np.float32

        # Verify L2 unit norm for every single bounding box embedding
        norms = np.linalg.norm(embeds, axis=1)
        np.testing.assert_allclose(norms, 1.0, atol=1e-5)

    def test_roialign_box_formats_acceptance(self):
        """Verifies extract_roi_embeddings supports list, numpy array, and torch.Tensor boxes."""
        extractor = C4FeatureExtractor(spatial_stride=16)
        feat = torch.randn(1, 64, 16, 16)
        extractor.captured_feature_map = feat

        raw_box = [16.0, 16.0, 64.0, 64.0]

        # 1D single box
        emb_1d = extractor.extract_roi_embeddings(raw_box)
        assert emb_1d.shape == (1, 64)

        # 2D list
        emb_list = extractor.extract_roi_embeddings([raw_box, raw_box])
        assert emb_list.shape == (2, 64)

        # 2D numpy array
        emb_np = extractor.extract_roi_embeddings(np.array([raw_box, raw_box]))
        assert emb_np.shape == (2, 64)

        # 2D torch tensor
        emb_torch = extractor.extract_roi_embeddings(torch.tensor([raw_box, raw_box]))
        assert emb_torch.shape == (2, 64)

    def test_roialign_empty_boxes_handling(self):
        """Verifies extract_roi_embeddings handles empty bounding box collections without crashing."""
        extractor = C4FeatureExtractor(spatial_stride=16)
        c_channels = 96
        extractor.captured_feature_map = torch.randn(1, c_channels, 16, 16)

        # Empty python list
        out_list = extractor.extract_roi_embeddings([])
        assert out_list.shape == (0, c_channels)
        assert out_list.dtype == np.float32

        # Empty numpy array
        out_np = extractor.extract_roi_embeddings(np.empty((0, 4)))
        assert out_np.shape == (0, c_channels)

        # Empty torch tensor
        out_tensor = extractor.extract_roi_embeddings(torch.empty((0, 4)))
        assert out_tensor.shape == (0, c_channels)

    def test_roialign_coordinate_scaling(self):
        """Verifies coordinate scaling when input image resolution differs from spatial stride mapping."""
        extractor = C4FeatureExtractor(spatial_stride=16)
        # Feature map is 10x10. At stride 16, native image size is 160x160.
        feat = torch.randn(1, 32, 10, 10)
        boxes = [[20.0, 20.0, 60.0, 60.0]]

        # Pass image shape (320, 320) -> scale factor 0.5 applied
        embeds = extractor.extract_roi_embeddings(boxes, feature_map=feat, img_shape=(320, 320))
        assert embeds.shape == (1, 32)
        assert np.isclose(np.linalg.norm(embeds[0]), 1.0, atol=1e-5)

    def test_extract_without_feature_map_raises_runtime_error(self):
        """Verifies calling extract_roi_embeddings without any available feature map raises RuntimeError."""
        extractor = C4FeatureExtractor(spatial_stride=16)
        extractor.captured_feature_map = None
        with pytest.raises(RuntimeError, match="No feature map available"):
            extractor.extract_roi_embeddings([[0, 0, 10, 10]])

    def test_extract_with_invalid_box_type_raises_type_error(self):
        """Verifies passing invalid box type raises TypeError."""
        extractor = C4FeatureExtractor(spatial_stride=16)
        extractor.captured_feature_map = torch.randn(1, 32, 10, 10)
        with pytest.raises(TypeError, match="Unsupported boxes type"):
            extractor.extract_roi_embeddings("invalid_box_type")  # type: ignore


# ==============================================================================
# 2. Unit Tests: ReidGallery
# ==============================================================================


class TestReidGallery:
    """Unit tests for ReidGallery: appearance bank burial, lifecycle aging/pruning,
    Hungarian bipartite matching, threshold acceptance/rejection, and multi-sample footprint.
    """

    def test_gallery_bury_single_and_multi_embedding(self):
        """Verifies burying 1D and 2D appearance embeddings, checking L2 normalization."""
        gallery = ReidGallery(cosine_thresh=0.60, max_gap=10, max_samples_per_track=5)
        assert gallery.bank_size == 0
        assert gallery.get_lost_ids() == []

        # Single 1D embedding (norm is non-unit 5.0)
        vec_1d = np.ones(64, dtype=np.float32) * 5.0
        gallery.bury(final_id=101, embeds=vec_1d, frame_id=12)

        assert gallery.bank_size == 1
        assert gallery.get_lost_ids() == [101]
        stored_entry = gallery._bank[101]
        assert stored_entry["frames_lost"] == 0
        assert stored_entry["buried_frame"] == 12
        assert stored_entry["embeds"].shape == (1, 64)
        np.testing.assert_allclose(np.linalg.norm(stored_entry["embeds"][0]), 1.0, atol=1e-5)

        # Multi-sample 2D embedding
        vecs_2d = np.random.randn(3, 64).astype(np.float32)
        gallery.bury(final_id=202, embeds=vecs_2d, frame_id=15)

        assert gallery.bank_size == 2
        assert set(gallery.get_lost_ids()) == {101, 202}
        assert gallery._bank[202]["embeds"].shape == (3, 64)
        for row in gallery._bank[202]["embeds"]:
            np.testing.assert_allclose(np.linalg.norm(row), 1.0, atol=1e-5)

    def test_gallery_bury_multi_sample_capping(self):
        """Verifies gallery subsamples down to max_samples_per_track when track has many frames."""
        gallery = ReidGallery(max_samples_per_track=5)
        # Supply 12 historical samples
        history = np.random.randn(12, 32).astype(np.float32)
        gallery.bury(final_id=303, embeds=history, frame_id=20)

        assert gallery._bank[303]["embeds"].shape == (5, 32)

    def test_gallery_age_and_prune(self):
        """Verifies aging increments frames_lost and removes tracks exceeding max_gap."""
        gallery = ReidGallery(max_gap=3)
        emb = np.random.randn(16).astype(np.float32)
        gallery.bury(final_id=1, embeds=emb, frame_id=100)
        gallery.bury(final_id=2, embeds=emb, frame_id=100)

        # Frame 101: frames_lost = 1 <= 3
        pruned_1 = gallery.age_and_prune(frame_id=101)
        assert pruned_1 == []
        assert gallery.bank_size == 2

        # Frame 102: frames_lost = 2 <= 3
        pruned_2 = gallery.age_and_prune(frame_id=102)
        assert pruned_2 == []
        assert gallery.bank_size == 2

        # Frame 103: frames_lost = 3 <= 3
        pruned_3 = gallery.age_and_prune(frame_id=103)
        assert pruned_3 == []
        assert gallery.bank_size == 2

        # Frame 104: frames_lost = 4 > 3 -> Pruned!
        pruned_4 = gallery.age_and_prune(frame_id=104)
        assert set(pruned_4) == {1, 2}
        assert gallery.bank_size == 0
        assert gallery.get_lost_ids() == []

    def test_gallery_hungarian_matching_threshold_acceptance(self):
        """Verifies Hungarian bipartite assignment matches candidates when cosine similarity >= threshold."""
        gallery = ReidGallery(cosine_thresh=0.60)

        # Construct distinct unit vectors
        v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        v2 = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)

        gallery.bury(final_id=10, embeds=v1, frame_id=1)
        gallery.bury(final_id=20, embeds=v2, frame_id=1)
        assert gallery.bank_size == 2

        # Candidate embeddings: c1 is very close to v1 (cos ~ 0.98), c2 is very close to v2 (cos ~ 0.98)
        c1 = np.array([0.98, 0.20, 0.0, 0.0], dtype=np.float32)
        c2 = np.array([0.15, 0.99, 0.0, 0.0], dtype=np.float32)
        cands = np.stack([c1, c2])

        matches = gallery.match_newborns(cands, candidate_ids=[1001, 1002], frame_id=5)

        # Candidate 0 matches ID 10, Candidate 1 matches ID 20
        assert matches == [10, 20]
        # Resurrected tracks are removed from the gallery bank
        assert gallery.bank_size == 0

    def test_gallery_hungarian_matching_threshold_rejection(self):
        """Verifies Hungarian assignment rejects candidates whose similarity is strictly below threshold."""
        gallery = ReidGallery(cosine_thresh=0.75)

        v1 = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        gallery.bury(final_id=10, embeds=v1, frame_id=1)

        # Candidate with cosine similarity ~ 0.50 (below 0.75)
        c_low = np.array([0.50, 0.866, 0.0, 0.0], dtype=np.float32)

        matches = gallery.match_newborns(np.expand_dims(c_low, 0), candidate_ids=[999], frame_id=5)

        assert matches == [None]
        # Track 10 was not resurrected, remains in gallery
        assert gallery.bank_size == 1
        assert gallery.get_lost_ids() == [10]

    def test_gallery_multi_sample_footprint_matching(self):
        """Verifies candidate matches buried track if it resembles ANY angle across stored multi-sample footprint."""
        gallery = ReidGallery(cosine_thresh=0.70)

        # Buried track 7 observed at 3 angles: front, side, rear
        angle_front = np.array([1.0, 0.0, 0.0, 0.0], dtype=np.float32)
        angle_side = np.array([0.0, 1.0, 0.0, 0.0], dtype=np.float32)
        angle_rear = np.array([0.0, 0.0, 1.0, 0.0], dtype=np.float32)
        gallery.bury(final_id=7, embeds=np.stack([angle_front, angle_side, angle_rear]))

        # Newborn candidate matches the 'rear' angle with high similarity 0.95,
        # but has near-zero similarity to 'front' and 'side'.
        cand_rear = np.array([0.05, 0.05, 0.99, 0.0], dtype=np.float32)

        matches = gallery.match_newborns(np.expand_dims(cand_rear, 0), candidate_ids=[888])

        # Successfully matches ID 7 using max-similarity across the 3 samples
        assert matches == [7]
        assert gallery.bank_size == 0

    def test_gallery_bipartite_matching_uniqueness(self):
        """Verifies Hungarian matching enforces 1-to-1 assignment when multiple candidates compete for one buried track."""
        gallery = ReidGallery(cosine_thresh=0.60)
        v1 = np.array([1.0, 0.0, 0.0], dtype=np.float32)
        gallery.bury(final_id=42, embeds=v1)

        # Both candidates are close to v1, but c_better is closer (sim 0.99 vs 0.80)
        c_better = np.array([0.99, 0.14, 0.0], dtype=np.float32)
        c_worse = np.array([0.80, 0.60, 0.0], dtype=np.float32)
        cands = np.stack([c_worse, c_better])

        matches = gallery.match_newborns(cands)

        # Hungarian algorithm globally pairs c_better with 42, c_worse gets None
        assert matches[1] == 42
        assert matches[0] is None
        assert gallery.bank_size == 0

    def test_gallery_empty_inputs_handling(self):
        """Verifies match_newborns with empty gallery or empty candidates."""
        gallery = ReidGallery()

        # Empty candidates
        assert gallery.match_newborns(np.empty((0, 32))) == []
        assert gallery.match_newborns(None) == []  # type: ignore

        # Candidates against empty gallery
        cands = np.random.randn(3, 32).astype(np.float32)
        assert gallery.match_newborns(cands) == [None, None, None]

    def test_gallery_clear(self):
        """Verifies clear() purges all bank records."""
        gallery = ReidGallery()
        gallery.bury(1, np.ones(10))
        gallery.bury(2, np.ones(10))
        assert gallery.bank_size == 2
        gallery.clear()
        assert gallery.bank_size == 0
        assert gallery.get_lost_ids() == []


# ==============================================================================
# 3. Unit Tests: TemporalConfirmationGate
# ==============================================================================


class TestTemporalConfirmationGate:
    """Unit tests for TemporalConfirmationGate: K-of-W sliding window confirmation,
    transient reflection / flicker suppression, and stale memory eviction.
    """

    def test_sliding_window_persistence_k_of_w(self):
        """Verifies a damage track is confirmed exactly on reaching min_hits within window_size."""
        gate = TemporalConfirmationGate(min_hits=3, window_size=5)

        # Frame 1: hit 1 -> Not confirmed
        res1 = gate.update(frame_idx=1, active_track_ids=[10])
        assert res1 == set()
        assert not gate.is_confirmed(10)
        assert gate.get_hit_count_in_window(10) == 1
        assert gate.get_total_hits(10) == 1

        # Frame 2: hit 2 -> Not confirmed
        res2 = gate.update(frame_idx=2, active_track_ids=[10])
        assert res2 == set()
        assert not gate.is_confirmed(10)
        assert gate.get_hit_count_in_window(10) == 2
        assert gate.get_total_hits(10) == 2

        # Frame 3: hit 3 -> Newly confirmed!
        res3 = gate.update(frame_idx=3, active_track_ids=[10])
        assert res3 == {10}
        assert gate.is_confirmed(10)
        assert gate.get_confirmed_ids() == {10}
        assert gate.get_hit_count_in_window(10) == 3
        assert gate.get_total_hits(10) == 3

        # Frame 4: hit 4 -> Remains confirmed, newly_confirmed is empty
        res4 = gate.update(frame_idx=4, active_track_ids=[10])
        assert res4 == set()
        assert gate.is_confirmed(10)
        assert gate.get_total_hits(10) == 4

    def test_specular_reflection_flicker_suppression(self):
        """Verifies 1-frame and 2-frame specular glints/flickers are NEVER confirmed."""
        gate = TemporalConfirmationGate(min_hits=3, window_size=10)

        # Frame 1: Real damage (ID 1) starts
        gate.update(frame_idx=1, active_track_ids=[1])

        # Frame 2: Real damage (ID 1) continues; Specular Glint A (ID 99) appears for 1 frame
        gate.update(frame_idx=2, active_track_ids=[1, 99])

        # Frame 3: Real damage (ID 1) continues; Glint A (99) is GONE
        newly_conf = gate.update(frame_idx=3, active_track_ids=[1])
        assert newly_conf == {1}  # ID 1 reached 3 hits!

        # Frames 4-5: Specular Flicker B (ID 88) appears for only 2 consecutive frames
        gate.update(frame_idx=4, active_track_ids=[1, 88])
        gate.update(frame_idx=5, active_track_ids=[1, 88])

        # Frame 6: Only Real damage (ID 1) remains
        gate.update(frame_idx=6, active_track_ids=[1])

        # Final assertions:
        # Real damage ID 1 is confirmed
        assert gate.is_confirmed(1) is True

        # Specular Glint A (ID 99, 1 hit) is NOT confirmed
        assert gate.is_confirmed(99) is False
        assert gate.get_total_hits(99) == 1

        # Specular Flicker B (ID 88, 2 hits) is NOT confirmed
        assert gate.is_confirmed(88) is False
        assert gate.get_total_hits(88) == 2

        # Confirmed IDs set contains ONLY genuine persistent damage
        assert gate.get_confirmed_ids() == {1}

    def test_sliding_window_expiration_prevents_slow_accumulation(self):
        """Verifies hits spaced further than window_size expire and do not trigger confirmation."""
        gate = TemporalConfirmationGate(min_hits=3, window_size=4)

        # Frame 1: hit 1
        gate.update(frame_idx=1, active_track_ids=[55])
        assert gate.get_hit_count_in_window(55) == 1

        # Frames 2, 3, 4: no detection
        gate.update(frame_idx=2, active_track_ids=[])
        gate.update(frame_idx=3, active_track_ids=[])
        gate.update(frame_idx=4, active_track_ids=[])

        # Frame 5: hit 2, but frame 1 expired from window [2..5]
        gate.update(frame_idx=5, active_track_ids=[55])
        assert gate.get_hit_count_in_window(55) == 1  # only frame 5 remains

        # Frames 6, 7, 8: no detection
        gate.update(frame_idx=6, active_track_ids=[])
        gate.update(frame_idx=7, active_track_ids=[])
        gate.update(frame_idx=8, active_track_ids=[])

        # Frame 9: hit 3 lifetime, but frame 5 expired from window [6..9]
        gate.update(frame_idx=9, active_track_ids=[55])
        assert gate.get_hit_count_in_window(55) == 1

        # Track 55 had 3 lifetime hits, but never >= 3 within any 4-frame window
        assert gate.get_total_hits(55) == 3
        assert not gate.is_confirmed(55)
        assert gate.get_confirmed_ids() == set()

    def test_inactive_memory_cleanup(self):
        """Verifies unconfirmed tracks inactive for > max_inactive_frames are purged from memory."""
        gate = TemporalConfirmationGate(min_hits=3, window_size=5, max_inactive_frames=5)

        # Unconfirmed track 77 seen at frame 1
        gate.update(frame_idx=1, active_track_ids=[77])
        assert 77 in gate._window_history

        # Advance 6 frames without track 77 (inactive gap = 7 - 1 = 6 > 5)
        gate.update(frame_idx=7, active_track_ids=[])

        # Track 77 was unconfirmed, so its internal histories are purged
        assert 77 not in gate._window_history
        assert 77 not in gate._last_seen_frame
        assert 77 not in gate._total_hits

    def test_gate_clear(self):
        """Verifies clear() wipes all confirmed and history state."""
        gate = TemporalConfirmationGate(min_hits=2, window_size=5)
        gate.update(1, [1])
        gate.update(2, [1])
        assert gate.is_confirmed(1)

        gate.clear()
        assert not gate.is_confirmed(1)
        assert gate.get_confirmed_ids() == set()
        assert gate.get_total_hits(1) == 0


# ==============================================================================
# 4. Integration Tests: OcclusionReIDTracker
# ==============================================================================


class TestOcclusionReIDTrackerMock:
    """Isolated integration tests for OcclusionReIDTracker tracking logic,
    Hungarian newborn association, ID switch reduction, and state transitions.
    """

    def test_tracker_initialization(self):
        """Verifies tracker initialization with custom parameters without weights."""
        tracker = OcclusionReIDTracker(
            yolo_model=None,
            cosine_thresh=0.65,
            gallery_max_gap=120,
            temporal_min_hits=4,
            temporal_window_size=25,
            device="cpu",
        )
        assert tracker.gallery.cosine_thresh == 0.65
        assert tracker.gallery.max_gap == 120
        assert tracker.temporal_gate.min_hits == 4
        assert tracker.temporal_gate.window_size == 25
        assert tracker.device == "cpu"

    def test_tracker_id_switch_reduction_synthetic_lifecycle(self):
        """Simulates detector output across frames where damage disappears due to occlusion
        and reappears with a NEW raw ByteTrack ID, verifying Re-ID restores the historic ID.
        """
        tracker = OcclusionReIDTracker(
            yolo_model=None,
            cosine_thresh=0.60,
            gallery_max_gap=10,
            temporal_min_hits=3,
            temporal_window_size=10,
        )

        dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)

        # Consistent feature embedding representing front-bumper scratch
        scratch_emb = np.array([0.9, 0.1, 0.0, 0.0], dtype=np.float32)
        scratch_emb /= np.linalg.norm(scratch_emb)

        # Frame 1: ByteTrack spawns raw ID 1
        tracks_f1 = tracker._associate_and_reid(
            frame_bgr=dummy_img,
            frame_idx=1,
            boxes_xyxy=np.array([[20, 20, 80, 80]]),
            confs=np.array([0.85]),
            cls_ids=np.array([1]),
            raw_ids=[1],
            polygons=[None],
            embeds=np.expand_dims(scratch_emb, 0),
        )
        assert len(tracks_f1) == 1
        assert tracks_f1[0].final_id == 1
        assert tracks_f1[0].raw_track_id == 1
        assert not tracks_f1[0].is_confirmed  # hit 1

        # Frame 2: ByteTrack tracks raw ID 1
        tracks_f2 = tracker._associate_and_reid(
            frame_bgr=dummy_img,
            frame_idx=2,
            boxes_xyxy=np.array([[22, 22, 82, 82]]),
            confs=np.array([0.88]),
            cls_ids=np.array([1]),
            raw_ids=[1],
            polygons=[None],
            embeds=np.expand_dims(scratch_emb, 0),
        )
        assert tracks_f2[0].final_id == 1
        assert not tracks_f2[0].is_confirmed  # hit 2

        # Frame 3: OCCLUSION! Empty frame, ID 1 is lost and buried in gallery
        tracker._handle_empty_frame(frame_idx=3)
        assert tracker.gallery.bank_size == 1
        assert tracker.gallery.get_lost_ids() == [1]

        # Frame 4: Occlusion continues
        tracker._handle_empty_frame(frame_idx=4)
        assert tracker.gallery.bank_size == 1

        # Frame 5: Vehicle emerges from occlusion. ByteTrack spawns NEW raw ID 5!
        # The damage has the same appearance embedding (scratch_emb)
        tracks_f5 = tracker._associate_and_reid(
            frame_bgr=dummy_img,
            frame_idx=5,
            boxes_xyxy=np.array([[25, 25, 85, 85]]),
            confs=np.array([0.90]),
            cls_ids=np.array([1]),
            raw_ids=[5],  # NEW ByteTrack raw ID!
            polygons=[None],
            embeds=np.expand_dims(scratch_emb, 0),
        )

        assert len(tracks_f5) == 1
        # KEY ASSERTION: Re-ID successfully mapped newborn raw ID 5 back to historic final_id 1!
        assert tracks_f5[0].final_id == 1
        assert tracks_f5[0].raw_track_id == 5
        # Hit 3 within window [1..5] -> Confirmed!
        assert tracks_f5[0].is_confirmed is True

        # Verify summary stats
        assert len(tracker._all_raw_ids_seen) == 2  # raw IDs 1 and 5
        assert len(tracker._all_final_ids_seen) == 1  # unified final ID 1
        # ID switch reduction: (2 - 1) / 2 = 50.0%
        raw_count = len(tracker._all_raw_ids_seen)
        final_count = len(tracker._all_final_ids_seen)
        reduction = (raw_count - final_count) / float(raw_count) * 100.0
        assert reduction == 50.0

        # Verify TrackedDamageSummary integrity
        summary = tracker._track_summaries[1]
        assert summary.final_id == 1
        assert summary.total_detections == 3
        assert summary.is_confirmed is True
        assert summary.best_confidence == 0.90
        assert summary.first_frame_idx == 1
        assert summary.last_frame_idx == 5
        assert len(summary.trajectory_bboxes) == 3

    def test_tracker_empty_frame_handling(self):
        """Verifies empty frame cleans up active tracks and ages gallery."""
        tracker = OcclusionReIDTracker(yolo_model=None)
        tracker._active_final_ids_prev = {10, 20}
        tracker._appearance_history[10] = [np.random.randn(32)]
        tracker._appearance_history[20] = [np.random.randn(32)]

        tracker._handle_empty_frame(frame_idx=1)

        assert len(tracker._active_final_ids_prev) == 0
        assert tracker.gallery.bank_size == 2
        assert set(tracker.gallery.get_lost_ids()) == {10, 20}

    def test_tracker_missing_video_raises_file_not_found(self):
        """Verifies track_video raises FileNotFoundError when video path does not exist."""
        tracker = OcclusionReIDTracker(yolo_model=None)
        with pytest.raises(FileNotFoundError, match="Video file not found"):
            tracker.track_video("non_existent_walkaround.mp4")

    def test_tracker_reset_clears_all_structures(self):
        """Verifies reset() restores clean slate."""
        tracker = OcclusionReIDTracker(yolo_model=None)
        tracker._all_raw_ids_seen.add(1)
        tracker._all_final_ids_seen.add(1)
        tracker._raw_to_final_id[1] = 1
        tracker.gallery.bury(1, np.ones(10))
        tracker.temporal_gate.update(1, [1])

        tracker.reset()

        assert len(tracker._all_raw_ids_seen) == 0
        assert len(tracker._all_final_ids_seen) == 0
        assert len(tracker._raw_to_final_id) == 0
        assert tracker.gallery.bank_size == 0
        assert tracker.temporal_gate.get_confirmed_ids() == set()


# ==============================================================================
# 5. Integration Tests: Real Weights & Video Cohorts
# ==============================================================================


@pytest.fixture(scope="module")
def real_tracker() -> OcclusionReIDTracker:
    """Loads tracker with real YOLO damage segmentation weights."""
    return OcclusionReIDTracker(
        weights_path=CARDD_WEIGHTS,
        conf_threshold=0.10,
        cosine_thresh=0.60,
        temporal_min_hits=3,
        temporal_window_size=20,
    )


@pytest.mark.skipif(not CARDD_WEIGHTS.exists(), reason="cardd-yolov8s-seg.pt weights not found")
class TestOcclusionReIDTrackerRealWeights:
    """End-to-end integration tests using cardd-yolov8s-seg.pt detector on real
    vehicle inspection video assets from test_assets/videos/.
    """

    def test_frame_tracking_and_feature_extraction(self, real_tracker: OcclusionReIDTracker):
        """Verifies single-frame tracking extracts valid TrackedDamage instances with embeddings."""
        assert SIMPLE_VIDEO_CAR001.exists(), f"Video missing: {SIMPLE_VIDEO_CAR001}"
        cap = cv2.VideoCapture(str(SIMPLE_VIDEO_CAR001))
        ret, frame = cap.read()
        cap.release()
        assert ret is True and frame is not None

        damages: List[TrackedDamage] = real_tracker.track_frame(frame, frame_idx=1)

        # In frame 1 of car_001, scratch damage is detected
        assert len(damages) >= 1
        first_dmg = damages[0]
        assert isinstance(first_dmg, TrackedDamage)
        assert first_dmg.final_id is not None
        assert first_dmg.raw_track_id is not None
        assert first_dmg.confidence >= 0.10
        assert first_dmg.class_name in ("scratch", "dent", "crack", "glass_shatter", "lamp_broken", "tire_flat")
        assert len(first_dmg.bbox_xyxy) == 4
        # At frame 1 (hit 1), track is not yet confirmed (min_hits=3)
        assert first_dmg.is_confirmed is False
        # Feature embedding is extracted and unit normalized
        assert first_dmg.embedding is not None
        assert isinstance(first_dmg.embedding, np.ndarray)
        np.testing.assert_allclose(np.linalg.norm(first_dmg.embedding), 1.0, atol=1e-5)

    def test_video_tracking_simple_cohort_car_001(self, real_tracker: OcclusionReIDTracker):
        """Tests full tracking on simple walkaround video (car_001.mp4).
        Verifies ID switch reduction, temporal confirmation, and summary output.
        """
        assert SIMPLE_VIDEO_CAR001.exists()

        result: VideoTrackingResult = real_tracker.track_video(
            video_path=SIMPLE_VIDEO_CAR001,
            max_frames=30,
            conf=0.10,
        )

        assert isinstance(result, VideoTrackingResult)
        assert result.total_frames == 30
        assert result.raw_unique_ids_count >= 1
        assert result.reid_unique_ids_count >= 1

        # Re-ID reduces or maintains unique IDs compared to raw tracker
        assert result.reid_unique_ids_count <= result.raw_unique_ids_count
        assert result.id_switch_reduction_pct >= 0.0

        # Confirmed tracks verification
        assert result.confirmed_unique_ids_count == len(result.confirmed_tracks)
        assert len(result.confirmed_tracks) >= 1

        for track in result.confirmed_tracks:
            assert isinstance(track, TrackedDamageSummary)
            assert track.is_confirmed is True
            assert track.total_detections >= 3  # reached min_hits
            assert track.best_confidence >= 0.10
            assert track.first_frame_idx <= track.last_frame_idx
            assert len(track.trajectory_bboxes) == track.total_detections
            assert track.best_frame_img is not None
            assert track.best_frame_img.shape == (640, 360, 3) or track.best_frame_img.ndim == 3

    def test_video_tracking_difficult_cohort_and_flicker_suppression(
        self, real_tracker: OcclusionReIDTracker
    ):
        """Tests tracking on difficult scenario video (scenario_01_damaged_collision.mp4).
        Verifies that transient specular reflections / flickers are filtered out
        (confirmed_unique_ids <= reid_unique_ids).
        """
        assert DIFFICULT_VIDEO_COLLISION.exists()

        result: VideoTrackingResult = real_tracker.track_video(
            video_path=DIFFICULT_VIDEO_COLLISION,
            max_frames=30,
            conf=0.10,
        )

        assert result.total_frames == 30
        assert result.raw_unique_ids_count >= 1
        assert result.reid_unique_ids_count <= result.raw_unique_ids_count

        # Specular reflection / transient flicker suppression:
        # confirmed_unique_ids_count must be <= reid_unique_ids_count
        assert result.confirmed_unique_ids_count <= result.reid_unique_ids_count
        assert len(result.confirmed_tracks) == result.confirmed_unique_ids_count
        assert result.confirmed_unique_ids_count >= 1

    def test_video_tracking_rtdetr_vd_sequence_aveo(self, real_tracker: OcclusionReIDTracker):
        """Tests tracking on RTDETR-VD benchmark dataset sequence (aveo.mp4)."""
        assert RTDETR_VD_AVEO.exists()

        result: VideoTrackingResult = real_tracker.track_video(
            video_path=RTDETR_VD_AVEO,
            max_frames=30,
            conf=0.10,
        )

        assert isinstance(result, VideoTrackingResult)
        assert result.total_frames == 30
        assert result.video_path == str(RTDETR_VD_AVEO)
