import os
_ffmpeg_dir = r"C:\Users\Hp\AppData\Local\ffmpeg\bin"
if os.path.exists(_ffmpeg_dir) and _ffmpeg_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] = f"{_ffmpeg_dir};{os.environ.get('PATH', '')}"

"""
tests/dual_mask_segmentation/conftest.py
Hermetic Fixtures, Synthetic Image Generators, and Model Mocks for Stage 2.
"""
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from unittest.mock import AsyncMock
import uuid

import cv2
import numpy as np
import pytest
import pytest_asyncio
from shapely.geometry import Polygon, box

from app.domain.dual_mask_segmentation.config import Stage2Settings
from app.domain.dual_mask_segmentation.schemas import (
    FrameDualPredictions,
    GroupedPartCandidate,
    OEMPartCatalogueRecord,
    PartDamageIntersection,
    RawMaskPrediction,
)
from app.domain.dual_mask_segmentation.taxonomy import (
    CARDD_CLASS_MAP,
    CARPARTS_CLASS_MAP,
    select_primary_damage_class,
)
from tests.in_memory_db import (
    FakeAsyncSession,
    in_memory_db,
    patch_in_memory_db,
)

# Apply in-memory patches for repositories and RedisManager
patch_in_memory_db()


@pytest_asyncio.fixture(autouse=True)
async def reset_in_memory_state():
    """Guarantees pristine in-memory DB and lock state for each test execution."""
    in_memory_db.reset()


@pytest_asyncio.fixture
async def db_session() -> FakeAsyncSession:
    """Yields hermetic FakeAsyncSession resolving against in_memory_db."""
    return FakeAsyncSession()


@pytest_asyncio.fixture
async def redis_mock() -> AsyncMock:
    """Provides a mocked async Redis client with publish interception."""
    client = AsyncMock()
    client.publish = AsyncMock(return_value=1)
    return client


@pytest.fixture
def stage2_settings(tmp_path: Path) -> Stage2Settings:
    """Provides isolated Stage2Settings with temp output directory."""
    return Stage2Settings(
        som_output_dir=tmp_path / "autosettle_som",
        panel_border_margin_px=15,
        max_border_vertex_contact_ratio=0.05,
        min_persistence_frames=2,
    )


@pytest.fixture
def gpu_semaphore() -> asyncio.Semaphore:
    """Provides asyncio GPU concurrency lock."""
    return asyncio.Semaphore(1)


@pytest.fixture
def synthetic_frame_1080p() -> np.ndarray:
    """Generates a high-contrast 1920x1080 test frame with non-zero Laplacian sharpness."""
    img = np.zeros((1080, 1920, 3), dtype=np.uint8)
    # Background gradient
    for y in range(1080):
        img[y, :, 0] = int((y / 1080.0) * 180)
        img[y, :, 1] = int((1.0 - y / 1080.0) * 160)
        img[y, :, 2] = 200
    # Add contrast grid lines to produce Laplacian variance > 150
    for x in range(0, 1920, 60):
        cv2.line(img, (x, 0), (x, 1080), (30, 30, 30), 2)
    for y in range(0, 1080, 60):
        cv2.line(img, (0, y), (1920, y), (30, 30, 30), 2)
    return img


@pytest.fixture
def synthetic_frame_720p() -> np.ndarray:
    """Generates a high-contrast 1280x720 test frame with non-zero Laplacian sharpness."""
    img = np.zeros((720, 1280, 3), dtype=np.uint8)
    for y in range(720):
        img[y, :, 0] = 120
        img[y, :, 1] = int((y / 720.0) * 200)
        img[y, :, 2] = 180
    for x in range(0, 1280, 40):
        cv2.line(img, (x, 0), (x, 720), (40, 40, 40), 1)
    return img


