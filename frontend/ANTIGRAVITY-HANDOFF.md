# Antigravity handoff — Auto-Settle AI

## Build target

Use this repository as the implementation reference for a responsive claims-adjustment frontend. Preserve the existing interaction model and visual direction; improve or port the interface to your chosen production stack as needed. The current site is a real browser-only hackathon prototype, not a functioning insurance service. It has no backend, API routes, policy engine, computer-vision model, pricing database, payment flow, or durable storage.

The intended product supports minor motor claims from vehicle images/video through clear damage assessment, an itemized repair estimate, bounded cash-in-lieu negotiation, either a final settlement or safe human/garage handoff, and a readable audit record.

## Existing project map

- `index.html` — semantic app shell, nav, queue, claim workstation tabs, intake, guardrail catalog, standalone audit view, and local camera dialog.
- `src/styles.css` — design tokens, component styling, desktop/sidebar structure, mobile bottom navigation and single-column reflow, focus and reduced-motion states, and print layout.
- `src/app.js` — client-only view switching, example claim, image/video upload previews, browser camera recording, simulated negotiation, scenario switches, local decision state, and browser-generated JSON export.
- `assets/damage-evidence.svg` — original illustrative sample evidence view, with the dent location highlighted; it is an illustration, not a real claim photo.
- `README.md` — visual direction, reference links, run instructions, and prototype boundary.
- `TODO.md` — the sourced deliverable criteria and current completion status.
- `manus-routes.json` — current static page declaration (`/`). Views are client-side sections, not separate URL routes.

Run the prototype from the project root with `python3 -m http.server 3000 --bind 0.0.0.0`. The app deliberately uses browser APIs and local state only. Upload files do not leave the user's browser. The sample review is always illustrative.

## Screen map and user journey

1. **Overview / queue.** Summary counts and a recent claim queue lead into sample case `CLM-48291` or an intake flow.
2. **New claim / evidence intake.** Accept image or video files, preview locally, support drag/drop and optional browser-camera recording, and collect registration, model, incident date/location and narrative. The form explicitly tells users no server upload or automated analysis runs in this prototype.
3. **Claim review / assessment.** Show evidence, candidate damage area, identity/continuity checks, component, damage class, severity, confidence and minor/non-safety finding. The sample is a driver-side front-door L4 crease dent at 96% confidence.
4. **Repair estimate.** Show repair work, labour/materials, GST, deductible, net eligible amount, pricing basis and a 75% / 85% / 95% settlement window.
5. **Settlement conversation.** Show an initial offer, allow a counteroffer and optional explanation, make bounded counteroffers, prevent an out-of-range settlement, and provide accept, cashless garage, or human-review paths.
6. **Decision.** Display the accepted amount inside the band, a garage path with no cash payment, or an explicit escalation with reason and no unsupported payout.
7. **Audit trail.** Chronological evidence, assessment, guardrail, estimate, offer, counteroffer, block and decision entries. Browser-only JSON export and print-to-PDF are demonstrations, not persistent signed records.
8. **Guardrails.** Explain stop/re-record/handoff rules, current example checks, and interactive failure scenarios.

## Fixed sample economics and interaction states

Keep the displayed sample math internally consistent unless the product/policy owner changes the rate card:

- Repair line items: ₹3,000 denting/alignment + ₹4,500 full-panel repaint + ₹1,500 materials = ₹9,000 subtotal.
- GST ₹1,620; garage estimate ₹10,620.
- Deductible ₹620; net eligible amount ₹10,000.
- Opening offer ₹7,500 (75%); target ₹8,500 (85%); automated offer ceiling ₹9,500 (95%).
- Autonomous repair-cost ceiling: ₹25,000 net repair cost.
- A customer request above ₹9,500 must never become an automated settlement. Explain the boundary and offer acceptance of the current in-range amount, a garage path, or human review.
- Any settlement outside the approved ₹7,500–₹9,500 band is blocked in the UI demo. A UI-level check is only illustrative; do not treat it as production authorization.
- The negotiation prototype allows up to three bounded counteroffer rounds, with an optional explanation affecting the mock concession. The displayed guardrail never widens.

## Guardrail/handoff catalog

Preserve clear user-facing outcomes for the currently represented rules:

- **ESC-00 — capture/policy pre-check:** expired policy, supported capture-duration/resolution issue, poor lighting/sharpness, or edit metadata → request re-record / correct capture.
- **ESC-01 — vehicle/plate mismatch:** block offer and route to human/fraud review; do not accuse the claimant.
- **ESC-02 — broken continuity or scene cut:** do not link evidence frames automatically; request one unbroken live capture.
- **ESC-03 — previously paid, unrepaired part:** pause and require repair proof or adjuster review.
- **ESC-04 — possible old rust/oxidation:** treat as uncertainty, not a fraud conclusion; human review.
- **ESC-05 — impacts on opposite vehicle sides:** clarify whether there are multiple incidents; separate claims/review.
- **ESC-06 — safety-critical or hidden damage:** no cash-in-lieu offer; physical garage inspection.
- **ESC-07 — confidence below 55%:** ask for clearer evidence if it can resolve the uncertainty, otherwise a human desk adjuster.
- **ESC-08 — net repair estimate above ₹25,000:** stop autonomous negotiation and route to a licensed surveyor.

## Visual and interaction direction

Continue the calm editorial utility aesthetic already in the prototype: mineral-white surfaces, ink text, muted green as the ownable action color, and amber/red only for caution/hard stops. Use the existing `DM Sans` + `Newsreader` + `IBM Plex Mono` pairing and hierarchy: editorial serif for a few large headings and amounts, clean sans for product/UI copy, monospace for claim identifiers and policy labels. Favor aligned information, open whitespace, legible tables, hairline dividers, unambiguous status chips and plain-language explanations. Do not revert to violet gradient hero art, excessive glassmorphism, generic AI sparkle motifs, blurry glow backgrounds, unexplained floating orbs, or card tiles for every line of content.

On narrow screens, keep each step readable as one column, allow evidence/table overflow locally rather than page-level overflow, provide mobile bottom navigation, retain a visible offer ceiling, and keep touch controls practical. Status must remain understandable without color alone. Preserve keyboard focus styles, semantic controls/labels, useful image alternative text, reduced-motion support and print-friendly audit output.

## Extension boundary

When turning this into a real product, connect each displayed value/state to the approved policy, parts/labour rate-card and claim-workflow authority; do not let presentation-layer copy or a browser calculation approve a real payout. Implement actual identity, evidence provenance, tamper detection, fraud review, safety triage, decision recording, consent, notifications, payment/garage handoff, retention and audit integrity outside this static interface. Derive the design from approved operations and jurisdictional policy rather than assuming the demo values are binding.


## Damage grade labels

Keep the five source severity labels in the assessment experience and use the active grade to focus—not hide—the rest of the scale:

- **L1** — Surface scuff
- **L2** — Basecoat scratch
- **L3** — Shallow dent / paintless dent repair (PDR)
- **L4** — Creased dent
- **L5** — Structural tear / crack

The sample demonstrates L4. A visible numeric confidence must not be presented as proof that a claim is genuine or eligible; retain evidence uncertainty and safe escalation states.
