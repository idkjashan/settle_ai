"use client";

import Link from "next/link";
import { useState } from "react";
import { Icon, type IconName } from "@/components/icons";
import { ESCALATION_RULES, type EscalationRule } from "@/lib/rules";
import { useClaims } from "@/lib/store";
import { inr } from "@/lib/format";

type ScenarioKey = "clear" | "confidence" | "safety" | "continuity" | "limit" | "rust" | "mismatch" | "repeat";

const SCENARIOS: Record<Exclude<ScenarioKey, "clear">, { rule: string; icon: string; title: string; detail: string }> = {
  confidence: { rule: "ESC-07", icon: "warn", title: "Human desk adjuster", detail: "Detection confidence fell below 55% — the claim pauses for a clearer close-up or human review." },
  safety: { rule: "ESC-06", icon: "block", title: "Physical inspection", detail: "A safety-critical part (windshield, wheel, radiator) routes to a garage — no cash-in-lieu." },
  continuity: { rule: "ESC-02", icon: "warn", title: "Require live capture", detail: "A scene cut was detected between plate and damage — one unbroken recording is required." },
  limit: { rule: "ESC-08", icon: "block", title: "Licensed surveyor", detail: "The net repair estimate crossed the ₹25,000 autonomous ceiling — human assessment takes over." },
  rust: { rule: "ESC-04", icon: "warn", title: "Escalate for review", detail: "Old rust or flaking filler suggests pre-existing damage — uncertain age is never billed as new." },
  mismatch: { rule: "ESC-01", icon: "block", title: "Block and escalate", detail: "The plate or colour differs from the policy record — routed to fraud review, no offer." },
  repeat: { rule: "ESC-03", icon: "warn", title: "Pause and review", detail: "The same part has an open cash-paid record — repair proof or an adjuster decides." },
};

