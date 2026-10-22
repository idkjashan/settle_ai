"use client";

import type { ClaimDetail } from "@/lib/types";
import { Icon } from "@/components/icons";
import { inr } from "@/lib/format";
import { RangeMeter } from "./assessment";

export function EstimateTab({ detail, onContinue }: { detail: ClaimDetail | null; onContinue: () => void }) {
  const est = detail?.telemetry?.actuarial_estimate;

  if (!est) {
    return (
      <div className="panel">
        <div className="empty-state">
          <div className="empty-icon">
            <Icon name="database" size={24} />
          </div>
          <h3>{detail?.claim_status.startsWith("REJECTED") || detail?.escalation_code ? "No estimate — claim escalated" : "Estimate pending"}</h3>
          <p>
            {detail?.escalation_code
              ? `The pipeline stopped before pricing (${detail.escalation_code}). No cash estimate was produced.`
              : "The deterministic actuarial pricing engine runs once damage parts are verified. Check back in a moment."}
          </p>
        </div>
      </div>
    );
  }

  const s = est.summary;
  const band = est.settlement_band;

  return (
    <div className="economics-layout">
      <div className="panel estimate-panel">
        <div className="panel-topline">
          <div>
            <p className="eyebrow">
              REFERENCE RATE CARD · {est.vehicle_make.toUpperCase()} {est.vehicle_model.toUpperCase()} {est.vehicle_year}
            </p>
            <h2>Repair estimate</h2>
            <p>
              {est.line_items.length} line item{est.line_items.length > 1 ? "s" : ""} · deterministic OEM pricing ·{" "}
              {est.is_zero_dep_active ? "zero-dep cover" : "with depreciation"}
            </p>
          </div>
          <span className="estimate-badge">
            <Icon name="database" /> Reference pricing
          </span>
        </div>

        <div className="estimate-table">
          <div className="estimate-head">
            <span>WORK &amp; PARTS</span>
            <span>CALCULATION</span>
            <span className="align-right">AMOUNT</span>
          </div>
          {est.line_items.map((li, i) => (
            <div className="estimate-row" key={li.canonical_part_key}>
              <span className="estimate-item">
                <b className="line-icon">{String(i + 1).padStart(2, "0")}</b>
                <span>
                  <strong>
                    {li.display_part_name} · {li.action.replace(/_/g, " ").toLowerCase()}
                  </strong>
                  <small>
                    OEM {li.oem_part_number} · {li.material} · {li.depth_grade} · {(li.iop_ratio * 100).toFixed(1)}% IoP
                  </small>
                </span>
              </span>
              <span className="estimate-calc">
                parts {inr(li.net_part_cost_inr)} + labour {inr(li.rr_labour_inr)} + paint {inr(li.final_paint_inr)}
              </span>
              <strong className="align-right">{inr(li.gross_line_item_total_inr)}</strong>
            </div>
          ))}
          <div className="estimate-row estimate-subtotal">
            <span>Parts (net of depreciation)</span>
            <span className="estimate-calc">depreciation {inr(s.total_depreciation_inr)}</span>
            <strong className="align-right">{inr(s.total_net_parts_inr)}</strong>
          </div>
          <div className="estimate-row">
            <span>Labour &amp; paint</span>
            <span className="estimate-calc">incl. salvage −{inr(s.total_salvage_deduction_inr)}</span>
            <strong className="align-right">{inr(s.total_labour_inr + parseFloat(s.total_paint_inr))}</strong>
          </div>
          <div className="estimate-row">
            <span>GST</span>
            <span className="estimate-calc">18% of pre-tax subtotal</span>
            <strong className="align-right">{inr(s.total_gst_inr)}</strong>
          </div>
          <div className="estimate-row estimate-total">
            <span>
              <strong>Estimated garage repair</strong>
              <small>Gross reference cost before policy deductible</small>
            </span>
            <span />
            <strong className="align-right">{inr(s.gross_garage_repair_inr)}</strong>
          </div>
          <div className="estimate-row deductible-row">
            <span>Policy deductible</span>
            <span className="estimate-calc">Customer responsibility</span>
            <strong className="align-right">− {inr(s.total_deductible_inr)}</strong>
          </div>
        </div>

        <div className="net-total">
          <span>
            <span className="net-label">NET ELIGIBLE CLAIM</span>
            <small>Used to calculate the cash-settlement range</small>
          </span>
          <strong>{inr(s.net_claim_liability_inr)}</strong>
        </div>

        <div className="estimate-footnote">
          <Icon name="info" />
          <p>
            The estimate uses a deterministic reference rate card; the AI does not invent part or labour prices. Every line item is auditable
            against the OEM catalogue.
          </p>
        </div>
      </div>

      <aside className="estimate-aside">
        <section className="panel range-breakdown">
          <p className="eyebrow">CASH RANGE</p>
          <h3>
            Three numbers.
            <br />
            One clear boundary.
          </h3>
          <p className="range-intro">Offers are calculated from the {inr(s.net_claim_liability_inr)} net eligible claim.</p>
          <div className="range-meter on-light">
            <div className="range-line large">
              <span className="range-fill" />
              <i className="range-point point-start" />
              <i className="range-point point-target" />
              <i className="range-point point-cap" />
            </div>
          </div>
          <div className="range-table">
            <div>
              <span>
                <i className="range-swatch swatch-start" /> Opening · 75%
              </span>
              <strong>{inr(band.initial_offer_inr)}</strong>
            </div>
            <div>
              <span>
                <i className="range-swatch swatch-target" /> Target · 85%
              </span>
              <strong>{inr(band.target_settlement_inr)}</strong>
            </div>
            <div>
              <span>
                <i className="range-swatch swatch-cap" /> Maximum · 95%
              </span>
              <strong>{inr(band.walkaway_cap_inr)}</strong>
            </div>
          </div>
          {est.is_ceiling_breached ? (
            <div className="hard-cap" style={{ borderColor: "var(--red)", color: "var(--red)" }}>
              <Icon name="lock" />
              <span>
                <b>Ceiling breached</b>
                <small>Net repair exceeds the ₹25,000 autonomous limit — escalated to a licensed surveyor (ESC-08).</small>
              </span>
            </div>
          ) : (
            <div className="hard-cap">
              <Icon name="lock" />
              <span>
                <b>Hard ceiling</b>
                <small>Autonomous settlements stop at {inr(band.financial_ceiling_inr)} net repair cost.</small>
              </span>
            </div>
          )}
          <button type="button" className="button button-green button-full" onClick={onContinue}>
            Continue to offer <span>→</span>
          </button>
        </section>

        <section className="ncb-note">
          <span className="ncb-icon">i</span>
          <div>
            <strong>{est.ncb_advisory.recommendation.replace(/_/g, " ")}</strong>
            <p>{est.ncb_advisory.advisory_message}</p>
            <p style={{ marginTop: 6 }}>
              <b>Estimated NCB loss:</b> {inr(est.ncb_advisory.estimated_ncb_loss_inr)} · <b>Net benefit:</b>{" "}
              {inr(est.ncb_advisory.net_benefit_inr)}
            </p>
          </div>
        </section>
      </aside>
    </div>
  );
}
