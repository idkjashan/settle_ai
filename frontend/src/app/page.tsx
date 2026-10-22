"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { useClaims } from "@/lib/store";
import { useDisplayClaims, ClaimsTable } from "@/components/claims-table";
import { StatusTag } from "@/components/status-tag";
import { Icon } from "@/components/icons";
import { dayLabel, greeting, inr, timeAgo } from "@/lib/format";

type Filter = "all" | "ready" | "review" | "settled";

export default function OverviewPage() {
  const { claims, details, apiOnline } = useClaims();
  const rows = useDisplayClaims();
  const [filter, setFilter] = useState<Filter>("all");

  const stats = useMemo(() => {
    const byPhase = { ready: 0, review: 0, settled: 0, processing: 0, escalated: 0, rejected: 0, garage: 0 };
    let repairTotal = 0;
    for (const r of rows) {
      const phase = r.detail ? phaseOf(r.detail.claim_status, r.detail.escalation_code) : "processing";
      byPhase[phase] += 1;
      if (r.estimate) repairTotal += r.estimate;
    }
    return { byPhase, repairTotal };
  }, [rows]);

  const filtered = rows.filter((r) => {
    if (filter === "all") return true;
    if (filter === "ready") return r.detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION";
    if (filter === "settled") return r.detail?.claim_status === "SETTLED_CASH_IN_LIEU";
    if (filter === "review")
      return r.detail ? ["ESCALATED", "ESCALATED_HUMAN_REVIEW"].includes(r.detail.claim_status) || !!r.detail.escalation_code : false;
    return true;
  });

  const nextUp = rows.find((r) => r.detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION") ?? rows[0];
  const nextBand = nextUp?.detail?.telemetry.actuarial_estimate?.settlement_band;

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">{dayLabel(new Date())} · CLAIMS DESK</p>
          <h1>
            {greeting()}, Nisha<span className="period">.</span>
          </h1>
          <p className="subhead">A clear view of what needs your attention today.</p>
        </div>
        <Link className="button button-dark" href="/new-claim">
          <Icon name="plus" /> Start a claim
        </Link>
      </div>

      <div className="metric-row" aria-label="Claims desk snapshot">
        <article className="metric-card">
          <div className="metric-label">
            In your queue <span className="metric-icon"><Icon name="inbox" /></span>
          </div>
          <div className="metric-value">
            {String(claims.length).padStart(2, "0")}
            <span className="metric-small"> claims</span>
          </div>
          <div className="metric-foot">
            <span className="metric-mark mark-blue" /> {stats.byPhase.ready} ready for review
          </div>
        </article>
        <article className="metric-card">
          <div className="metric-label">
            Estimated exposure <span className="metric-icon"><Icon name="clock" /></span>
          </div>
          <div className="metric-value">{stats.repairTotal ? inr(stats.repairTotal) : "₹0"}</div>
          <div className="metric-foot">Across active repair estimates</div>
        </article>
        <article className="metric-card">
          <div className="metric-label">
            Ready to settle <span className="metric-icon"><Icon name="check" /></span>
          </div>
          <div className="metric-value">
            {String(stats.byPhase.ready).padStart(2, "0")}
            <span className="metric-small"> claims</span>
          </div>
          <div className="metric-foot">
            <span className="metric-mark mark-green" /> Within policy limits
          </div>
        </article>
        <article className="metric-card">
          <div className="metric-label">
            Human review <span className="metric-icon"><Icon name="person" /></span>
          </div>
          <div className="metric-value">
            {String(stats.byPhase.escalated).padStart(2, "0")}
            <span className="metric-small"> claims</span>
          </div>
          <div className="metric-foot">
            <span className="metric-mark mark-amber" /> Needs a closer look
          </div>
        </article>
      </div>

      <div className="section-heading">
        <div>
          <p className="eyebrow">ACTIVE CLAIM QUEUE</p>
          <h2>Recent claims</h2>
        </div>
        <Link className="text-button" href="/claims">
          Open all claims <span>↗</span>
        </Link>
      </div>

      <div className="overview-layout">
        <section className="panel queue-panel" aria-labelledby="queue-title">
          <div className="panel-topline">
            <div>
              <h3 id="queue-title">Live queue</h3>
              <p>{apiOnline === false ? "Backend offline — showing last known state" : "Synced with the autonomous pipeline"}</p>
            </div>
            <div className="filter-group">
              {(["all", "ready", "review", "settled"] as Filter[]).map((f) => (
                <button key={f} type="button" className={`filter-pill ${filter === f ? "is-active" : ""}`} onClick={() => setFilter(f)}>
                  {f[0].toUpperCase() + f.slice(1)} ({countFor(f, rows)})
                </button>
              ))}
            </div>
          </div>

          {filtered.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">
                <Icon name="inbox" size={24} />
              </div>
              <h3>No claims here yet</h3>
              <p>Submit a walkaround video or photo pack and the autonomous adjuster will take it from intake to cash offer.</p>
              <Link className="button button-dark" href="/new-claim">
                <Icon name="plus" /> Start a claim
              </Link>
            </div>
          ) : (
            <>
              <ClaimsTable rows={filtered} />
              <div className="panel-footer">
                <span>
                  Showing {filtered.length} of {rows.length} claims
                </span>
                <Link className="quiet-link" href="/claims">
                  Open claims desk <span>→</span>
                </Link>
              </div>
            </>
          )}
        </section>

        {nextUp ? (
          <aside className="attention-card">
            <div className="attention-head">
              <span className="attention-icon">
                <Icon name="spark" />
              </span>
              <span className="small-caps">NEXT UP</span>
            </div>
            <p className="attention-kicker">CLAIM {nextUp.label}</p>
            <h3>
              One clear decision,
              <br />
              ready when you are.
            </h3>
            <p className="attention-copy">
              {nextUp.damageLabel} on the {nextUp.damagePart.toLowerCase()}. Evidence verified, vehicle matched, offer inside the approved
              range.
            </p>
            <div className="attention-facts">
              <div>
                <span>Opening offer</span>
                <strong>{nextBand ? inr(nextBand.initial_offer_inr) : "—"}</strong>
              </div>
              <div>
                <span>Maximum approval</span>
                <strong>{nextBand ? inr(nextBand.walkaway_cap_inr) : "—"}</strong>
              </div>
            </div>
            <Link className="button button-light" href={`/claims/${nextUp.id}`}>
              Review this claim <span>→</span>
            </Link>
            <p className="attention-caption">
              <span className="live-dot" /> {timeAgo(nextUp.createdAt)} · audited OEM reference rate card
            </p>
          </aside>
        ) : (
          <aside className="attention-card">
            <div className="attention-head">
              <span className="attention-icon">
                <Icon name="spark" />
              </span>
              <span className="small-caps">GET STARTED</span>
            </div>
            <h3>
              Your desk is clear.
              <br />
              Start with evidence.
            </h3>
            <p className="attention-copy">
              Upload one unbroken walkaround video or a 3–6 photo pack. The pipeline handles identity, segmentation, pricing and the bounded
              offer.
            </p>
            <Link className="button button-light" href="/new-claim">
              Start a claim <span>→</span>
            </Link>
          </aside>
        )}
      </div>

      <div className="overview-bottom-note">
        <Icon name="info" />
        <span>
          Autonomous settlement is limited to eligible minor damage. Safety concerns, uncertain evidence, or amounts above ₹25,000 move to a
          human adjuster.
        </span>
        <Link className="quiet-link" href="/guardrails">
          See guardrails
        </Link>
      </div>
    </>
  );
}

function countFor(filter: Filter, rows: ReturnType<typeof useDisplayClaims>): number {
  if (filter === "all") return rows.length;
  if (filter === "ready") return rows.filter((r) => r.detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION").length;
  if (filter === "settled") return rows.filter((r) => r.detail?.claim_status === "SETTLED_CASH_IN_LIEU").length;
  return rows.filter(
    (r) => r.detail && (["ESCALATED", "ESCALATED_HUMAN_REVIEW"].includes(r.detail.claim_status) || !!r.detail.escalation_code),
  ).length;
}

function phaseOf(claimStatus: string, escalationCode: string | null): "ready" | "review" | "settled" | "processing" | "escalated" | "rejected" | "garage" {
  if (claimStatus === "PRICED_READY_FOR_NEGOTIATION") return "ready";
  if (claimStatus === "SETTLED_CASH_IN_LIEU") return "settled";
  if (claimStatus.startsWith("ESCALATED") || escalationCode) return "escalated";
  if (claimStatus.startsWith("REJECTED")) return "rejected";
  return "processing";
}