@pytest.fixture
def temp_keyframe_files(tmp_path: Path, synthetic_frame_1080p: np.ndarray) -> Dict[str, Path]:
    """Saves synthetic 1080p keyframes to disk and returns mapping."""
    kf_dir = tmp_path / "keyframes"
    kf_dir.mkdir(parents=True, exist_ok=True)

    kf_map: Dict[str, Path] = {}
    for i in range(1, 4):
        kf_key = f"kf_{i:02d}"
        path = kf_dir / f"frame_{i:04d}.jpg"
        frame_copy = synthetic_frame_1080p.copy()
        cv2.putText(
            frame_copy,
            f"KEYFRAME {i}",
            (100, 100),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.5,
            (255, 255, 255),
            2,
        )
        cv2.imwrite(str(path), frame_copy, [cv2.IMWRITE_JPEG_QUALITY, 95])
        kf_map[kf_key] = path

    return kf_map


# ---------------------------------------------------------------------------
# Synthetic Prediction Factory Helpers
# ---------------------------------------------------------------------------

def make_box_polygon_coords(x1: float, y1: float, x2: float, y2: float) -> np.ndarray:
    """Returns (4, 2) numpy array of bounding polygon vertices."""
    return np.array(
        [[x1, y1], [x2, y1], [x2, y2], [x1, y2]],
        dtype=np.float32,
    )


def make_raw_part_prediction(
    class_name: str,
    confidence: float,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    polygon_coords: Optional[np.ndarray] = None,
) -> RawMaskPrediction:
    """Builds a RawMaskPrediction for a Carparts-Seg vehicle part."""
    # Find class id from CARPARTS_CLASS_MAP
    class_id = next((k for k, v in CARPARTS_CLASS_MAP.items() if v == class_name), 0)
    if polygon_coords is None:
        polygon_coords = make_box_polygon_coords(float(x1), float(y1), float(x2), float(y2))
    return RawMaskPrediction(
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        bbox_xyxy=(x1, y1, x2, y2),
        polygon_xy_px=polygon_coords,
    )


def make_raw_damage_prediction(
    class_name: str,
    confidence: float,
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    polygon_coords: Optional[np.ndarray] = None,
) -> RawMaskPrediction:
    """Builds a RawMaskPrediction for a CarDD damage instance."""
    class_id = next((k for k, v in CARDD_CLASS_MAP.items() if v == class_name), 0)
    if polygon_coords is None:
        polygon_coords = make_box_polygon_coords(float(x1), float(y1), float(x2), float(y2))
    return RawMaskPrediction(
        class_id=class_id,
        class_name=class_name,
        confidence=confidence,
        bbox_xyxy=(x1, y1, x2, y2),
        polygon_xy_px=polygon_coords,
    )


def make_frame_predictions(
    keyframe_key: str,
    frame_path: Path,
    frame_index: int,
    width_px: int = 1920,
    height_px: int = 1080,
    laplacian_sharpness: float = 180.0,
    part_predictions: Optional[List[RawMaskPrediction]] = None,
    damage_predictions: Optional[List[RawMaskPrediction]] = None,
) -> FrameDualPredictions:
    """Constructs a FrameDualPredictions DTO for pipeline testing."""
    return FrameDualPredictions(
        keyframe_key=keyframe_key,
        frame_path=frame_path,
        frame_index=frame_index,
        width_px=width_px,
        height_px=height_px,
        laplacian_sharpness=laplacian_sharpness,
        part_predictions=part_predictions or [],
        damage_predictions=damage_predictions or [],
    )