export default function GuardrailsPage() {
  const { claims, details } = useClaims();
  const [scenario, setScenario] = useState<ScenarioKey>("clear");

  const nextReady = claims.map((c) => details[c.id]).find((d) => d?.claim_status === "PRICED_READY_FOR_NEGOTIATION") ?? null;
  const est = nextReady?.telemetry.actuarial_estimate;

  const outcome =
    scenario === "clear"
      ? { icon: "clear" as const, title: "Continue to bounded offer", detail: "Evidence is clear and the claim remains inside the autonomous limit." }
      : SCENARIOS[scenario];

  return (
    <>
      <div className="backline">
        <Link className="back-button" href="/">
          ← <span>Overview</span>
        </Link>
        <span className="backline-sep">/</span>
        <span>Guardrails</span>
        <span className="demo-tag">POLICY RULES</span>
      </div>

      <div className="page-heading">
        <div>
          <p className="eyebrow">SAFE BY DESIGN</p>
          <h1>
            Know when to stop<span className="period">.</span>
          </h1>
          <p className="subhead">Autonomous decisions stay inside financial and operational limits. Uncertainty is a reason to pause, not guess.</p>
        </div>
      </div>

      <div className="guardrail-overview">
        <div className="guardrail-state-card">
          <span className="large-status-icon">
            <Icon name="shield" size={24} />
          </span>
          <div>
            <p className="eyebrow">{nextReady ? "CURRENT ACTIVE CLAIM" : "DESK STATE"}</p>
            <h2 className="good-text">{nextReady ? "9 checks passed" : "Guardrails armed"}</h2>
            <p>
              {est
                ? `Non-safety damage · ${inr(est.summary.gross_garage_repair_inr)} estimated repair`
                : "Every claim runs the same deterministic perimeter before any money moves."}
            </p>
          </div>
          <Link className="button button-green" href={nextReady ? `/claims/${nextReady.claim_id}` : "/claims"}>
            Return to claims <span>→</span>
          </Link>
        </div>
        <div className="guardrail-mini-grid">
          <div>
            <span>Confidence</span>
            <strong>{est ? "96%" : "—"}</strong>
            <small>Minimum 55%</small>
          </div>
          <div>
            <span>Net repair estimate</span>
            <strong>{est ? inr(est.summary.net_claim_liability_inr) : "—"}</strong>
            <small>Autonomous limit ₹25,000</small>
          </div>
          <div>
            <span>Maximum offer</span>
            <strong>{est ? inr(est.settlement_band.walkaway_cap_inr) : "—"}</strong>
            <small>95% of eligible claim</small>
          </div>
        </div>
      </div>

      <div className="section-heading">
        <div>
          <p className="eyebrow">ESCALATION CATALOG</p>
          <h2>When automation hands off</h2>
        </div>
        <span className="catalog-count">{String(ESCALATION_RULES.length).padStart(2, "0")} RULES</span>
      </div>

      <div className="rule-list">
        {ESCALATION_RULES.map((rule) => (
          <RuleRow key={rule.code} rule={rule} />
        ))}
      </div>

      <section className="scenario-panel panel">
        <div className="scenario-copy">
          <p className="eyebrow">DEMO A GUARDRAIL</p>
          <h2>See what happens when a check fails.</h2>
          <p>Select a condition to preview the interface state. Presets on the New claim page reproduce several of these live.</p>
          <div className="scenario-select-wrap">
            <label htmlFor="scenario-select">Example condition</label>
            <select id="scenario-select" value={scenario} onChange={(e) => setScenario(e.target.value as ScenarioKey)}>
              <option value="clear">All checks clear (Happy Path · Within limits)</option>
              <option value="confidence">ESC-07: Confidence below 55%</option>
              <option value="safety">ESC-06: Safety-critical part detected</option>
              <option value="continuity">ESC-02: Video continuity failure</option>
              <option value="limit">ESC-08: Repair estimate over ₹25,000</option>
              <option value="rust">ESC-04: Possible pre-existing rust</option>
              <option value="mismatch">ESC-01: Vehicle plate mismatch</option>
              <option value="repeat">ESC-03: Repeated unrepaired damage</option>
            </select>
          </div>
          <div style={{ marginTop: 14 }}>
            <Link className="button button-dark" href="/new-claim">
              <Icon name="spark" /> Try it live in New claim <span>→</span>
            </Link>
          </div>
        </div>
        <div className="scenario-result" aria-live="polite">
          <span className={`scenario-result-icon ${outcome.icon}`}>
            {outcome.icon === "clear" ? <Icon name="check" /> : outcome.icon === "warn" ? <Icon name="info" /> : <Icon name="shield" />}
          </span>
          <div>
            <span className="small-caps">{scenario === "clear" ? "CURRENT OUTCOME" : `OUTCOME · ${SCENARIOS[scenario as Exclude<ScenarioKey, "clear">].rule}`}</span>
            <strong>{outcome.title}</strong>
            <p>{outcome.detail}</p>
          </div>
        </div>
      </section>
    </>
  );
}

function RuleRow({ rule }: { rule: EscalationRule }) {
  const symbolClass = rule.outcome === "retry" ? "outcome-blue" : rule.outcome === "block" || rule.outcome === "surveyor" ? "outcome-red" : "outcome-amber";
  const symbol = rule.outcome === "retry" ? "↺" : rule.outcome === "block" ? "!" : "↗";
  return (
    <article className="rule-row">
      <span className="rule-id">{rule.code}</span>
      <div className="rule-main">
        <strong>{rule.title}</strong>
        <p>{rule.detail}</p>
      </div>
      <span className="rule-trigger">{rule.trigger}</span>
      <span className="rule-outcome">
        <span className={`outcome-symbol ${symbolClass}`}>{symbol}</span>
        <span>
          <b>{rule.outcomeTitle}</b>
          <small>{rule.outcomeDetail}</small>
        </span>
      </span>
    </article>
  );
}
