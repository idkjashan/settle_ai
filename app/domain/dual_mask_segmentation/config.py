from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Stage2Settings(BaseSettings):
    """Frozen operational thresholds and paths for Stage 2 Dual-Mask Segmentation."""
    model_config = SettingsConfigDict(env_prefix="STAGE2_", frozen=True)

    # Model paths & inference parameters
    carparts_model_path: str = Field(default="weights/yolo11m-carparts-seg.pt")
    cardd_model_path: str = Field(default="weights/yolo11m-cardd-seg.pt")
    gpu_batch_size: int = Field(default=8)
    inference_imgsz: int = Field(default=640)
    use_fp16_half: bool = Field(default=True)

    # Detection confidence thresholds
    part_min_confidence: float = Field(default=0.45)
    damage_min_confidence_global: float = Field(default=0.35)
    high_conf_escalation_floor: float = Field(default=0.45)

    # Shapely geometry & spillover thresholds
    min_polygon_area_px: float = Field(default=50.0)
    min_intersection_area_px: float = Field(default=250.0)
    spillover_min_ratio: float = Field(default=0.10)
    spillover_override_area_px: float = Field(default=2500.0)
    iop_floor_linear: float = Field(default=0.003)   # 0.3% for scratch, crack
    iop_floor_areal: float = Field(default=0.008)    # 0.8% for dent, lamp_broken, glass_shatter, tire_flat

    # Zoom Anti-Inflation & Completeness parameters
    panel_border_margin_px: int = Field(default=15)
    max_border_vertex_contact_ratio: float = Field(default=0.05)
    clipped_panel_iop_scale_factor: float = Field(default=0.35)
    clipped_panel_max_iop_cap: float = Field(default=0.25)

    # Multi-frame persistence & trajectory resolution
    min_persistence_frames: int = Field(default=2)
    single_frame_override_part_conf: float = Field(default=0.80)
    single_frame_override_damage_conf: float = Field(default=0.75)
    trajectory_side_window_radius: int = Field(default=4)

    # Set-of-Marks (SoM) rendering
    som_output_dir: Path = Field(default=Path("/tmp/autosettle_som"))
    som_contour_dilation_px: int = Field(default=15)
    som_crop_padding_ratio: float = Field(default=0.35)
    som_min_padding_px: int = Field(default=120)
    svg_simplify_tolerance_px: float = Field(default=2.0)