def make_test_intersection(
    keyframe_key: str = "kf_01",
    frame_index: int = 1,
    part_class: str = "front_left_door",
    part_confidence: float = 0.92,
    part_box: Tuple[int, int, int, int] = (200, 200, 1200, 800),
    is_complete_panel: bool = True,
    border_contact_ratio: float = 0.0,
    damage_classes: Optional[List[str]] = None,
    damage_confidence: float = 0.88,
    dmg_box: Tuple[int, int, int, int] = (400, 400, 600, 550),
    width_px: int = 1920,
    height_px: int = 1080,
    sharpness: float = 180.0,
) -> PartDamageIntersection:
    """Builds a test PartDamageIntersection object with valid Shapely polygons."""
    dmg_classes = damage_classes or ["dent"]
    p_poly = box(*part_box)
    d_poly = box(*dmg_box)
    inter_poly = d_poly.intersection(p_poly)
    part_area = float(p_poly.area)
    inter_area = float(inter_poly.area)
    iop_ratio = inter_area / part_area if part_area > 0 else 0.0

    return PartDamageIntersection(
        keyframe_key=keyframe_key,
        frame_index=frame_index,
        width_px=width_px,
        height_px=height_px,
        laplacian_sharpness=sharpness,
        raw_part_class=part_class,
        resolved_part_key=part_class,
        part_confidence=part_confidence,
        part_bbox_xyxy=part_box,
        is_complete_panel=is_complete_panel,
        border_contact_ratio=border_contact_ratio,
        part_area_px=round(part_area, 2),
        union_damage_intersection_area_px=round(inter_area, 2),
        raw_iop_ratio=round(iop_ratio, 4),
        damage_classes=dmg_classes,
        primary_damage_class=select_primary_damage_class(dmg_classes),
        max_damage_confidence=round(damage_confidence, 4),
        part_polygon=p_poly,
        union_damage_polygon=inter_poly,
    )


def make_test_candidate(
    canonical_part_key: str = "front_left_door",
    damage_classes: Optional[List[str]] = None,
    final_iop_ratio: float = 0.084,
    iop_estimation_method: str = "UNCLIPPED_COMPLETE_PANEL",
    part_confidence: float = 0.92,
    damage_confidence: float = 0.88,
    persistence_frame_count: int = 2,
    intersection: Optional[PartDamageIntersection] = None,
) -> GroupedPartCandidate:
    """Constructs a test GroupedPartCandidate for testing downstream stages."""
    dmg_classes = damage_classes or ["dent"]
    inter = intersection or make_test_intersection(
        part_class=canonical_part_key,
        damage_classes=dmg_classes,
        damage_confidence=damage_confidence,
        part_confidence=part_confidence,
    )
    return GroupedPartCandidate(
        canonical_part_key=canonical_part_key,
        raw_detected_part_classes=[canonical_part_key],
        side_resolution_method="TRAJECTORY_PROPAGATED_LEFT",
        detected_damage_classes=dmg_classes,
        primary_damage_class=select_primary_damage_class(dmg_classes),
        final_iop_ratio=final_iop_ratio,
        iop_estimation_method=iop_estimation_method,
        zoom_clipped_frames_filtered=0,
        persistence_frame_count=persistence_frame_count,
        part_confidence=part_confidence,
        damage_confidence=damage_confidence,
        area_measurement_intersection=inter,
        vlm_closeup_intersection=inter,
    )


def make_creta_oem_catalogue_record(
    canonical_part_key: str = "front_left_door",
) -> OEMPartCatalogueRecord:
    """Builds an OEM catalogue record matching Hyundai Creta specs from in_memory_db."""
    from tests.in_memory_db import HYUNDAI_CRETA_PARTS

    matched = next((p for p in HYUNDAI_CRETA_PARTS if p[0] == canonical_part_key), None)
    if not matched:
        # Fallback default
        return OEMPartCatalogueRecord(
            canonical_part_key=canonical_part_key,
            display_part_name="Test Part",
            oem_part_number="TEST-0001",
            part_material="metal",
            depreciation_rate_non_zero_dep=0.0,
            oem_part_cost_inr=11500.0,
            rr_labour_inr=950.0,
            denting_base_labour_inr=1400.0,
            full_panel_paint_inr=4200.0,
            pdr_or_polish_flat_inr=850.0,
            is_repairable=True,
            is_safety_critical=False,
        )

    key, name, pnum, mat, cost, rr, dent, paint, pdr, rep, safe = matched
    return OEMPartCatalogueRecord(
        canonical_part_key=key,
        display_part_name=name,
        oem_part_number=pnum,
        part_material=mat,
        depreciation_rate_non_zero_dep=0.0,
        oem_part_cost_inr=float(cost),
        rr_labour_inr=float(rr),
        denting_base_labour_inr=float(dent),
        full_panel_paint_inr=float(paint),
        pdr_or_polish_flat_inr=float(pdr),
        is_repairable=rep,
        is_safety_critical=safe,
    )
