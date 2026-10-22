"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AdjusterDossier, ClaimDetail } from "@/lib/types";
import { Icon } from "@/components/icons";
import { inr, shortId } from "@/lib/format";
import { ruleFor } from "@/lib/rules";

export function DecisionTab({ claimId, detail, onBackToSettlement }: { claimId: string; detail: ClaimDetail | null; onBackToSettlement: () => void }) {
  const [dossier, setDossier] = useState<AdjusterDossier | null>(null);
  const voucher = detail?.telemetry.settlement_voucher ?? null;

  useEffect(() => {
    const needsDossier = !!detail && !voucher && (detail.claim_status.startsWith("ESCALATED") || detail.claim_status === "ROUTED_CASHLESS_GARAGE" || !!detail.escalation_code);
    if (!needsDossier) return;
    api
      .getDossier(claimId)
      .then(setDossier)
      .catch(() => setDossier(null));
  }, [claimId, detail, voucher]);

  if (voucher) {
    return (
      <div className="decision-wrap">
        <div className="voucher-card">
          <div className="voucher-head">
            <div>
              <span className="small-caps" style={{ color: "rgba(255,255,255,0.8)" }}>
                SETTLEMENT CERTIFICATE · {voucher.voucher_id}
              </span>
              <h2>Cash-in-lieu settled</h2>
            </div>
            <div style={{ textAlign: "right" }}>
              <span className="small-caps" style={{ color: "rgba(255,255,255,0.8)" }}>
                DISBURSED
              </span>
              <div className="settled-amount">{inr(voucher.settled_amount_inr)}</div>
            </div>
          </div>
          <div className="voucher-body">
            <p style={{ color: "var(--muted)", fontSize: "var(--font-sm)", marginTop: 0 }}>
              {voucher.settled_amount_words}
            </p>
            <div className="voucher-grid">
              <div>
                <span>Claim</span>
                <code>{shortId(voucher.claim_id)}</code>
              </div>
              <div>
                <span>Policy</span>
                <code>{voucher.policy_id}</code>
              </div>
              <div>
                <span>Vehicle</span>
                <code>
                  {voucher.vehicle_make_model} · {voucher.registration_number}
                </code>
              </div>
              <div>
                <span>UPI beneficiary</span>
                <code>{voucher.beneficiary_upi_id ?? "registered policy mobile"}</code>
              </div>
              <div>
                <span>Disbursement ref</span>
                <code>{voucher.disbursement_ref}</code>
              </div>
              <div>
                <span>Digital signature</span>
                <code>{voucher.digital_signature_sha256.slice(0, 24)}…</code>
              </div>
            </div>
            {voucher.apportioned_parts?.length > 0 && (
              <>
                <p className="small-caps" style={{ marginBottom: 8 }}>
                  APPORTIONED PART PAYOUTS
                </p>
                <div className="damage-items-list" style={{ marginBottom: 14 }}>
                  {voucher.apportioned_parts.map((p) => (
                    <div className="damage-item-card" key={p.canonical_part_key}>
                      <span>
                        <b>{p.display_part_name?.replace(/_/g, " ")}</b>
                      </span>
                      <strong style={{ color: "var(--green2)" }}>{inr(p.apportioned_amount_inr)}</strong>
                    </div>
                  ))}
                </div>
              </>
            )}
            <div className="offer-actions">
              <a className="button button-dark" href={api.voucherPdfUrl(claimId)} target="_blank" rel="noreferrer">
                <Icon name="download" /> Download PDF certificate
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (dossier) {
    const rule = ruleFor(dossier.escalation_code);
    return (
      <div className="decision-wrap">
        <div className="dossier-card">
          <div className="dossier-head">
            <div>
              <span className="small-caps">
                HUMAN ADJUSTER DOSSIER · {dossier.dossier_id}
              </span>
              <h2>{dossier.escalation_code} — routed for human review</h2>
            </div>
          </div>
          <div className="dossier-body">
            <p style={{ color: "var(--ink)", fontWeight: 600, margin: "0 0 6px" }}>{dossier.escalation_reason}</p>
            <p style={{ color: "var(--muted)", fontSize: "var(--font-sm)" }}>
              <b>Recommended action:</b> {dossier.recommended_surveyor_action}
            </p>
            {rule && (
              <p style={{ color: "var(--muted)", fontSize: "var(--font-sm)" }}>
                <b>Rule:</b> {rule.title} — {rule.outcomeTitle}.
              </p>
            )}
            {dossier.surveyor_checklist.length > 0 && (
              <>
                <p className="small-caps" style={{ margin: "14px 0 8px" }}>
                  SURVEYOR CHECKLIST
                </p>
                <ul className="checklist">
                  {dossier.surveyor_checklist.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            )}
            <div className="offer-actions" style={{ marginTop: 16 }}>
              <a className="button button-dark" href={api.dossierPdfUrl(claimId)} target="_blank" rel="noreferrer">
                <Icon name="download" /> Download dossier PDF
              </a>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (detail?.claim_status.startsWith("REJECTED")) {
    return (
      <div className="decision-wrap">
        <div className="decision-empty">
          <span className="decision-icon" style={{ background: "var(--redbg)", color: "var(--red)" }}>
            <Icon name="shield" size={22} />
          </span>
          <p className="eyebrow">FINAL OUTCOME</p>
          <h2>Rejected at the gate.</h2>
          <p>
            {detail.escalation_code ?? "ESC-00"} — {(detail.failure_codes ?? []).join(", ") || "evidence pre-checks failed"}. The claimant can
            re-capture evidence and resubmit.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="decision-wrap">
      <div className="decision-empty">
        <span className="decision-icon">
          <Icon name="file" size={22} />
        </span>
        <p className="eyebrow">FINAL OUTCOME</p>
        <h2>No decision yet.</h2>
        <p>Review the evidence and offer conversation. An accepted cash offer or a human escalation will appear here with the next steps.</p>
        <button type="button" className="button button-green" onClick={onBackToSettlement}>
          Continue settlement <span>→</span>
        </button>
      </div>
    </div>
  );
}
