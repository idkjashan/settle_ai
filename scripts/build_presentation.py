import os
import sys
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

# -------------------------------------------------------------
# Color Palette
# -------------------------------------------------------------
NAVY_DARK = RGBColor(11, 19, 43)        # #0B132B - Dark Background
NAVY_PRIMARY = RGBColor(15, 23, 42)     # #0F172A - Slate 900
SLATE_BLUE = RGBColor(30, 58, 138)      # #1E3A8A - Brand Primary
CYAN_ACCENT = RGBColor(2, 132, 199)     # #0284C7 - Brand Accent
EMERALD_GREEN = RGBColor(5, 150, 105)   # #059669 - Success
AMBER_WARN = RGBColor(217, 119, 6)      # #D97706 - Warning / Escalation
CRIMSON_RED = RGBColor(220, 38, 38)     # #DC2626 - Danger
BG_LIGHT = RGBColor(248, 250, 252)      # #F8FAFC - Off White
WHITE = RGBColor(255, 255, 255)         # #FFFFFF - Pure White
CARD_BORDER = RGBColor(226, 232, 240)   # #E2E8F0 - Light Border
TEXT_MUTED = RGBColor(100, 116, 139)    # #64748B - Muted Text
TEXT_DARK = RGBColor(15, 23, 42)        # #0F172A - Main Text

FONT_TITLE = "Segoe UI"
FONT_BODY = "Segoe UI"

