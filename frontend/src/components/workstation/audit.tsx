"use client";

import { useMemo } from "react";
import type { ClaimDetail, ClaimEvent } from "@/lib/types";
import { Icon } from "@/components/icons";
import { inr, shortId, clockTime } from "@/lib/format";
import { useClaims } from "@/lib/store";

export interface AuditEntry {
  kind: "green" | "blue" | "amber" | "red";
  title: string;
  detail: string;
  time?: string;
  tag: string;
}

export function buildAuditEntries(detail: ClaimDetail, events: Array<ClaimEvent & { receivedAt?: string }>): AuditEntry[] {
  const t = detail.telemetry;
  const entries: AuditEntry[] = [];
  const evTime = (name: string) => events.find((e) => e.event === name)?.receivedAt;

  entries.push({
    kind: "blue",
    title: "Claim registered",
    detail: `Policy ${detail.policy_id} · media ingested and hashed (SHA-256 dedupe check).`,
    tag: "EVIDENCE",
  });

  const ff = t.fast_fail;
  if (ff) {
    entries.push({
      kind: ff.tier1_report?.passed ? "green" : "red",
      title: ff.tier1_report?.passed ? "Stage 0 fast-fail gate passed" : `Stage 0 gate stopped claim${detail.escalation_code ? ` · ${detail.escalation_code}` : ""}`,
      detail: ff.tier1_report?.passed
        ? `Policy active · ${ff.capture_modality === "PHOTO_PACK" ? `${ff.photo_metadata_report?.photo_count ?? "?"} photos validated` : "container & visual quality verified"}.`
        : `Failure codes: ${(detail.failure_codes ?? ff.tier1_report?.failure_codes ?? []).join(", ") || "—"}`,
      time: evTime("FAST_FAIL_GATE_PASSED"),
      tag: "PRE-CHECK",
    });
  }

  const vc = t.vehicle_continuity;
  if (vc) {
    const plate = vc.plate_report;
    entries.push({
      kind: vc.passed ? "green" : "red",
      title: vc.passed ? "Stage 1 identity & continuity verified" : `Stage 1 identity failure${vc.escalation_code ? ` · ${vc.escalation_code}` : ""}`,
      detail: [
        plate ? `ANPR plate ${plate.extracted_plate ?? "—"} vs ${plate.expected_plate} (${Math.round((plate.ocr_confidence ?? 0) * 100)}% OCR)` : null,
        vc.color_report ? `colour ${vc.color_report.is_color_match ? "matched" : "mismatch"} (${vc.color_report.expected_color_name})` : null,
        vc.cut_report ? `continuity ${vc.cut_report.is_continuous ? "continuous" : "cut detected"}` : null,
        vc.tracking_report ? `${vc.tracking_report.frames_tracked ?? 0} frames tracked` : null,
      ]
        .filter(Boolean)
        .join(" · "),
      time: evTime("STAGE_1_PASSED"),
      tag: "IDENTITY",
    });
  }

  const dm = t.dual_mask;
  if (dm) {
    const grounded = (dm.grounded_parts ?? []) as unknown[];
    entries.push({
      kind: "green",
      title: "Stage 2 dual-mask segmentation complete",
      detail: `${grounded.length} grounded damaged part${grounded.length === 1 ? "" : "s"} conditioned by claim intent.`,
      tag: "SEGMENTATION",
    });
  }

  const vlm = t.vlm_inspection;
  if (vlm) {
    const verified = vlm.verified_parts ?? [];
    entries.push({
      kind: verified.length ? "green" : "amber",
      title: "Stage 3 VLM damage inspection complete",
      detail: verified.length
        ? verified.map((p) => `${p.display_part_name?.replace(/_/g, " ")} (${(p.primary_damage_class ?? "damage").replace(/_/g, " ")}, ${p.depth_grade ?? "?"}, ${Math.round((p.vlm_confidence ?? 0) * 100)}% VLM)`).join(" · ")
        : "No parts passed forensic verification.",
      tag: "VLM",
    });
  }

  const est = t.actuarial_estimate;
  if (est) {
    entries.push({
      kind: est.is_ceiling_breached ? "red" : "green",
      title: est.is_ceiling_breached ? `Stage 4 pricing — ceiling breached${est.escalation_code ? ` · ${est.escalation_code}` : ""}` : "Stage 4 actuarial pricing complete",
      detail: est.is_ceiling_breached
        ? `Gross repair ${inr(est.summary.gross_garage_repair_inr)} exceeds the ₹25,000 autonomous ceiling.`
        : `Gross repair ${inr(est.summary.gross_garage_repair_inr)} · net liability ${inr(est.summary.net_claim_liability_inr)} · offer band ${inr(est.settlement_band.initial_offer_inr)}–${inr(est.settlement_band.walkaway_cap_inr)}.`,
      time: evTime("STAGE_4_PRICING_COMPLETED") ?? evTime("ACTUARIAL_PRICING_COMPLETED"),
      tag: "PRICING",
    });
  }

  const neg = t.negotiation_session;
  if (neg) {
    entries.push({
      kind: "green",
      title: "Initial offer card signed (HMAC-SHA256)",
      detail: `Opening offer ${inr(neg.active_offer_card.amount_inr)} · round ${neg.active_offer_card.round_num}.`,
      time: evTime("CLAIM_OFFER_READY"),
      tag: "OFFER",
    });
    for (const turn of neg.turns ?? []) {
      entries.push({
        kind: "blue",
        title: `Negotiation round ${turn.round_num} completed`,
        detail: `Claimant: “${turn.claimant_message.slice(0, 90)}${turn.claimant_message.length > 90 ? "…" : ""}” → offer ${inr(turn.offered_amount_inr)}.`,
        time: turn.timestamp,
        tag: "NEGOTIATION",
      });
    }
  }

  const voucher = t.settlement_voucher;
  if (voucher) {
    entries.push({
      kind: "green",
      title: "Settled — cash-in-lieu voucher disbursed",
      detail: `${inr(voucher.settled_amount_inr)} via UPI · ref ${voucher.disbursement_ref} · sig ${voucher.digital_signature_sha256.slice(0, 16)}…`,
      time: voucher.issued_at,
      tag: "SETTLED",
    });
  }

  if (detail.claim_status === "ROUTED_CASHLESS_GARAGE") {
    entries.push({
      kind: "amber",
      title: "Claim routed to cashless garage",
      detail: "Claimant opted for authorized network garage repair. Surveyor dossier compiled.",
      tag: "ROUTED",
    });
  } else if (detail.escalation_code && !voucher) {
    entries.push({
      kind: "amber",
      title: `Escalated · ${detail.escalation_code}`,
      detail: "Automated settlement stopped; human adjuster dossier compiled with forensic telemetry.",
      time: evTime("CLAIM_ESCALATED"),
      tag: "GUARDRAIL",
    });
  }

  return entries;
}

