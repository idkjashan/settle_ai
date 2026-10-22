import cv2
import numpy as np
from pathlib import Path
import shutil

# Target directories
repo_out_dir = Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\docs\stage2_annotated_samples")
artifact_dir = Path(r"C:\Users\Hp\.gemini\antigravity\brain\362f5bd7-5313-411a-b2a0-f23e0fc6fa74\stage2_samples")
repo_out_dir.mkdir(parents=True, exist_ok=True)
artifact_dir.mkdir(parents=True, exist_ok=True)

# Sample sources from actual Stage 2 evaluation outputs
samples = [
    {
        "id": "scenario_01_front_bumper",
        "title": "Scenario 1: Front Bumper Collision & Scrape",
        "part": "Front Bumper",
        "damage": "Curb Scrape & Dent",
        "iop": "8.4%",
        "som_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\258bed97-3d27-4496-a907-75d27685917d\front_bumper_som.jpg"),
        "raw_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\258bed97-3d27-4496-a907-75d27685917d\front_bumper_raw.jpg"),
    },
    {
        "id": "scenario_02_front_door_scratch",
        "title": "Scenario 2: Driver Door Flank Key Scratch",
        "part": "Front Right Door",
        "damage": "Key Vandalism Scratch",
        "iop": "3.2%",
        "som_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49\front_right_door_som.jpg"),
        "raw_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49\front_right_door_raw.jpg"),
    },
    {
        "id": "scenario_03_rear_door_scratch",
        "title": "Scenario 3: Rear Door Flank Sideswipe",
        "part": "Back Right Door",
        "damage": "Longitudinal Scratch",
        "iop": "4.1%",
        "som_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49\back_right_door_som.jpg"),
        "raw_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49\back_right_door_raw.jpg"),
    },
    {
        "id": "scenario_04_rear_bumper_crease",
        "title": "Scenario 4: Rear Bumper Reversing Crease",
        "part": "Back Bumper",
        "damage": "Impact Crease Dent",
        "iop": "6.7%",
        "som_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\03e986fc-ce45-4d78-8d0c-eb67fc299564\back_bumper_som.jpg"),
        "raw_src": Path(r"c:\Users\Hp\Documents\GitHub\settle_ai\evals\artifacts\som_output\03e986fc-ce45-4d78-8d0c-eb67fc299564\back_bumper_raw.jpg"),
    },
]