def create_presentation():
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]

    # Helper: Set Slide Background
    def set_slide_background(slide, color):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = color
        bg.line.fill.background()
        return bg

    # Helper: Add Standard Header
    def add_header(slide, title, category="AUTO-SETTLE AI ARCHITECTURE"):
        # Category Tag
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.5), Inches(0.35))
        tf_cat = cat_box.text_frame
        tf_cat.word_wrap = True
        tf_cat.margin_left = tf_cat.margin_top = tf_cat.margin_right = tf_cat.margin_bottom = 0
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category.upper()
        p_cat.font.name = FONT_TITLE
        p_cat.font.size = Pt(11)
        p_cat.font.bold = True
        p_cat.font.color.rgb = CYAN_ACCENT

        # Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.72), Inches(11.5), Inches(0.65))
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        tf_title.margin_left = tf_title.margin_top = tf_title.margin_right = tf_title.margin_bottom = 0
        p_title = tf_title.paragraphs[0]
        p_title.text = title
        p_title.font.name = FONT_TITLE
        p_title.font.size = Pt(22)
        p_title.font.bold = True
        p_title.font.color.rgb = TEXT_DARK

    # Helper: Add Container Card
    def add_card(slide, left, top, width, height, bg_color=WHITE, border_color=CARD_BORDER):
        card = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        if border_color:
            card.line.color.rgb = border_color
            card.line.width = Pt(1)
        else:
            card.line.fill.background()
        return card

    # Helper: Add Stat Box
    def add_stat_box(slide, left, top, width, height, stat_number, label, accent_color=SLATE_BLUE):
        add_card(slide, left, top, width, height, bg_color=WHITE, border_color=CARD_BORDER)
        # Accent bar on top
        bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, width, Inches(0.08))
        bar.fill.solid()
        bar.fill.fore_color.rgb = accent_color
        bar.line.fill.background()

        tb = slide.shapes.add_textbox(left + Inches(0.2), top + Inches(0.2), width - Inches(0.4), height - Inches(0.3))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
        p0 = tf.paragraphs[0]
        p0.text = stat_number
        p0.font.name = FONT_TITLE
        p0.font.size = Pt(24)
        p0.font.bold = True
        p0.font.color.rgb = accent_color

        p1 = tf.add_paragraph()
        p1.text = label
        p1.font.name = FONT_BODY
        p1.font.size = Pt(10)
        p1.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 1: Title Slide (Dark Theme)
    # =========================================================
    slide1 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide1, NAVY_DARK)

    # Decorative Cyan Bar
    bar1 = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.8), Inches(1.2), Inches(0.1))
    bar1.fill.solid()
    bar1.fill.fore_color.rgb = CYAN_ACCENT
    bar1.line.fill.background()

    # Main Title
    t_box = slide1.shapes.add_textbox(Inches(1.2), Inches(2.2), Inches(11.0), Inches(2.2))
    tf1 = t_box.text_frame
    tf1.word_wrap = True
    p1_0 = tf1.paragraphs[0]
    p1_0.text = "🚗 Auto-Settle AI"
    p1_0.font.name = FONT_TITLE
    p1_0.font.size = Pt(40)
    p1_0.font.bold = True
    p1_0.font.color.rgb = WHITE

    p1_1 = tf1.add_paragraph()
    p1_1.text = "Autonomous Video-to-Cash Motor Claims Adjuster"
    p1_1.font.name = FONT_TITLE
    p1_1.font.size = Pt(22)
    p1_1.font.bold = True
    p1_1.font.color.rgb = CYAN_ACCENT
    p1_1.space_before = Pt(8)

    p1_2 = tf1.add_paragraph()
    p1_2.text = "Complete Architecture, Stage 0 to Stage 6 Implementation, and Operational Milestones"
    p1_2.font.name = FONT_BODY
    p1_2.font.size = Pt(14)
    p1_2.font.color.rgb = RGBColor(203, 213, 225)
    p1_2.space_before = Pt(16)

    # Bottom Pill Badges
    badges = [
        ("End-to-End Pipeline", "Stages 0 through 6"),
        ("Processing SLA", "< 90 Seconds Video-to-Cash"),
        ("Surveyor Overhead", "Slashed from ₹3,500 to < ₹5"),
        ("Automated Tests", "426 / 426 Passing (100%)"),
    ]
    for i, (b_title, b_val) in enumerate(badges):
        x = Inches(1.2 + i * 2.75)
        y = Inches(5.2)
        w = Inches(2.55)
        h = Inches(1.2)
        card = slide1.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(30, 41, 59)
        card.line.color.rgb = RGBColor(51, 65, 85)
        
        tb = slide1.shapes.add_textbox(x + Inches(0.2), y + Inches(0.2), w - Inches(0.4), h - Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.text = b_val
        p0.font.name = FONT_TITLE
        p0.font.size = Pt(13)
        p0.font.bold = True
        p0.font.color.rgb = WHITE
        
        p1 = tf.add_paragraph()
        p1.text = b_title
        p1.font.name = FONT_BODY
        p1.font.size = Pt(10)
        p1.font.color.rgb = RGBColor(148, 163, 184)

    # =========================================================
    # SLIDE 2: Executive Summary & The Problem Statement
    # =========================================================
    slide2 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide2, BG_LIGHT)
    add_header(slide2, "Executive Summary: The Motor Claims Dilemma", "Problem & Opportunity")

    # Left Card: Traditional Claims (The Pain)
    add_card(slide2, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.2))
    tb_left = slide2.shapes.add_textbox(Inches(1.1), Inches(1.9), Inches(5.0), Inches(4.6))
    tf_l = tb_left.text_frame
    tf_l.word_wrap = True
    p = tf_l.paragraphs[0]
    p.text = "Traditional Physical Claims Workflow"
    p.font.name = FONT_TITLE
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = CRIMSON_RED

    points_trad = [
        ("80%+ Minor Exterior Damage", "Scratches, bumper dents, broken mirrors (< ₹25,000 / $300) dominate claim volume."),
        ("5 to 7 Day Turnaround", "Requires scheduling physical human surveyor dispatch and garage inspection."),
        ("₹3,000 - ₹5,000 Overhead", "Surveyor fees, travel, loss adjustment expenses, and administrative paperwork."),
        ("Subjective & Fraud-Prone", "Prone to unrecorded prior damage, collusion, camera zoom cheating, and double-dipping."),
        ("Customer Churn", "Claimants endure lengthy disputes and vehicle downtime for minor touch-ups.")
    ]
    for title, desc in points_trad:
        p_t = tf_l.add_paragraph()
        p_t.text = f"• {title}: "
        p_t.font.bold = True
        p_t.font.size = Pt(11)
        p_t.font.color.rgb = TEXT_DARK
        p_t.space_before = Pt(10)
        
        # Add description inline
        run = p_t.add_run()
        run.text = desc
        run.font.bold = False
        run.font.color.rgb = TEXT_MUTED

    # Right Card: Auto-Settle AI Solution
    add_card(slide2, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.2))
    tb_right = slide2.shapes.add_textbox(Inches(7.1), Inches(1.9), Inches(5.1), Inches(4.6))
    tf_r = tb_right.text_frame
    tf_r.word_wrap = True
    p = tf_r.paragraphs[0]
    p.text = "Auto-Settle AI Autonomous Transformation"
    p.font.name = FONT_TITLE
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = EMERALD_GREEN

    points_sol = [
        ("< 90 Seconds Resolution", "Claimant uploads a 15s phone walkaround or 3-6 photos; receives instant UPI cash."),
        ("< ₹5 Compute Cost", "Slashes surveyor loss-adjustment expenses by 99.8% via automated computer vision."),
        ("Dual-Modality Flexibility", "Full support for continuous video walkarounds or structured photo packs."),
        ("Zero Financial Hallucination", "Statutory IRDAI / IMT depreciation calculated deterministically with Decimal math."),
        ("Forensic Anti-Fraud Defense", "Pre-existing rust detection (ESC-04), cut firewalls, and tamper-proof HMAC offer cards.")
    ]
    for title, desc in points_sol:
        p_t = tf_r.add_paragraph()
        p_t.text = f"✔ {title}: "
        p_t.font.bold = True
        p_t.font.size = Pt(11)
        p_t.font.color.rgb = TEXT_DARK
        p_t.space_before = Pt(10)
        
        run = p_t.add_run()
        run.text = desc
        run.font.bold = False
        run.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 3: The Fatal Flaws of "Naive AI" Claims
    # =========================================================
    slide3 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide3, BG_LIGHT)
    add_header(slide3, "The 5 Fatal Flaws of 'Naive AI' Claims Platforms", "Architectural Philosophy")

    flaws = [
        ("1. Static Photo Spoofing", 
         "Naive AI: User downloads damaged car photos from Google or snaps a stranger's car in a parking lot.\n\nAuto-Settle Fix: Mandatory continuous ByteTrack walkaround or plate-anchored photo pack matched against policy ANPR & HSV paint color."),
        ("2. Camera Zoom Cheating", 
         "Naive AI: Holding camera 5 cm from a 2 cm scratch makes the entire door look destroyed, triggering false replacement.\n\nAuto-Settle Fix: Intersection-over-Part (IoP = Area(D ∩ P)/Area(P)) and Dual-Frame Split locking wide panel surface area."),
        ("3. Financial Hallucination", 
         "Naive AI: Prompting an LLM to 'estimate repair cost' leads to arbitrary numbers and prompt injection exploits.\n\nAuto-Settle Fix: Zero AI financial authority. 100% Python standard library Decimal statutory IMT arithmetic and SQL parts."),
        ("4. Dirt & Glare False Positives", 
         "Naive AI: Neural networks mistake mud splatters, bird droppings, chalk, or sun glare for deep dent creases.\n\nAuto-Settle Fix: Set-of-Marks (SoM) dual crops with 8-contaminant quarantine and bare-metal substrate exposure checks."),
        ("5. Repeat 'Double-Dipping' Fraud", 
         "Naive AI: User collects cash payout, leaves scratch unrepaired, and claims again 6 months later.\n\nAuto-Settle Fix: SQL Unrepaired Claims Ledger locking settled VIN parts with partial unique indexes (ESC-03).")
    ]

    for i, (title, text) in enumerate(flaws):
        col = i % 3
        row = i // 3
        w = Inches(3.7)
        h = Inches(2.4)
        x = Inches(0.8 + col * 4.0)
        y = Inches(1.6 + row * 2.65)
        if i == 4:
            # Center the 5th item
            x = Inches(4.8)
            y = Inches(4.25)
            w = Inches(3.7)

        add_card(slide3, x, y, w, h)
        tb = slide3.shapes.add_textbox(x + Inches(0.25), y + Inches(0.2), w - Inches(0.5), h - Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.text = title
        p0.font.name = FONT_TITLE
        p0.font.size = Pt(13)
        p0.font.bold = True
        p0.font.color.rgb = SLATE_BLUE

        p1 = tf.add_paragraph()
        p1.text = text
        p1.font.name = FONT_BODY
        p1.font.size = Pt(9.5)
        p1.font.color.rgb = TEXT_DARK
        p1.space_before = Pt(6)

    # =========================================================
    # SLIDE 4: End-to-End System Pipeline Overview
    # =========================================================
    slide4 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide4, BG_LIGHT)
    add_header(slide4, "End-to-End System Architecture Pipeline", "The 7 Core Processing Packets")

    stages = [
        ("STAGE 0", "Fast-Fail Gate", "< 180ms", "Policy SQL, SHA-256 dedupe, ffprobe NLE blacklist, OpenCV luminance & Laplacian sharpness."),
        ("STAGE 1", "Vehicle Identity", "< 1.2s", "Gate 1 cut firewall, Gate 2 progressive ANPR & HSV paint, Gate 3 ByteTrack keyframe extraction."),
        ("INTENT", "Claim Intent NLP", "< 5ms", "FastEmbed ONNX (MiniLM-L6-v2) intent extraction; quarantines unclaimed pre-existing damage."),
        ("STAGE 2", "Dual-Mask Seg", "< 250ms", "Carparts-Seg + CarDD-Seg, Shapely GEOS C++ IoP, zoom anti-inflation clamp, 15px cyan SoM crops."),
        ("STAGE 3", "VLM Inspection", "< 600ms", "Gemini 2.5 Flash / Ollama dual crops, 8-contaminant quarantine, ESC-04 rust & ESC-06 chassis gates."),
        ("STAGE 4", "Actuarial Engine", "< 50ms", "IMT statutory depreciation, continuous dent labor scaling, paint finish multipliers, NCB advisory."),
        ("STAGE 5 & 6", "Negotiate & Settle", "< 120ms", "3-round concession FSM, HMAC offer signing, pro-rata penny balancing, instant voucher & PDF.")
    ]

    for i, (tag, name, sla, desc) in enumerate(stages):
        x = Inches(0.8 + (i % 4) * 2.95)
        y = Inches(1.6 + (i // 4) * 2.7)
        w = Inches(2.75)
        h = Inches(2.4)
        add_card(slide4, x, y, w, h)

        # Header tag
        tag_box = slide4.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x + Inches(0.2), y + Inches(0.2), Inches(1.1), Inches(0.3))
        tag_box.fill.solid()
        tag_box.fill.fore_color.rgb = SLATE_BLUE
        tag_box.line.fill.background()
        tf_t = tag_box.text_frame
        p_t = tf_t.paragraphs[0]
        p_t.text = tag
        p_t.font.name = FONT_TITLE
        p_t.font.size = Pt(9)
        p_t.font.bold = True
        p_t.font.color.rgb = WHITE
        p_t.alignment = PP_ALIGN.CENTER

        # SLA tag
        sla_box = slide4.shapes.add_textbox(x + Inches(1.4), y + Inches(0.2), Inches(1.1), Inches(0.3))
        tf_s = sla_box.text_frame
        p_s = tf_s.paragraphs[0]
        p_s.text = sla
        p_s.font.name = FONT_TITLE
        p_s.font.size = Pt(10)
        p_s.font.bold = True
        p_s.font.color.rgb = CYAN_ACCENT
        p_s.alignment = PP_ALIGN.RIGHT

        # Name & Description
        tb = slide4.shapes.add_textbox(x + Inches(0.2), y + Inches(0.6), w - Inches(0.4), h - Inches(0.7))
        tf = tb.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.text = name
        p0.font.name = FONT_TITLE
        p0.font.size = Pt(14)
        p0.font.bold = True
        p0.font.color.rgb = TEXT_DARK

        p1 = tf.add_paragraph()
        p1.text = desc
        p1.font.name = FONT_BODY
        p1.font.size = Pt(9.5)
        p1.font.color.rgb = TEXT_MUTED
        p1.space_before = Pt(8)

    # =========================================================
    # SLIDE 5: Stage 0 Deep Dive: Fast-Fail Gate
    # =========================================================
    slide5 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide5, BG_LIGHT)
    add_header(slide5, "Stage 0: Dual-Modality Fast-Fail Perimeter Gate", "Sub-180ms Intake Invariants")

    # 3 Column Cards
    col_w = Inches(3.7)
    col_h = Inches(5.1)

    # Card 1: Inputs & Policy Gate
    add_card(slide5, Inches(0.8), Inches(1.6), col_w, col_h)
    tb1 = slide5.shapes.add_textbox(Inches(1.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "1. Policy & Hash Verification"
    p.font.name = FONT_TITLE
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items1 = [
        ("Inputs", "policy_id, video or 3-6 photos, optional claim_description, is_demo_rehearsal."),
        ("SQL Status Check", "Queries PostgreSQL for ACTIVE policy, verifies date coverage, and ensures claims_ytd < max_claims_per_year."),
        ("SHA-256 Deduplication", "Calculates video hash on the fly. Rejects exact duplicate submissions across history."),
        ("Demo Bypass", "Allows rehearsal bypass for stress-testing without polluting claims database.")
    ]
    for h, b in items1:
        p_i = tf1.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10.5)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Card 2: Container Forensics
    add_card(slide5, Inches(4.8), Inches(1.6), col_w, col_h)
    tb2 = slide5.shapes.add_textbox(Inches(5.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "2. Container Forensics (ffprobe)"
    p.font.name = FONT_TITLE
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items2 = [
        ("Duration Bounding", "Strictly enforces 5.0s <= duration <= 60.0s (rejects 2s snippets or 10-minute uploads)."),
        ("Resolution Gate", "Rejects video if width or height < 720p (1280x720) or framerate < 15 fps."),
        ("NLE Editor Blacklist", "Detects metadata tags from CapCut, Adobe Premiere, InShot, DaVinci Resolve."),
        ("Encoder Whitelist", "Allows authentic mobile camera encoders (Lavf, libx264, Apple/Android hardware muxers).")
    ]
    for h, b in items2:
        p_i = tf2.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10.5)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Card 3: Visual Quality Gate
    add_card(slide5, Inches(8.8), Inches(1.6), col_w, col_h)
    tb3 = slide5.shapes.add_textbox(Inches(9.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    p = tf3.paragraphs[0]
    p.text = "3. OpenCV Quality & Remediation"
    p.font.name = FONT_TITLE
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items3 = [
        ("5-Frame Grab Sampling", "Zero-transcode cv2 grab() scan across video quarters."),
        ("Luminance Bounds", "Mean YUV luminance strictly 45.0 <= Y <= 220.0 (rejects pitch-dark or blinding sun glare)."),
        ("Laplacian Sharpness", "Normalized variance >= 80.0 (rejects out-of-focus or smeared lenses)."),
        ("ESC-00 Remediation", "Returns HTTP 200 with UX guidance directing claimant how to retake video cleanly.")
    ]
    for h, b in items3:
        p_i = tf3.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10.5)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 6: Stage 1 Deep Dive: Vehicle Identity & Continuity
    # =========================================================
    slide6 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide6, BG_LIGHT)
    add_header(slide6, "Stage 1: Vehicle Identity & Continuity Grounding", "Anti-Fraud Grounding Gates")

    col_w = Inches(3.7)
    col_h = Inches(5.1)

    # Gate 1: Cut Firewall
    add_card(slide6, Inches(0.8), Inches(1.6), col_w, col_h)
    tb1 = slide6.shapes.add_textbox(Inches(1.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "Gate 1: Cut & Splice Firewall"
    p.font.name = FONT_TITLE
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items1 = [
        ("Sub-100ms CPU Decode", "320x180 fast resolution downsample for real-time video scan."),
        ("160-bin HSV Correlation", "Flags hard cut if histogram correlation r < 0.60 between frames."),
        ("PySceneDetect Content", "Score >= 27.0 combined with r < 0.70 eliminates false flags on fast corner pans."),
        ("Freeze-Frame Gate", "Flags splice if camera pauses identically for > 15 frames / 750ms.")
    ]
    for h, b in items1:
        p_i = tf1.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10.5)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Gate 2: Progressive ANPR & Paint
    add_card(slide6, Inches(4.8), Inches(1.6), col_w, col_h)
    tb2 = slide6.shapes.add_textbox(Inches(5.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "Gate 2: ANPR & Paint Grounding"
    p.font.name = FONT_TITLE
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items2 = [
        ("YOLO11m-seg Bumper ROI", "Constrains OCR to vehicle bumper zones, filtering street signs."),
        ("2-Line HSRP Merging", "Merges stacked Indian plate text (e.g., 'DL 01' + 'AB 1234')."),
        ("Homoglyph Levenshtein", "Forgives OCR character swaps (8 <-> B, 0 <-> O, 1 <-> I)."),
        ("Dominant Paint HSV", "Extracts body paint (stripping tires/glass), validates delta E <= 35.0 against policy.")
    ]
    for h, b in items2:
        p_i = tf2.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10.5)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Gate 3: ByteTrack & Keyframes
    add_card(slide6, Inches(8.8), Inches(1.6), col_w, col_h)
    tb3 = slide6.shapes.add_textbox(Inches(9.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    p = tf3.paragraphs[0]
    p.text = "Gate 3: ByteTrack & Keyframes"
    p.font.name = FONT_TITLE
    p.font.size = Pt(15)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items3 = [
        ("Multi-Car Latching", "Selects largest vehicle candidate (>= 6% area), preventing track jumping in parking lots."),
        ("Macro Zoom Hand-Off", "Holds track state for 45 frames when camera zooms into 10 cm closeup."),
        ("Reverse Walkaround", "Dynamically anchors front bumper when plate appears at end of walkaround."),
        ("Canonical Keyframes", "Extracts front_bumper, side_panel, and damage_closeup_primary scored by sharpness.")
    ]
    for h, b in items3:
        p_i = tf3.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10.5)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 7: System 1 NLP: Dynamic Claim Intent Grounding
    # =========================================================
    slide7 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide7, BG_LIGHT)
    add_header(slide7, "System 1 NLP: Dynamic Claim Intent Grounding", "Zero-Cost Semantic Quarantine (< 5ms)")

    # 2 Wide Cards
    add_card(slide7, Inches(0.8), Inches(1.6), Inches(5.6), Inches(5.1))
    tb_l = slide7.shapes.add_textbox(Inches(1.05), Inches(1.85), Inches(5.1), Inches(4.6))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p = tf_l.paragraphs[0]
    p.text = "Local FastEmbed ONNX Extraction"
    p.font.name = FONT_TITLE
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    intent_pts = [
        ("Sub-5ms Execution", "Runs local MiniLM-L6-v2 ONNX runtime—zero external API calls or latency overhead."),
        ("Directional Disambiguation", "Resolves 'driver side' -> left in India/UK, 'passenger side' -> right, 'front' vs 'rear'."),
        ("Synonym & Slang Resolution", "Maps colloquialisms ('dicky' -> trunk/tailgate, 'bonnet' -> hood, 'light broken' -> lamp_broken)."),
        ("Dynamic Taxonomy Registry", "Thread-safe singleton mapping text embeddings directly to OEM part keys.")
    ]
    for h, b in intent_pts:
        p_i = tf_l.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(11)
        p_i.space_before = Pt(12)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Right Card: Damage Quarantine Logic
    add_card(slide7, Inches(6.8), Inches(1.6), Inches(5.7), Inches(5.1))
    tb_r = slide7.shapes.add_textbox(Inches(7.05), Inches(1.85), Inches(5.2), Inches(4.6))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    p = tf_r.paragraphs[0]
    p.text = "Claimed vs. Unclaimed Quarantine Logic"
    p.font.name = FONT_TITLE
    p.font.size = Pt(16)
    p.font.bold = True
    p.font.color.rgb = EMERALD_GREEN

    quar_pts = [
        ("Claimed Damage -> Billed", "When claimant reports 'scratched bumper', segmented bumper scratch is admitted to repair schedule."),
        ("Unclaimed Damage -> Quarantined", "Stone chips or pre-existing door scuffs are quarantined to UNCLAIMED_PREEXISTING_DAMAGE."),
        ("Bypasses ESC-05 False Fraud", "Prevents opposite-side pre-existing scratches from triggering false multi-hit fraud rejections."),
        ("Anti-Phantom Gate (ESC-07)", "If claimant declares 'dented front door' but computer vision finds no dent, raises ESC-07_CLAIMED_DAMAGE_NOT_FOUND.")
    ]
    for h, b in quar_pts:
        p_i = tf_r.add_paragraph()
        p_i.text = f"✔ {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(11)
        p_i.space_before = Pt(12)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 8: Stage 2 Deep Dive: Dual-Mask Segmentation
    # =========================================================
    slide8 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide8, BG_LIGHT)
    add_header(slide8, "Stage 2: Conditioned Dual-Mask Part & Damage Segmentation", "Shapely GEOS C++ Spatial Analytics")

    col_w = Inches(3.7)
    col_h = Inches(5.1)

    # Col 1: Dual Models
    add_card(slide8, Inches(0.8), Inches(1.6), col_w, col_h)
    tb1 = slide8.shapes.add_textbox(Inches(1.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "1. Dual YOLO FP16 Batched"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items1 = [
        ("Model A: Carparts-Seg", "Segments 23 canonical parts (or 33 AutoInspect classes mapped to canonical OEM keys)."),
        ("Model B: CarDD-Seg", "Segments 6 damage classes (dent, scratch, crack, glass_shatter, lamp_broken, tire_flat)."),
        ("Batched FP16 Inference", "Runs under shared GPU semaphore locking to prevent VRAM spikes."),
        ("Strict Taxonomy Check", "Rejects generic COCO 80-class models to prevent cross-wiring person -> dent.")
    ]
    for h, b in items1:
        p_i = tf1.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(8)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 2: Spatial Intersection
    add_card(slide8, Inches(4.8), Inches(1.6), col_w, col_h)
    tb2 = slide8.shapes.add_textbox(Inches(5.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "2. Shapely Spatial Math"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items2 = [
        ("IoP Formula", "IoP = Area(Damage ∩ Part) / Area(Part). Normalizes for camera distance."),
        ("Self-Healing Polygons", "Repairs bow-ties and invalid geometries with .buffer(0)."),
        ("10% Spillover Filter", "Discards 3% bleed onto adjacent panels due to loose boundary masks."),
        ("Unary Union Merging", "Overlapping dent + scratch on same panel are merged (prevents double-counting).")
    ]
    for h, b in items2:
        p_i = tf2.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(8)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 3: Zoom Anti-Inflation & SoM
    add_card(slide8, Inches(8.8), Inches(1.6), col_w, col_h)
    tb3 = slide8.shapes.add_textbox(Inches(9.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    p = tf3.paragraphs[0]
    p.text = "3. Anti-Inflation & SoM"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items3 = [
        ("15px Margin Detection", "Flags is_complete_panel=False if panel touches image boundary."),
        ("Dual-Frame Split", "Locks IoP from medium shot (0.032); macro closeup used only for VLM micro-depth."),
        ("Closeup-Only Clamp", "Clamps IoP <= 0.25 if only macro closeup exists (blocks false replacement)."),
        ("0% Occlusion SoM", "Renders 15px dilated exterior cyan contour; damage interior is 100% bit-identical.")
    ]
    for h, b in items3:
        p_i = tf3.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(8)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 9: Stage 3 Deep Dive: VLM Inspection & Forensics
    # =========================================================
    slide9 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide9, BG_LIGHT)
    add_header(slide9, "Stage 3: Set-of-Marks (SoM) VLM Damage Inspection", "Multi-Provider Vision Forensics (< 600ms)")

    col_w = Inches(3.7)
    col_h = Inches(5.1)

    # Col 1: Vision Adapters
    add_card(slide9, Inches(0.8), Inches(1.6), col_w, col_h)
    tb1 = slide9.shapes.add_textbox(Inches(1.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "Decoupled Vision Adapters"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items1 = [
        ("Gemini 2.5 Flash", "Cloud VLM with temp=0.0 and structured Pydantic response schema."),
        ("Local Ollama miniCPM-V", "Async HTTP client over kernel route table (< 0.1ms IP probe)."),
        ("Circuit Breaker", "Trips to OPEN on 5 consecutive failures, 30s backoff with randomized jitter."),
        ("Resilient JSON Parser", "Repairs markdown code fences, trailing commas, and Python literal syntax.")
    ]
    for h, b in items1:
        p_i = tf1.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(8)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 2: 8-Contaminant Quarantine
    add_card(slide9, Inches(4.8), Inches(1.6), col_w, col_h)
    tb2 = slide9.shapes.add_textbox(Inches(5.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "8-Contaminant Quarantine"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items2 = [
        ("Mud, Dirt & Bird Droppings", "Diverts surface dirt away from billing schedules."),
        ("Chalk, Marker & Decals", "Filters deliberate sticker spoofing or workshop chalk outlines."),
        ("Specular Glare & Reflections", "Filters sunlight reflections that fool deep segmenters."),
        ("Plastic Rust Invariant", "Overrides VLM plastic bumper rust hallucination to False (plastic cannot rust).")
    ]
    for h, b in items2:
        p_i = tf2.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(8)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 3: Forensic Fraud Gates
    add_card(slide9, Inches(8.8), Inches(1.6), col_w, col_h)
    tb3 = slide9.shapes.add_textbox(Inches(9.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    p = tf3.paragraphs[0]
    p.text = "Forensic Fraud Gates"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = CRIMSON_RED

    items3 = [
        ("ESC-04 Pre-Existing Rust", "Halts claim if bare-metal orange rust or flaking body putty is detected."),
        ("ESC-06 Chassis Misalignment", "Halts claim if structural frame shift or uneven panel gaps are visible."),
        ("ESC-07 Zero Real Damage", "Halts claim if all detections were quarantined as glare or dirt."),
        ("Depth Grades (L1 - L5)", "Assigns physical depth: L1 scuff, L2 scratch, L3 ding (PDR), L4 crease, L5 tear.")
    ]
    for h, b in items3:
        p_i = tf3.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(8)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 10: Stage 4 Deep Dive: Actuarial Pricing Engine
    # =========================================================
    slide10 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide10, BG_LIGHT)
    add_header(slide10, "Stage 4: Deterministic Actuarial Pricing Engine", "Statutory Indian Motor Tariff (IMT) & IRDAI Rules")

    # 4 Cards
    cw = Inches(2.75)
    ch = Inches(5.1)

    cards_s4 = [
        ("Statutory Depreciation", SLATE_BLUE, [
            ("100% Decimal Math", "Zero float rounding errors; strictly ROUND_HALF_UP."),
            ("Materials Schedule", "Rubber/Plastic flat 50%, Glass 0%, Fiberglass 30%."),
            ("Metal Age Brackets", "<6m: 0%, 6m-1y: 5%, 1-2y: 10%, 2-3y: 15%, 3-4y: 25%, 4-5y: 35%, 5-10y: 40%, >10y: 50%."),
            ("Zero-Dep Rider", "Forces part depreciation to 0.00% if policy rider active.")
        ]),
        ("Labor & Paint Rates", SLATE_BLUE, [
            ("Continuous Dent Scaling", "gamma(IoP) = min(2.0, 1.0 + IoP * 2.5). Scales labor dynamically."),
            ("Repair vs Replace", "Replaced if IoP > 0.30, L5 tear, or unrepairable lamp assembly."),
            ("Paint Finish Multipliers", "Solid 1.0x, Metallic 1.25x, Pearl 1.35x finish."),
            ("Blend Overlap Discount", "Primary 100%, secondary adjacent 75%, tertiary+ 60%.")
        ]),
        ("Excess & NCB Advisory", SLATE_BLUE, [
            ("Compulsory Excess", "<= 1500cc: ₹1,000; > 1500cc (e.g. Fortuner): ₹2,000."),
            ("Salvage Deduction", "Replaced metal parts: 5% scrap recovery deducted."),
            ("NCB Step-Back Warning", "Calculates 3-year loss of renewal bonus discount."),
            ("Economic Utility", "Advises PAY_OUT_OF_POCKET if future NCB penalty > net payout.")
        ]),
        ("Cash Settlement Band", EMERALD_GREEN, [
            ("O_0 (Initial Offer)", "75% of Net Garage Repair liability."),
            ("O_target (Fair Target)", "85% of Net Garage Repair liability."),
            ("O_max (Autonomous Cap)", "min(₹25,000, 95% of Net Garage Repair)."),
            ("ESC-08 Ceiling Guard", "Claims > ₹25,000 escalate to Senior Adjuster with estimate saved.")
        ])
    ]

    for i, (ctitle, ccolor, citems) in enumerate(cards_s4):
        x = Inches(0.8 + i * 2.95)
        y = Inches(1.6)
        add_card(slide10, x, y, cw, ch)
        tb = slide10.shapes.add_textbox(x + Inches(0.2), y + Inches(0.25), cw - Inches(0.4), ch - Inches(0.5))
        tf = tb.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = ctitle
        p.font.name = FONT_TITLE
        p.font.size = Pt(13)
        p.font.bold = True
        p.font.color.rgb = ccolor

        for h, b in citems:
            p_i = tf.add_paragraph()
            p_i.text = f"• {h}: "
            p_i.font.bold = True
            p_i.font.size = Pt(9.5)
            p_i.space_before = Pt(8)
            r = p_i.add_run()
            r.text = b
            r.font.bold = False
            r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 11: Stage 5 Deep Dive: Bounded Negotiation FSM
    # =========================================================
    slide11 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide11, BG_LIGHT)
    add_header(slide11, "Stage 5: Bounded Negotiation Chatbot FSM", "Concession Math & Cryptographic HMAC-SHA256 Signing")

    col_w = Inches(3.7)
    col_h = Inches(5.1)

    # Col 1: Cryptographic Signing
    add_card(slide11, Inches(0.8), Inches(1.6), col_w, col_h)
    tb1 = slide11.shapes.add_textbox(Inches(1.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "HMAC-SHA256 Offer Signing"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items1 = [
        ("Tamper-Proof Payload", "Every card signed over {claim_id}:{round}:{amount_inr}:{expires_at}."),
        ("Zero Client Trust", "Frontend DevTools tampering causes instant HTTP 403 InvalidOfferTokenError."),
        ("24-Hour Expiration", "Offers expire automatically after 24 hours to prevent stale acceptance."),
        ("State Isolation", "Each round updates Redis cache and PostgreSQL negotiation_session atomically.")
    ]
    for h, b in items1:
        p_i = tf1.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 2: Concession Math
    add_card(slide11, Inches(4.8), Inches(1.6), col_w, col_h)
    tb2 = slide11.shapes.add_textbox(Inches(5.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "3-Round Concession Math"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items2 = [
        ("Dynamic Alpha Decay", "alpha_1 = 0.50, alpha_2 = 0.35, alpha_3 = 0.25 (decreasing concessions)."),
        ("Concession Formula", "O_r = O_{r-1} + alpha_r * RationaleScore * min(Counter - O_{r-1}, O_target - O_{r-1})."),
        ("Anchor Inversion Guard", "If user asks <= O_current (typo), clamps to O_current and explains."),
        ("Round 3 Terminal Lock", "Final take-it-or-leave-it offer locked strictly to <= O_max <= ₹25,000.")
    ]
    for h, b in items2:
        p_i = tf2.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 3: NLP Parser
    add_card(slide11, Inches(8.8), Inches(1.6), col_w, col_h)
    tb3 = slide11.shapes.add_textbox(Inches(9.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    p = tf3.paragraphs[0]
    p.text = "Vernacular & Hinglish NLP"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items3 = [
        ("Currency Extraction", "Parses INR across '₹15,000', 'Rs 12500', '18000 bucks', 'INR 14,000.50'."),
        ("Relative Deltas", "Understands '+2000', 'add 1500', 'increase by Rs 2,500'."),
        ("Hinglish Keywords", "Detects 'paisa badhao bohot kam hai', 'kharcha zyada hai', 'theek hai manzoor'."),
        ("Template Presenter", "100% deterministic conversational template fallback (zero LLM drift).")
    ]
    for h, b in items3:
        p_i = tf3.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 12: Stage 6 Deep Dive: Settlement & Escalation
    # =========================================================
    slide12 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide12, BG_LIGHT)
    add_header(slide12, "Stage 6: Settlement Router, Apportionment & Dossier", "Penny-Balanced Apportionment & Ledger Commitments")

    col_w = Inches(3.7)
    col_h = Inches(5.1)

    # Col 1: Pro-Rata Apportionment
    add_card(slide12, Inches(0.8), Inches(1.6), col_w, col_h)
    tb1 = slide12.shapes.add_textbox(Inches(1.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True
    p = tf1.paragraphs[0]
    p.text = "Pro-Rata Apportionment"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items1 = [
        ("Multi-Part Allocation", "Distributes agreed cash lump-sum (e.g. ₹12,500) proportionally across damaged parts."),
        ("Penny Balancing Formula", "S_i = floor(O_settled * E_i / E_gross). Residual paise allocated to highest-value part."),
        ("Bit-Level Sum Invariant", "Guarantees sum(S_i) == O_settled down to exact 0.00 paise mark."),
        ("Audit Compliance", "Ensures precise accounting entries for insurer financial ledgers.")
    ]
    for h, b in items1:
        p_i = tf1.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 2: Unrepaired Ledger & Vouchers
    add_card(slide12, Inches(4.8), Inches(1.6), col_w, col_h)
    tb2 = slide12.shapes.add_textbox(Inches(5.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf2 = tb2.text_frame
    tf2.word_wrap = True
    p = tf2.paragraphs[0]
    p.text = "Ledger & Instant Vouchers"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = EMERALD_GREEN

    items2 = [
        ("Unrepaired Ledger Write", "Commits each settled part to unrepaired_claims_ledger in PostgreSQL (locks ESC-03)."),
        ("Instant Voucher Issuance", "Generates VOUCHER-AUTOSETTLE-YYYYMMDD-XXXX with simulated IMPS payout reference."),
        ("Indian Rupee Words", "Formats amount to text (e.g. 'Twelve Thousand Five Hundred Rupees Only')."),
        ("SHA-256 Digital Seal", "Seals voucher tamper-proof with digital certificate hash.")
    ]
    for h, b in items2:
        p_i = tf2.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # Col 3: Escalation & PDFs
    add_card(slide12, Inches(8.8), Inches(1.6), col_w, col_h)
    tb3 = slide12.shapes.add_textbox(Inches(9.05), Inches(1.85), col_w - Inches(0.5), col_h - Inches(0.5))
    tf3 = tb3.text_frame
    tf3.word_wrap = True
    p = tf3.paragraphs[0]
    p.text = "Escalation & PDF Service"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    items3 = [
        ("Cashless Garage Routing", "Claimant rejection (ESC-USER-REJECT) routes claim to authorized cashless workshop."),
        ("ReportLab PDF Service", "Generates vector printable PDF Settlement Certificate (/voucher/pdf)."),
        ("Surveyor Review Dossier", "Generates comprehensive PDF Adjuster Dossier (/dossier/pdf) on escalation."),
        ("6-Point Physical Checklist", "Includes standardized surveyor checklist: odometer, VIN stamp, frame alignment.")
    ]
    for h, b in items3:
        p_i = tf3.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(10)
        p_i.space_before = Pt(10)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 13: The Master Escalation Matrix (ESC-00 to ESC-09)
    # =========================================================
    slide13 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide13, BG_LIGHT)
    add_header(slide13, "Master Anti-Fraud & Escalation Taxonomy", "Autonomous Risk Containment Gates")

    esc_table_data = [
        ("ESC-00", "Perimeter Video / Photo Fail", "Dark, blurry, corrupt, or CapCut NLE edit metadata tags", "Stage 0", "HTTP 200 + UX Recapture"),
        ("ESC-01", "Cut / Splice Firewall Breach", "Video jump cuts, camera splices, or frozen frames", "Stage 1", "Hard Rejection"),
        ("ESC-02", "Vehicle Identity Mismatch", "License plate OCR or paint HSV color mismatch against policy", "Stage 1", "Hard Rejection"),
        ("ESC-03", "Repeat 'Double-Dipping' Claim", "Part already settled for cash in unrepaired_claims_ledger", "Stage 2 / 4", "Hard Fraud Halt"),
        ("ESC-04", "Pre-Existing Rust / Oxidation", "VLM detects bare-metal orange rust or flaking old putty", "Stage 3", "Pre-Existing Fraud Halt"),
        ("ESC-05", "Opposite-Side Multi-Hit Fraud", "Unrelated damages on both left and right flanks simultaneously", "Stage 2", "Desk Adjuster Escalation"),
        ("ESC-06", "Safety-Critical Structural Damage", "Glass shatter, wheel rim deformation, or chassis frame shift", "Stage 2 / 3", "Physical Surveyor Review"),
        ("ESC-07", "Zero Real Damage Detected", "All detections quarantined as dirt/glare or intent not found", "Stage 2 / 3", "Desk Adjuster Review"),
        ("ESC-08", "Autonomous Financial Ceiling", "Net repair estimate exceeds self-settlement cap (> ₹25,000)", "Stage 4", "Senior Adjuster Handoff"),
        ("ESC-09", "Catalogue Part Missing", "Discontinued part missing from OEM database & segment fallback", "Stage 4", "Procurement Review"),
        ("ESC-USER-REJECT", "Cashless Garage Selected", "Claimant declines cash offers; prefers authorized garage repair", "Stage 5 / 6", "Cashless Garage Routing")
    ]

    # Create Table Shape
    rows = len(esc_table_data) + 1
    cols = 5
    t_left = Inches(0.8)
    t_top = Inches(1.5)
    t_width = Inches(11.73)
    t_height = Inches(5.3)

    table_shape = slide13.shapes.add_table(rows, cols, t_left, t_top, t_width, t_height)
    table = table_shape.table
    table.columns[0].width = Inches(1.6)
    table.columns[1].width = Inches(2.5)
    table.columns[2].width = Inches(4.3)
    table.columns[3].width = Inches(1.2)
    table.columns[4].width = Inches(2.13)

    headers = ["Escalation Code", "Failure Category", "Trigger Condition", "Stage", "System Action"]
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.fill.solid()
        cell.fill.fore_color.rgb = SLATE_BLUE
        p = cell.text_frame.paragraphs[0]
        p.text = h
        p.font.name = FONT_TITLE
        p.font.size = Pt(10)
        p.font.bold = True
        p.font.color.rgb = WHITE

    for i, row in enumerate(esc_table_data, 1):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 == 1 else RGBColor(241, 245, 249)
            p = cell.text_frame.paragraphs[0]
            p.text = val
            p.font.name = FONT_BODY
            p.font.size = Pt(8.5)
            if j == 0:
                p.font.bold = True
                p.font.color.rgb = CRIMSON_RED if "ESC" in val else TEXT_DARK
            else:
                p.font.color.rgb = TEXT_DARK

    # =========================================================
    # SLIDE 14: Testing, Verification & Regression Ledger
    # =========================================================
    slide14 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide14, BG_LIGHT)
    add_header(slide14, "Testing Rigor, CI Gates & Verification Milestones", "426 Automated Tests • Zero Regression Status")

    # Top Stats
    stat_w = Inches(2.75)
    stat_h = Inches(1.2)
    add_stat_box(slide14, Inches(0.8), Inches(1.5), stat_w, stat_h, "426 / 426", "Total Automated Pytest Tests (100% Pass)", EMERALD_GREEN)
    add_stat_box(slide14, Inches(3.75), Inches(1.5), stat_w, stat_h, "20 / 20", "E2E Curated Scenarios Passed (100%)", SLATE_BLUE)
    add_stat_box(slide14, Inches(6.7), Inches(1.5), stat_w, stat_h, "0.00%", "SoM Interior Damage Occlusion (Bit-Level)", CYAN_ACCENT)
    add_stat_box(slide14, Inches(9.65), Inches(1.5), stat_w, stat_h, "0 Failures", "Zero Floating-Point Math on Financial Decisions", EMERALD_GREEN)

    # 2 Detail Cards below
    add_card(slide14, Inches(0.8), Inches(2.9), Inches(5.7), Inches(3.8))
    tb_l = slide14.shapes.add_textbox(Inches(1.05), Inches(3.1), Inches(5.2), Inches(3.4))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p = tf_l.paragraphs[0]
    p.text = "Comprehensive Test Suite Breakdown"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = SLATE_BLUE

    suite_items = [
        ("Stage 0 Suite", "29 tests covering policy caps, SHA-256 dedupe, ffprobe NLE blacklist, photo packs."),
        ("Stage 1 Suite", "23 tests covering cut detection, 2-line HSRP OCR, color grounding, and ByteTrack."),
        ("System 1 NLP", "23 tests covering FastEmbed ONNX token matching and damage quarantine."),
        ("Stage 2 Suite", "41 tests covering GEOS polygon IoP, zoom anti-inflation, and 33-class taxonomy."),
        ("Stage 3 Suite", "80 tests covering VLM adapters, circuit breakers, 8 contaminants, and rust fraud."),
        ("Stage 4 Suite", "102 tests covering all 8 IMT metal brackets, labor scaling, and NCB utility."),
        ("Stage 5 & 6 Suite", "93 tests covering concession curves, HMAC signing, penny balancing, and APIs.")
    ]
    for h, b in suite_items:
        p_i = tf_l.add_paragraph()
        p_i.text = f"• {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(9.5)
        p_i.space_before = Pt(4)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    add_card(slide14, Inches(6.8), Inches(2.9), Inches(5.7), Inches(3.8))
    tb_r = slide14.shapes.add_textbox(Inches(7.05), Inches(3.1), Inches(5.2), Inches(3.4))
    tf_r = tb_r.text_frame
    tf_r.word_wrap = True
    p = tf_r.paragraphs[0]
    p.text = "Adversarial Red-Team & Real Video Cohort"
    p.font.name = FONT_TITLE
    p.font.size = Pt(14)
    p.font.bold = True
    p.font.color.rgb = EMERALD_GREEN

    adv_items = [
        ("11-Attack Red-Team Suite", "Tests against 0-frame bypasses, scratch disk leaks, Redis lock TOCTOU races, CapCut metadata spoofing, and negative ROI coordinates."),
        ("Authentic Video Cohort", "car_videos/ directory pushed to GitHub containing 10 authentic walkaround videos and high-contrast macro damage photos for E2E validation."),
        ("Hermetic In-Memory DB", "FakeAsyncSession intercepts PostgreSQL queries in memory for sub-second deterministic test runs without external network dependencies."),
        ("CI Quantitative Invariants", "Enforces IoP error <= 1.5%, zero false panel replacements on zoom, 100% SQL hit rate, and latency SLAs.")
    ]
    for h, b in adv_items:
        p_i = tf_r.add_paragraph()
        p_i.text = f"✔ {h}: "
        p_i.font.bold = True
        p_i.font.size = Pt(9.5)
        p_i.space_before = Pt(6)
        r = p_i.add_run()
        r.text = b
        r.font.bold = False
        r.font.color.rgb = TEXT_MUTED

    # =========================================================
    # SLIDE 15: Tech Stack & Production Architecture
    # =========================================================
    slide15 = prs.slides.add_slide(blank_layout)
    set_slide_background(slide15, NAVY_DARK)

    # Decorative Cyan Bar
    bar15 = slide15.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(0.8), Inches(1.2), Inches(0.08))
    bar15.fill.solid()
    bar15.fill.fore_color.rgb = CYAN_ACCENT
    bar15.line.fill.background()

    # Title
    t_box15 = slide15.shapes.add_textbox(Inches(1.2), Inches(1.0), Inches(11.0), Inches(0.8))
    tf15 = t_box15.text_frame
    p15 = tf15.paragraphs[0]
    p15.text = "Technology Stack & Production Summary"
    p15.font.name = FONT_TITLE
    p15.font.size = Pt(26)
    p15.font.bold = True
    p15.font.color.rgb = WHITE

    # 4 Cards on Dark
    stack_cards = [
        ("Core Backend", [
            ("Python 3.11 / 3.12", "Modern async runtime with type annotations"),
            ("FastAPI 0.115+", "High-performance async ASGI web framework"),
            ("Pydantic v2", "Strict DTO validation and JSON schema emission"),
            ("Decimal Library", "Statutory currency precision (zero float math)")
        ]),
        ("Database & Messaging", [
            ("PostgreSQL 16", "Async SQLAlchemy 2.0 with GIN JSONB indexing"),
            ("Redis 7", "Distributed in-flight locks (SET NX EX) & SSE events"),
            ("Unrepaired Ledger", "Partial unique indexes on (vin, part) for ESC-03"),
            ("S3 / MinIO", "Scratch video streaming & keyframe persistence")
        ]),
        ("Computer Vision & AI", [
            ("Ultralytics YOLO11", "YOLO11m-seg for vehicle & damage segmentation"),
            ("Shapely 2.0", "C-GEOS spatial polygon intersection engine"),
            ("FastEmbed ONNX", "Local MiniLM-L6-v2 zero-latency intent embeddings"),
            ("PySceneDetect & OpenCV", "Sub-100ms cut detection & visual quality gates")
        ]),
        ("VLM & Document Engine", [
            ("Google Gemini 2.5 Flash", "Cloud VLM with strict JSON constrained decoding"),
            ("Ollama miniCPM-V", "Local offline VLM adapter with circuit breaker"),
            ("HMAC-SHA256", "Cryptographic signing of claimant offer cards"),
            ("ReportLab 5.1", "Vector PDF certificates and surveyor dossiers")
        ])
    ]

    for i, (sc_title, sc_items) in enumerate(stack_cards):
        x = Inches(1.2 + i * 2.75)
        y = Inches(2.0)
        w = Inches(2.55)
        h = Inches(4.6)
        card = slide15.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, x, y, w, h)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(30, 41, 59)
        card.line.color.rgb = RGBColor(51, 65, 85)

        tb = slide15.shapes.add_textbox(x + Inches(0.2), y + Inches(0.2), w - Inches(0.4), h - Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True
        p0 = tf.paragraphs[0]
        p0.text = sc_title
        p0.font.name = FONT_TITLE
        p0.font.size = Pt(14)
        p0.font.bold = True
        p0.font.color.rgb = CYAN_ACCENT

        for tech, desc in sc_items:
            p = tf.add_paragraph()
            p.text = f"{tech}\n"
            p.font.name = FONT_TITLE
            p.font.size = Pt(10.5)
            p.font.bold = True
            p.font.color.rgb = WHITE
            p.space_before = Pt(12)
            
            run = p.add_run()
            run.text = desc
            run.font.name = FONT_BODY
            run.font.size = Pt(9)
            run.font.bold = False
            run.font.color.rgb = RGBColor(148, 163, 184)

    from pathlib import Path
    output_dir = Path(__file__).resolve().parent.parent / "docs" / "presentation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "Auto_Settle_AI_Executive_Presentation.pptx"
    prs.save(str(output_path))
    print(f"Presentation saved successfully to: {output_path}")

if __name__ == "__main__":
    create_presentation()
