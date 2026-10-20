from typing import Dict, FrozenSet, Tuple

# Official 23-class Ultralytics Carparts-Seg mapping (Class 18 'object' is ignored)
CARPARTS_CLASS_MAP: Dict[int, str] = {
    0: "back_bumper",
    1: "back_door",
    2: "back_glass",
    3: "back_left_door",
    4: "back_left_light",
    5: "back_light",
    6: "back_right_door",
    7: "back_right_light",
    8: "front_bumper",
    9: "front_door",
    10: "front_glass",
    11: "front_left_door",
    12: "front_left_light",
    13: "front_light",
    14: "front_right_door",
    15: "front_right_light",
    16: "hood",
    17: "left_mirror",
    18: "object",  # Explicitly filtered out
    19: "right_mirror",
    20: "tailgate",
    21: "trunk",
    22: "wheel",
}

IGNORED_PART_CLASSES: FrozenSet[str] = frozenset({"object"})

LEFT_SIDE_PARTS: FrozenSet[str] = frozenset({
    "front_left_door",
    "back_left_door",
    "front_left_light",
    "back_left_light",
    "left_mirror",
})

RIGHT_SIDE_PARTS: FrozenSet[str] = frozenset({
    "front_right_door",
    "back_right_door",
    "front_right_light",
    "back_right_light",
    "right_mirror",
})

SAFETY_CRITICAL_PARTS: FrozenSet[str] = frozenset({
    "front_glass",
    "back_glass",
    "wheel",
})

# Maps (generic_part_key, side) -> explicit canonical_part_key
GENERIC_TO_SIDED_PART_MAP: Dict[Tuple[str, str], str] = {
    ("front_door", "LEFT"): "front_left_door",
    ("front_door", "RIGHT"): "front_right_door",
    ("back_door", "LEFT"): "back_left_door",
    ("back_door", "RIGHT"): "back_right_door",
    ("front_light", "LEFT"): "front_left_light",
    ("front_light", "RIGHT"): "front_right_light",
    ("back_light", "LEFT"): "back_left_light",
    ("back_light", "RIGHT"): "back_right_light",
}

# Official 6-class CarDD mapping
CARDD_CLASS_MAP: Dict[int, str] = {
    0: "dent",
    1: "scratch",
    2: "crack",
    3: "glass_shatter",
    4: "lamp_broken",
    5: "tire_flat",
}

LINEAR_DAMAGE_CLASSES: FrozenSet[str] = frozenset({"scratch", "crack"})
SAFETY_CRITICAL_DAMAGE_CLASSES: FrozenSet[str] = frozenset({"glass_shatter", "tire_flat"})

# Lower rank number = Higher actuarial priority when multiple damage classes hit the same part
DAMAGE_SEVERITY_PRIORITY: Dict[str, int] = {
    "tire_flat": 1,
    "glass_shatter": 2,
    "lamp_broken": 3,
    "crack": 4,
    "dent": 5,
    "scratch": 6,
}


def select_primary_damage_class(damage_classes: list[str]) -> str:
    """Returns the highest-severity damage class from a list of detected classes."""
    if not damage_classes:
        return "dent"
    return min(damage_classes, key=lambda c: DAMAGE_SEVERITY_PRIORITY.get(c, 99))


def validate_model_taxonomy(
    model: object,
    expected_class_map: Dict[int, str],
    model_role: str = "Model",
) -> None:
    """Validates that a YOLO model instance exposes the exact expected class count,
    indices, and label names.

    Inspects `model.names` (standard Ultralytics attribute).
    Raises Stage2ModelCompatibilityError if:
    1. The model does not expose a valid `names` attribute.
    2. The class count != len(expected_class_map).
    3. Any expected class ID is missing or maps to an unexpected label.
    """
    from app.domain.dual_mask_segmentation.exceptions import Stage2ModelCompatibilityError

    if not hasattr(model, "names") or getattr(model, "names") is None:
        raise Stage2ModelCompatibilityError(
            f"{model_role} validation failed: model object lacks a valid 'names' attribute.",
            details={"model_role": model_role},
        )

    raw_names = getattr(model, "names")
    if isinstance(raw_names, dict):
        try:
            model_names = {int(k): str(v) for k, v in raw_names.items()}
        except (ValueError, TypeError) as err:
            raise Stage2ModelCompatibilityError(
                f"{model_role} validation failed: 'names' dictionary contains non-integer keys ({err}).",
                details={"model_role": model_role, "error": str(err)},
            ) from err
    elif isinstance(raw_names, (list, tuple)):
        model_names = {i: str(v) for i, v in enumerate(raw_names)}
    else:
        raise Stage2ModelCompatibilityError(
            f"{model_role} validation failed: 'names' is neither a dict nor a list/tuple ({type(raw_names)}).",
            details={"model_role": model_role},
        )

    expected_count = len(expected_class_map)
    actual_count = len(model_names)
    if actual_count != expected_count:
        raise Stage2ModelCompatibilityError(
            f"{model_role} class count mismatch: expected {expected_count} classes, "
            f"but model has {actual_count} classes. (Generic COCO or incompatible checkpoint detected).",
            details={
                "model_role": model_role,
                "expected_count": expected_count,
                "actual_count": actual_count,
            },
        )

    for cid, expected_label in expected_class_map.items():
        if cid not in model_names:
            raise Stage2ModelCompatibilityError(
                f"{model_role} missing expected class ID {cid} ('{expected_label}').",
                details={
                    "model_role": model_role,
                    "missing_cid": cid,
                    "expected_label": expected_label,
                },
            )
        actual_label = model_names[cid].strip()
        if actual_label.lower() != expected_label.lower():
            raise Stage2ModelCompatibilityError(
                f"{model_role} taxonomy mismatch at class ID {cid}: expected '{expected_label}', got '{actual_label}'.",
                details={
                    "model_role": model_role,
                    "cid": cid,
                    "expected_label": expected_label,
                    "actual_label": actual_label,
                },
            )
