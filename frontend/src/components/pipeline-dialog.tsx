"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useClaims } from "@/lib/store";
import type { ClaimDetail } from "@/lib/types";
import { statusMeta } from "@/lib/format";
import { Icon } from "./icons";

const STAGES = [
  "Stage 0: Dual-Modality Perimeter Fast-Fail Gate",
  "Stage 1: Vehicle Identity & Continuity Grounding (ANPR + ByteTrack)",
  "Stage 2: Intent Grounding & Conditioned Dual-Mask Segmentation",
  "Stage 3: Set-of-Marks VLM Depth & Pre-Existing Rust Gate",
  "Stage 4: Deterministic Actuarial OEM Pricing & NCB Advisory",
  "Stage 5: Bounded FSM Negotiation & Cryptographic HMAC Signing",
];

type StepState = "pending" | "active" | "done" | "failed";

interface Props {
  open: boolean;
  claimId: string;
  onClose: () => void;
  onContinue: () => void;
}

export function PipelineDialog({ open, claimId, onClose, onContinue }: Props) {
  const { recordEvent, refreshClaim } = useClaims();
  const [detail, setDetail] = useState<ClaimDetail | null>(null);
  const [eventsSeen, setEventsSeen] = useState<string[]>([]);
  const esRef = useRef<EventSource | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (!open || !claimId) return;

    setDetail(null);
    setEventsSeen([]);

    // SSE subscription for real-time stage events
    try {
      const es = new EventSource(`/api/v1/claims/${claimId}/events`);
      esRef.current = es;
      es.onmessage = (msg) => {
        try {
          const parsed = JSON.parse(msg.data) as { event?: string };
          if (parsed.event) {
            setEventsSeen((prev) => (prev.includes(parsed.event!) ? prev : [...prev, parsed.event!]));
            recordEvent(claimId, { event: parsed.event!, claim_id: claimId, data: parsed as Record<string, unknown> });
          }
        } catch {
          /* non-JSON heartbeat */
        }
      };
      es.onerror = () => {
        es.close();
        esRef.current = null;
      };
    } catch {
      /* EventSource unsupported */
    }

    // Poll claim status as the source of truth
    const poll = async () => {
      const d = await refreshClaim(claimId);
      if (d) setDetail(d);
    };
    void poll();
    pollRef.current = setInterval(poll, 2200);

    return () => {
      esRef.current?.close();
      esRef.current = null;
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = null;
    };
  }, [open, claimId, refreshClaim, recordEvent]);

  const { steps, terminal, ok } = useMemo(() => computeSteps(detail), [detail]);

  const progress = (steps.filter((s) => s === "done").length / STAGES.length) * 100;

  if (!open) return null;

  const meta = detail ? statusMeta(detail.claim_status, detail.escalation_code) : null;

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="Pipeline progress">
      <div className="pipeline-dialog" style={{ margin: "auto" }}>
        <div className="pipeline-head">
          <div>
            <p className="eyebrow">AUTONOMOUS CLAIMS PIPELINE</p>
            <h2>{terminal ? (ok ? "Claim ready for settlement" : meta?.label ?? "Pipeline stopped") : "Processing Claim Evidence"}</h2>
          </div>
          <span className={`demo-tag ${terminal && !ok ? "" : ""}`} style={terminal && !ok ? { color: "var(--red)", background: "var(--redbg)" } : undefined}>
            {terminal ? (ok ? "COMPLETED" : "STOPPED") : "RUNNING"}
          </span>
        </div>
        <div className="pipeline-body">
          <p className="pipeline-desc">
            {terminal
              ? ok
                ? "All 6 pipeline stages completed. Initial Offer Card generated and cryptographically signed."
                : `Pipeline stopped: ${meta?.description ?? "escalation"}${detail?.failure_codes?.length ? ` (${detail.failure_codes.join(", ")})` : ""}`
              : "Executing perimeter forensics, continuity tracking, dual-mask segmentation, and OEM pricing calculation."}
          </p>
          <div className="pipeline-progress-bar">
            <div className="pipeline-progress-fill" style={{ width: `${progress}%` }} />
          </div>
          <div className="pipeline-steps">
            {STAGES.map((label, i) => (
              <div key={label} className={`pipeline-step ${steps[i]}`}>
                <span className="pipeline-step-dot">{steps[i] === "done" ? "✓" : steps[i] === "failed" ? "!" : i}</span>
                <span>{label}</span>
                {eventsSeen.includes(stageDoneEvent(i)) && steps[i] === "done" && (
                  <span style={{ marginLeft: "auto", fontSize: "var(--font-2xs)", color: "var(--green)" }}>LIVE</span>
                )}
              </div>
            ))}
          </div>
          {detail?.escalation_code && terminal && !ok && (
            <div className="finding-note" style={{ marginTop: 14 }}>
              <Icon name="info" />
              <p>
                <b>{detail.escalation_code}</b> — routed to the escalation path. Open the claim to review the adjuster dossier and forensic
                telemetry.
              </p>
            </div>
          )}
          <div className="dialog-actions" style={{ marginTop: 20, padding: 0 }}>
            {terminal && ok && (
              <button className="button button-green" type="button" onClick={onContinue}>
                Open in Claim Workstation <span>→</span>
              </button>
            )}
            <button className="button button-outline" type="button" onClick={terminal ? onContinue : onClose}>
              {terminal ? "Close" : "Run in background"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function stageDoneEvent(i: number): string {
  return ["FAST_FAIL_GATE_PASSED", "STAGE_1_PASSED", "STAGE_2_PASSED", "STAGE_3_PASSED", "STAGE_4_PRICING_COMPLETED", "CLAIM_OFFER_READY"][i];
}

function computeSteps(detail: ClaimDetail | null): { steps: StepState[]; terminal: boolean; ok: boolean } {
  const steps: StepState[] = ["pending", "pending", "pending", "pending", "pending", "pending"];
  if (!detail) return { steps, terminal: false, ok: false };

  const status = detail.claim_status.toUpperCase();
  const stageOrder = ["STAGE_0_SANITY", "STAGE_1_IDENTITY", "STAGE_2_SEGMENTATION", "STAGE_3_VLM_INSPECTION", "STAGE_4_ACTUARIAL_PRICING", "STAGE_5_NEGOTIATION", "STAGE_6_SETTLEMENT"];
  const reachedIdx = stageOrder.indexOf(detail.current_stage.toUpperCase());

  const failedEarly = status.startsWith("REJECTED");
  if (failedEarly) {
    const failStage = status.includes("FAST_FAIL") || status.includes("STAGE0") ? 0 : reachedIdx >= 0 ? reachedIdx : 0;
    for (let i = 0; i < failStage; i++) steps[i] = "done";
    steps[failStage] = "failed";
    return { steps, terminal: true, ok: false };
  }

  const terminalOk = ["PRICED_READY_FOR_NEGOTIATION", "SETTLED_CASH_IN_LIEU"].includes(status);
  const terminalStop = ["ESCALATED", "ESCALATED_HUMAN_REVIEW", "ROUTED_CASHLESS_GARAGE"].includes(status) || !!detail.escalation_code;

  if (terminalOk || terminalStop) {
    // Determine how far the pipeline got from telemetry presence
    const t = detail.telemetry;
    let reached = 0;
    if (t.fast_fail) reached = 1;
    if (t.vehicle_continuity) reached = 2;
    if (t.dual_mask) reached = 3;
    if (t.vlm_inspection) reached = 4;
    if (t.actuarial_estimate) reached = 5;
    if (t.negotiation_session || status === "PRICED_READY_FOR_NEGOTIATION") reached = 6;
    for (let i = 0; i < Math.min(reached, 6); i++) steps[i] = "done";
    if (terminalStop) {
      const stopAt = reached >= 6 ? 5 : Math.max(0, reached - 1);
      steps[stopAt] = "failed";
      for (let i = stopAt + 1; i < 6; i++) steps[i] = "pending";
    }
    return { steps, terminal: true, ok: terminalOk };
  }

  // In flight
  if (reachedIdx >= 0) {
    for (let i = 0; i < reachedIdx; i++) steps[i] = "done";
    steps[reachedIdx] = "active";
  } else {
    steps[0] = "active";
  }
  return { steps, terminal: false, ok: false };
}
