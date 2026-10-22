"use client";

import { useMemo, useState } from "react";
import type { ClaimDetail } from "@/lib/types";
import { Icon } from "@/components/icons";
import { inr } from "@/lib/format";
import { SEVERITY_SCALE, depthToSeverity } from "@/lib/rules";

type MediaMode = "video" | "yolo" | "som";

export function AssessmentTab({
  claimId,
  detail,
  localVideoUrl,
  onOpenSettlement,
}: {
  claimId: string;
  detail: ClaimDetail | null;
  localVideoUrl?: string;
  onOpenSettlement?: () => void;
}) {
  const [mode, setMode] = useState<MediaMode>("video");

  const vlm = detail?.telemetry.vlm_inspection ?? null;
  const verified = vlm?.verified_parts ?? [];
  const quarantined = vlm?.quarantined_parts ?? [];
  const dual = detail?.telemetry.dual_mask;
  const grounded = (dual?.grounded_parts ?? []) as unknown as Array<Record<string, unknown>>;
  const primary = verified[0];

  const severity = depthToSeverity(primary?.depth_grade);
  const confidence = primary ? Math.round(((primary.damage_confidence ?? primary.vlm_confidence ?? 0.9) as number) * 100) : null;
  const iop = primary?.iop_percentage;

  const cont = detail?.telemetry.vehicle_continuity;
  const checks = useMemo(
    () => [
      {
        label: cont?.cut_report ? (cont.cut_report.is_continuous ? "Video continuity passed" : "Continuity broken — cut detected") : "Continuity pending",
        ok: cont?.cut_report ? cont.cut_report.is_continuous : null,
      },
      {
        label: cont?.plate_report ? (cont.plate_report.is_verified ? `Plate & vehicle match (${cont.plate_report.extracted_plate ?? cont.plate_report.expected_plate})` : "Plate mismatch") : "ANPR plate check pending",
        ok: cont?.plate_report ? cont.plate_report.is_verified : null,
      },
      {
        label: cont?.color_report ? (cont.color_report.is_color_match ? `Colour matched (${cont.color_report.expected_color_name})` : "Colour mismatch") : "Colour grounding pending",
        ok: cont?.color_report ? cont.color_report.is_color_match : null,
      },
    ],
    [cont],
  );

  const est = detail?.telemetry.actuarial_estimate;
  const band = est?.settlement_band;

  const billed = verified.filter((p) => (p.claim_status ?? "CLAIMED") === "CLAIMED" || p.is_claimed !== false);

  const videoSrc = localVideoUrl ?? sampleVideoFor(claimId);

  return (
    <div className="assessment-layout">
      <div className="assessment-main">
        <section className="panel evidence-panel">
          <div className="panel-topline evidence-topline">
            <div>
              <div className="title-inline">
                <h2>Evidence review</h2>
                {cont?.plate_report?.is_verified && (
                  <span className="verified-tag">
                    <Icon name="check" /> Identity verified
                  </span>
                )}
              </div>
              <p>
                {detail?.telemetry.fast_fail?.capture_modality === "PHOTO_PACK"
                  ? `Photo pack · ${detail.telemetry.fast_fail?.photo_metadata_report?.photo_count ?? "—"} photos`
                  : "Continuous walkaround video evidence"}
              </p>
            </div>
          </div>
          <div className="media-switcher">
            <button className={`media-tab ${mode === "video" ? "is-active" : ""}`} type="button" onClick={() => setMode("video")}>
              <Icon name="play" /> {detail?.telemetry.fast_fail?.capture_modality === "PHOTO_PACK" ? "Photo pack" : "Walkaround video"}
            </button>
            <button className={`media-tab ${mode === "yolo" ? "is-active" : ""}`} type="button" onClick={() => setMode("yolo")}>
              <Icon name="spark" /> Dual-mask YOLO
            </button>
            <button className={`media-tab ${mode === "som" ? "is-active" : ""}`} type="button" onClick={() => setMode("som")}>
              <Icon name="shield" /> Set-of-Marks VLM
            </button>
          </div>
          <figure className="evidence-figure" style={{ margin: 0 }}>
            {mode === "video" ? (
              localVideoUrl ? (
                <video className="media-video-element" src={localVideoUrl} controls loop playsInline muted />
              ) : (
                <div className="evidence-placeholder">
                  <Icon name="video" size={30} />
                  <span>Original evidence stream lives on object storage.</span>
                  <span style={{ fontSize: "var(--font-2xs)", opacity: 0.7 }}>Frame telemetry &amp; keyframes verified below.</span>
                </div>
              )
            ) : mode === "yolo" ? (
              grounded.length || verified.length ? (
                <DualMaskCanvas parts={verified.length ? verified : (grounded as never)} />
              ) : (
                <div className="evidence-placeholder">
                  <Icon name="spark" size={30} />
                  <span>{dual ? "No grounded damage masks for this claim." : "Dual-mask segmentation pending…"}</span>
                </div>
              )
            ) : primary?.visual_reasoning_short ? (
              <div className="vlm-reasoning">
                <div className="vlm-reasoning-head">
                  <Icon name="eye" /> Qwen2-VL · Set-of-Marks Inspection
                </div>
                <p>{primary.visual_reasoning_short}</p>
                <div className="vlm-facts">
                  <div>
                    <span>Depth grade</span>
                    <b>{primary.depth_grade}</b>
                  </div>
                  <div>
                    <span>VLM confidence</span>
                    <b>{Math.round((primary.vlm_confidence ?? 0) * 100)}%</b>
                  </div>
                  <div>
                    <span>Closeup keyframe</span>
                    <b>{(primary as { vlm_closeup_keyframe?: string }).vlm_closeup_keyframe ?? "—"}</b>
                  </div>
                </div>
              </div>
            ) : (
              <div className="evidence-placeholder">
                <Icon name="shield" size={30} />
                <span>Set-of-Marks VLM inspection pending…</span>
              </div>
            )}
          </figure>
          <div className="evidence-meta" style={{ marginTop: 12 }}>
            {checks.map((c) => (
              <span key={c.label}>
                {c.ok == null ? <span className="meta-x">•</span> : c.ok ? <Icon name="check" /> : <span className="meta-x" style={{ color: "var(--red)" }}>✕</span>}
                {c.label}
              </span>
            ))}
          </div>
        </section>

        <section className="panel damage-panel">
          <div className="panel-topline">
            <div>
              <h2>Damage assessment</h2>
              <p>Dual-model YOLO inference conditioned by claim intent</p>
            </div>
            {confidence != null && (
              <span className="confidence-chip">
                <span className="confidence-dot" /> {confidence}% confidence
              </span>
            )}
          </div>
          {primary ? (
            <>
              <div className="damage-summary">
                <div className="damage-type-icon">
                  <Icon name="car" />
                </div>
                <div className="damage-copy">
                  <strong>{(primary.primary_damage_class ?? "damage").replace(/_/g, " ")}</strong>
                  <span>
                    {primary.display_part_name?.replace(/_/g, " ")} <b>·</b> {primary.part_material ?? "panel"}
                  </span>
                </div>
                <span className="severity-chip">
                  {severity} · {SEVERITY_SCALE.find((s) => s.grade === severity)?.label ?? "damage"}
                </span>
              </div>
              <div className="severity-scale">
                <span className="severity-scale-label">DAMAGE SCALE</span>
                {SEVERITY_SCALE.map((s) => (
                  <span key={s.grade} className={s.grade === severity ? "is-current" : ""}>
                    <b>{s.grade}</b>
                    <small>{s.label}</small>
                  </span>
                ))}
              </div>
              <div className="assessment-metrics">
                <div>
                  <span>Damage coverage</span>
                  <strong>
                    {iop != null ? `${typeof iop === "number" ? iop.toFixed(1) : iop}%` : "—"} <small>of panel</small>
                  </strong>
                </div>
                <div>
                  <span>Persistence</span>
                  <strong>
                    {primary.persistence_frame_count ?? "—"} <small>tracked frames</small>
                  </strong>
                </div>
                <div>
                  <span>Safety critical</span>
                  <strong className={primary.is_safety_critical ? "" : "good-text"}>
                    {primary.is_safety_critical ? "Yes — escalate" : "Non-safety"}
                  </strong>
                </div>
              </div>
              {primary.visual_reasoning_short && (
                <div className="finding-note">
                  <Icon name="info" />
                  <p>{primary.visual_reasoning_short}</p>
                </div>
              )}
            </>
          ) : (
            <div className="empty-state" style={{ padding: "28px 16px" }}>
              <h3>{detail ? "No verified damage yet" : "Assessment pending"}</h3>
              <p>
                {detail
                  ? "The pipeline has not grounded any damaged parts for this claim. Check the audit trail for stage outcomes."
                  : "The autonomous pipeline is still evaluating this evidence."}
              </p>
            </div>
          )}
        </section>

        <section className="panel quarantine-panel">
          <div className="panel-topline">
            <div>
              <p className="eyebrow">STAGE 2 INTENT-CONDITIONED SEGMENTATION</p>
              <h2>Damage quarantine engine</h2>
              <p>Distinguishing admitted claim defects from pre-existing road wear</p>
            </div>
            <span className="quarantine-chip">
              <Icon name="shield" /> Intent Filter Active
            </span>
          </div>
          <div className="quarantine-grid">
            <div className="quarantine-col billed">
              <div className="col-head">
                <Icon name="check" /> <strong>Billed Claim Items (Admitted)</strong>
                <span className="badge">{billed.length}</span>
              </div>
              <div className="damage-items-list">
                {billed.length ? (
                  billed.map((p, i) => (
                    <div className="damage-item-card" key={p.canonical_part_key ? `${p.canonical_part_key}-${i}` : `billed-${i}`}>
                      <span>
                        <b>{p.display_part_name?.replace(/_/g, " ")}</b>
                        <br />
                        <small style={{ color: "var(--muted)" }}>
                          {(p.primary_damage_class ?? "damage").replace(/_/g, " ")}
                          {p.iop_percentage != null ? ` · ${typeof p.iop_percentage === "number" ? p.iop_percentage.toFixed(1) : p.iop_percentage}% IoP` : ""}
                        </small>
                      </span>
                      <strong style={{ color: "var(--green2)" }}>
                        {est?.line_items?.find((l) => l.canonical_part_key === p.canonical_part_key)
                          ? inr(est.line_items.find((l) => l.canonical_part_key === p.canonical_part_key)!.gross_line_item_total_inr)
                          : ""}
                      </strong>
                    </div>
                  ))
                ) : (
                  <div className="damage-item-empty">No admitted items yet.</div>
                )}
              </div>
            </div>
            <div className="quarantine-col quarantined">
              <div className="col-head">
                <Icon name="lock" /> <strong>Pre-Existing Wear (Quarantined)</strong>
                <span className="badge">{quarantined.length}</span>
              </div>
              <div className="damage-items-list">
                {quarantined.length ? (
                  quarantined.map((p, i) => (
                    <div className="damage-item-card" key={(p.display_part_name as string) ?? i}>
                      <span>
                        <b>{(p.display_part_name as string)?.replace(/_/g, " ") ?? "Unclaimed wear"}</b>
                        <br />
                        <small style={{ color: "var(--muted)" }}>{(p.reason as string) ?? "Background wear · Bypasses ESC-05"}</small>
                      </span>
                      <span style={{ fontSize: 10, color: "var(--muted)" }}>Quarantined</span>
                    </div>
                  ))
                ) : (
                  <div className="damage-item-empty">Nothing quarantined.</div>
                )}
              </div>
            </div>
          </div>
          <div className="quarantine-note">
            <Icon name="info" />
            <span>
              Unclaimed background damage is quarantined to UNCLAIMED_PREEXISTING_DAMAGE and logged to the ledger without false fraud flags.
            </span>
          </div>
        </section>
      </div>

      <aside className="assessment-side">
        <section className="offer-card">
          <div className="offer-card-head">
            <span className="small-caps">CASH-IN-LIEU OFFER</span>
            <Icon name="lock" />
          </div>
          <p className="offer-label">Opening offer</p>
          <div className="offer-amount">{band ? inr(band.initial_offer_inr) : "—"}</div>
          <p className="offer-small">Your customer can accept this amount or make a counteroffer.</p>
          {band && <RangeMeter initial={parseFloat(band.initial_offer_inr)} cap={parseFloat(band.walkaway_cap_inr)} target={parseFloat(band.target_settlement_inr)} />}
          <div className="offer-limit">
            <span>Approved range</span>
            <strong>
              {band ? `${inr(band.initial_offer_inr)} — ${inr(band.walkaway_cap_inr)}` : "—"}
            </strong>
          </div>
          <div className="offer-limit offer-limit-soft">
            <span>Autonomous cap</span>
            <strong>{band ? inr(band.financial_ceiling_inr) : "₹25,000"}</strong>
          </div>
          <button className="button button-light button-full" type="button" onClick={onOpenSettlement} style={{ marginTop: 10 }}>
            Open settlement chat <span>→</span>
          </button>
          <p className="offer-lock-note">
            <Icon name="shield" /> Offer is locked to the approved range
          </p>
        </section>

        <section className="guardrail-card">
          <div className="guardrail-title">
            <Icon name="shield" />
            <strong>{detail?.escalation_code ? "Guardrail triggered" : "Guardrails passed"}</strong>
            <span className={`mini-check ${detail?.escalation_code ? "failed" : ""}`}>{detail?.escalation_code ? "!" : "✓"}</span>
          </div>
          <ul>
            <GuardRow ok={detail?.telemetry.fast_fail != null} label="Fast-fail pre-check" />
            <GuardRow ok={cont?.passed ?? null} label="Vehicle identity matched" />
            <GuardRow ok={detail?.telemetry.dual_mask ? true : null} label="Dual-mask segmentation" />
            <GuardRow ok={primary ? (primary.is_safety_critical ? false : true) : null} label="Minor, non-safety damage" />
            <GuardRow ok={est ? !est.is_ceiling_breached : null} label="Within ₹25,000 ceiling" />
          </ul>
        </section>

        <section className="compact-audit">
          <div className="compact-audit-head">
            <span className="small-caps">LATEST ACTIVITY</span>
          </div>
          <p>
            <span className={`audit-dot ${detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION" ? "audit-dot-green" : "audit-dot-blue"}`} />
            <span>
              <strong>{detail ? STAGE_LABELS_SHORT(detail) : "Awaiting pipeline"}</strong>
              <small>{detail ? `Stage: ${detail.current_stage}` : "Connecting…"}</small>
            </span>
          </p>
          <p>
            <span className="audit-dot audit-dot-blue" />
            <span>
              <strong>Claim registered</strong>
              <small>{detail?.telemetry.fast_fail ? "Fast-fail gate executed" : "Pending"}</small>
            </span>
          </p>
        </section>
      </aside>
    </div>
  );
}