export function AuditTab({ claimId, detail }: { claimId: string; detail: ClaimDetail | null }) {
  const { eventsByClaim } = useClaims();
  const events = (eventsByClaim[claimId] ?? []) as unknown as ClaimEvent[];

  const entries = useMemo(() => (detail ? buildAuditEntries(detail, events) : []), [detail, events]);

  const downloadJson = async () => {
    if (!detail) return;
    const blob = new Blob([JSON.stringify({ detail, liveEvents: events }, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit_${shortId(claimId)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  if (!detail) {
    return (
      <div className="panel">
        <div className="empty-state">
          <h3>Fetching audit ledger…</h3>
          <p>Live claim state is being synced from the backend.</p>
        </div>
      </div>
    );
  }

  const voucher = detail.telemetry.settlement_voucher;
  const decision = voucher ? "Settled · cash-in-lieu" : detail.claim_status;

  return (
    <section className="panel audit-panel">
      <div className="panel-topline">
        <div>
          <p className="eyebrow">
            CLAIM {shortId(claimId)} · VERIFIED AUDIT LEDGER
          </p>
          <h2>Audit trail</h2>
          <p>A chronological record of evidence, assessment, offers, guardrails, and decision.</p>
        </div>
        <div className="audit-actions">
          <button type="button" className="button button-outline" onClick={() => window.print()}>
            <Icon name="print" /> Print / save PDF
          </button>
          <button type="button" className="button button-dark" onClick={downloadJson}>
            <Icon name="download" /> Download JSON
          </button>
        </div>
      </div>
      <div className="audit-summary-strip">
        <div>
          <span>CLAIM</span>
          <strong>{shortId(claimId)}</strong>
        </div>
        <div>
          <span>POLICY</span>
          <strong>{detail.policy_id}</strong>
        </div>
        <div>
          <span>RECORD</span>
          <strong>Cryptographic Ledger</strong>
        </div>
        <div>
          <span>DECISION</span>
          <strong>{decision}</strong>
        </div>
      </div>
      <div className="audit-timeline">
        {entries.map((e, i) => (
          <div className="audit-entry" key={i}>
            <span className={`audit-dot audit-dot-${e.kind}`} />
            <div className="audit-entry-body">
              <div className="audit-entry-top">
                <strong>{e.title}</strong>
                <span className="audit-entry-time">{e.time ? clockTime(e.time) : "—"}</span>
                <span className="audit-entry-tag">{e.tag}</span>
              </div>
              <p className="audit-entry-detail">{e.detail}</p>
            </div>
          </div>
        ))}
      </div>
      <p className="audit-integrity-note">
        <Icon name="info" /> Audit records are cryptographically verifiable, containing SHA-256 evidence hashes and HMAC-signed settlement
        bounds.
      </p>
    </section>
  );
}
