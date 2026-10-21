from typing import Dict, FrozenSet, Sequence, Tuple, Union

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

# 33-class AutoInspect Carparts mapping (native sided parts)
CARPARTS_33_CLASS_MAP: Dict[int, str] = {
    0: "back-bumper",
    1: "back-windshield",
    2: "front-bumper",
    3: "grille",
    4: "hood",
    5: "left_back-door",
    6: "left_back-wheel",
    7: "left_back-window",
    8: "left_fender",
    9: "left_front-door",
    10: "left_front-wheel",
    11: "left_front-window",
    12: "left_headlight",
    13: "left_mirror",
    14: "left_quarter-panel",
    15: "left_rocker-panel",
    16: "left_tail-light",
    17: "license-plate",
    18: "right_back-door",
    19: "right_back-wheel",
    20: "right_back-window",
    21: "right_fender",
    22: "right_front-door",
    23: "right_front-wheel",
    24: "right_front-window",
    25: "right_headlight",
    26: "right_mirror",
    27: "right_quarter-panel",
    28: "right_rocker-panel",
    29: "right_tail-light",
    30: "roof",
    31: "trunk",
    32: "windshield",
}

# Maps 33-class AutoInspect labels to canonical 22 catalogue keys
CARPARTS_33_TO_CANONICAL: Dict[str, str] = {
    "back-bumper": "back_bumper",
    "back-windshield": "back_glass",
    "front-bumper": "front_bumper",
    "grille": "front_bumper",
    "hood": "hood",
    "left_back-door": "back_left_door",
    "left_back-wheel": "wheel",
    "left_back-window": "back_glass",
    "left_fender": "front_left_door",
    "left_front-door": "front_left_door",
    "left_front-wheel": "wheel",
    "left_front-window": "front_glass",
    "left_headlight": "front_left_light",
    "left_mirror": "left_mirror",
    "left_quarter-panel": "back_left_door",
    "left_rocker-panel": "front_left_door",
    "left_tail-light": "back_left_light",
    "license-plate": "object",  # Filtered out by IGNORED_PART_CLASSES
    "right_back-door": "back_right_door",
    "right_back-wheel": "wheel",
    "right_back-window": "back_glass",
    "right_fender": "front_right_door",
    "right_front-door": "front_right_door",
    "right_front-wheel": "wheel",
    "right_front-window": "front_glass",
    "right_headlight": "front_right_light",
    "right_mirror": "right_mirror",
    "right_quarter-panel": "back_right_door",
    "right_rocker-panel": "front_right_door",
    "right_tail-light": "back_right_light",
    "roof": "hood",
    "trunk": "trunk",
    "windshield": "front_glass",
}

CARPARTS_ALLOWED_TAXONOMIES: Tuple[Dict[int, str], ...] = (
    CARPARTS_CLASS_MAP,
    CARPARTS_33_CLASS_MAP,
)

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
    expected_class_map: Union[Dict[int, str], Sequence[Dict[int, str]]],
    model_role: str = "Model",
) -> Dict[int, str]:
    """Validates that a YOLO model instance exposes the exact expected class count,
    indices, and label names.

    Supports either a single expected taxonomy dict or a sequence of valid candidate
    taxonomies (e.g. 23-class or 33-class Carparts models).
    Returns the matched taxonomy Dict[int, str].

    Inspects `model.names` (standard Ultralytics attribute).
    Raises Stage2ModelCompatibilityError if:
    1. The model does not expose a valid `names` attribute.
    2. None of the candidate class maps match in length and labels.
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

    candidates: Sequence[Dict[int, str]]
    if isinstance(expected_class_map, dict):
        candidates = [expected_class_map]
    else:
        candidates = list(expected_class_map)

    last_error_msg = ""
    for candidate in candidates:
        expected_count = len(candidate)
        actual_count = len(model_names)
        if actual_count != expected_count:
            last_error_msg = (
                f"{model_role} class count mismatch: expected {expected_count} classes, "
                f"but model has {actual_count} classes."
            )
            continue

        matched = True
        for cid, expected_label in candidate.items():
            if cid not in model_names:
                last_error_msg = f"{model_role} missing expected class ID {cid} ('{expected_label}')."
                matched = False
                break
            actual_label = model_names[cid].strip()
            if actual_label.lower() != expected_label.lower():
                last_error_msg = (
                    f"{model_role} taxonomy mismatch at class ID {cid}: expected '{expected_label}', got '{actual_label}'."
                )
                matched = False
                break

        if matched:
            return candidate

    allowed_counts = [len(c) for c in candidates]
    raise Stage2ModelCompatibilityError(
        f"{model_role} validation failed against allowed taxonomies (expected {allowed_counts} classes, got {len(model_names)}). "
        f"{last_error_msg} (Generic COCO or incompatible checkpoint detected).",
        details={
            "model_role": model_role,
            "allowed_counts": allowed_counts,
            "actual_count": len(model_names),
            "last_error": last_error_msg,
        },
    )