function GuardRow({ ok, label }: { ok: boolean | null; label: string }) {
  return (
    <li>
      <i className={`guardrail-check ${ok === false ? "failed" : ""}`}>{ok === null ? "•" : ok ? "✓" : "✕"}</i>
      {label}
    </li>
  );
}

function STAGE_LABELS_SHORT(detail: ClaimDetail): string {
  const s = detail.claim_status;
  if (s === "PRICED_READY_FOR_NEGOTIATION") return "Offer ready";
  if (s === "SETTLED_CASH_IN_LIEU") return "Settled & disbursed";
  if (s.startsWith("ESCALATED") || detail.escalation_code) return detail.escalation_code ? `Escalated · ${detail.escalation_code}` : "Escalated";
  if (s.startsWith("REJECTED")) return "Rejected at gate";
  return "Pipeline running";
}

export function RangeMeter({ initial, target, cap }: { initial: number; target: number; cap: number }) {
  const pct = (v: number) => (cap > 0 ? Math.min(100, Math.max(0, (v / cap) * 100)) : 0);
  return (
    <div className="range-meter" aria-label="Offer range">
      <div className="range-line">
        <span className="range-fill" style={{ width: `${pct(initial)}%` }} />
        <i className="range-point point-start" />
        <i className="range-point point-target" style={{ left: `${pct(target)}%` }} />
        <i className="range-point point-cap" />
      </div>
      <div className="range-labels">
        <span>
          <b>75%</b>Start
        </span>
        <span>
          <b>85%</b>Target
        </span>
        <span>
          <b>95%</b>Cap
        </span>
      </div>
    </div>
  );
}