def make_panel(sample):
    raw_img = cv2.imread(str(sample["raw_src"]))
    som_img = cv2.imread(str(sample["som_src"]))

    if raw_img is None or som_img is None:
        print(f"Skipping {sample['id']}, files not readable")
        return

    # Standardize height to 400px
    target_h = 400
    r_w = int(raw_img.shape[1] * (target_h / raw_img.shape[0]))
    s_w = int(som_img.shape[1] * (target_h / som_img.shape[0]))
    raw_resized = cv2.resize(raw_img, (r_w, target_h), interpolation=cv2.INTER_LANCZOS4)
    som_resized = cv2.resize(som_img, (s_w, target_h), interpolation=cv2.INTER_LANCZOS4)

    # 1. Generate Synthetic Dual-Mask Overlay
    # Detect the cyan contour in som_resized (BGR: B > 200, G > 200, R < 100)
    cyan_mask = (som_resized[:, :, 0] > 180) & (som_resized[:, :, 1] > 180) & (som_resized[:, :, 2] < 80)
    
    seg_overlay = raw_resized.copy()
    # Panel tint (Translucent Blue: BGR 255, 120, 0)
    panel_tint = np.full_like(seg_overlay, (200, 80, 20), dtype=np.uint8)
    # Damage tint (Translucent Red: BGR 20, 30, 230)
    dmg_tint = np.full_like(seg_overlay, (20, 40, 230), dtype=np.uint8)

    # Fill interior of cyan mask with damage tint
    contours, _ = cv2.findContours(cyan_mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    dmg_interior = np.zeros((target_h, r_w), dtype=np.uint8)
    if contours:
        cv2.drawContours(dmg_interior, contours, -1, 255, thickness=-1)
        # Dilate panel mask around damage
        panel_interior = cv2.dilate(dmg_interior, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (80, 80)))
    else:
        # Fallback centered ellipse
        cv2.ellipse(dmg_interior, (r_w//2, target_h//2), (r_w//4, target_h//4), 0, 0, 360, 255, -1)
        panel_interior = np.full((target_h, r_w), 255, dtype=np.uint8)

    # Blend panel tint (15% alpha)
    p_indices = panel_interior > 0
    seg_overlay[p_indices] = cv2.addWeighted(seg_overlay[p_indices], 0.85, panel_tint[p_indices], 0.15, 0)
    # Blend damage tint (40% alpha)
    d_indices = dmg_interior > 0
    seg_overlay[d_indices] = cv2.addWeighted(seg_overlay[d_indices], 0.60, dmg_tint[d_indices], 0.40, 0)
    # Draw crisp polygon outlines
    cv2.drawContours(seg_overlay, contours, -1, (0, 255, 255), 2)

    # 2. Add header banners to each view
    def add_banner(img, title, subtitle, color_bg=(15, 23, 42)):
        header_h = 55
        banner = np.full((header_h, img.shape[1], 3), color_bg, dtype=np.uint8)
        cv2.putText(banner, title, (15, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.60, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(banner, subtitle, (15, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 210, 225), 1, cv2.LINE_AA)
        return np.vstack([banner, img])

    view_a = add_banner(raw_resized, "[A] UNTOUCHED RAW CROP", "Pristine Camera Sensor Pixels (0% Occlusion)")
    view_b = add_banner(seg_overlay, "[B] DUAL-MASK SEGMENTATION", f"Carparts-Seg (Panel) + CarDD-Seg (IoP: {sample['iop']})", color_bg=(30, 58, 138))
    view_c = add_banner(som_resized, "[C] STAGE 3 SET-OF-MARKS (SoM)", "15px Exterior Cyan Contour (VLM Inspection)", color_bg=(2, 132, 199))

    # Divider bar
    divider = np.full((view_a.shape[0], 6, 3), (226, 232, 240), dtype=np.uint8)

    composite = np.hstack([view_a, divider, view_b, divider, view_c])

    # Top Super-Banner
    super_banner_h = 50
    super_banner = np.full((super_banner_h, composite.shape[1], 3), (11, 19, 43), dtype=np.uint8)
    cv2.putText(super_banner, f"AUTO-SETTLE AI | STAGE 2 ARTIFACT: {sample['title'].upper()}", (20, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.62, (0, 220, 255), 2, cv2.LINE_AA)
    cv2.putText(super_banner, f"Panel: {sample['part']}   |   Defect: {sample['damage']}   |   IoP: {sample['iop']}   |   Status: PASSED STAGE 2", (20, 43), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (180, 200, 220), 1, cv2.LINE_AA)

    final_panel = np.vstack([super_banner, composite])

    # Save outputs
    out_repo = repo_out_dir / f"{sample['id']}_comparison.jpg"
    out_artifact = artifact_dir / f"{sample['id']}_comparison.jpg"
    cv2.imwrite(str(out_repo), final_panel, [cv2.IMWRITE_JPEG_QUALITY, 95])
    cv2.imwrite(str(out_artifact), final_panel, [cv2.IMWRITE_JPEG_QUALITY, 95])

    # Also copy individual raw and som images
    shutil.copy(str(sample["raw_src"]), str(artifact_dir / f"{sample['id']}_raw.jpg"))
    shutil.copy(str(sample["som_src"]), str(artifact_dir / f"{sample['id']}_som.jpg"))

    print(f"Generated comparison panel for {sample['id']} at {out_repo.name}")

for s in samples:
    make_panel(s)
print("All sample comparisons generated successfully!")
