"use client";

import type { ClaimDetail } from "@/lib/types";
import { statusMeta, type ClaimPhase } from "@/lib/format";

export function StatusTag({ detail }: { detail: ClaimDetail | null }) {
  if (!detail) {
    return (
      <span className="status-tag status-processing">
        <i /> Registered
      </span>
    );
  }
  const meta = statusMeta(detail.claim_status, detail.escalation_code);
  const cls: Record<ClaimPhase, string> = {
    processing: "status-processing",
    ready: "status-ready",
    settled: "status-paid",
    escalated: "status-review",
    rejected: "status-error",
    garage: "status-review",
  };
  return (
    <span className={`status-tag ${cls[meta.phase]}`}>
      <i />
      {meta.label}
    </span>
  );
}