function sampleVideoFor(claimId: string): string | undefined {
  return undefined;
}

// Simple SVG dual-mask visualization derived from grounded parts (no pixel data available client-side)
function DualMaskCanvas({ parts }: { parts: Array<{ display_part_name?: string; iop_percentage?: number; canonical_part_key: string }> }) {
  const rows = parts.slice(0, 4);
  return (
    <div className="dualmask-viz">
      <div className="dualmask-head">
        <Icon name="spark" /> Intent-conditioned dual masks · {parts.length} grounded
      </div>
      {rows.map((p, i) => {
        const iop = typeof p.iop_percentage === "number" ? p.iop_percentage : 50;
        return (
          <div className="dualmask-row" key={p.canonical_part_key ? `${p.canonical_part_key}-${i}` : `part-${i}`}>
            <div className="dualmask-bar">
              <div className="dualmask-fill damage" style={{ width: `${iop}%` }} />
              <div className="dualmask-fill part" style={{ width: `${Math.min(100, iop + 25)}%`, opacity: 0.25 }} />
            </div>
            <div className="dualmask-copy">
              <b>{p.display_part_name?.replace(/_/g, " ")}</b>
              <small>{iop.toFixed(1)}% IoP · damage ∩ part masks</small>
            </div>
          </div>
        );
      })}
    </div>
  );
}
