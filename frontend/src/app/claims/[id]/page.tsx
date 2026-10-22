"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { use, useEffect, useMemo, useState } from "react";
import { useClaimDetail, useClaims } from "@/lib/store";
import { Icon } from "@/components/icons";
import { StatusTag } from "@/components/status-tag";
import { inr, shortId, STAGE_LABELS, statusMeta, timeAgo } from "@/lib/format";
import { AssessmentTab } from "@/components/workstation/assessment";
import { EstimateTab } from "@/components/workstation/estimate";
import { SettlementTab } from "@/components/workstation/settlement";
import { AuditTab } from "@/components/workstation/audit";
import { DecisionTab } from "@/components/workstation/decision";

type Tab = "assessment" | "estimate" | "settlement" | "audit" | "decision";

const TAB_ORDER: Tab[] = ["assessment", "estimate", "settlement", "audit", "decision"];

export default function ClaimWorkstationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { claims, refreshClaim, eventsByClaim } = useClaims();
  const detail = useClaimDetail(id);
  const record = claims.find((c) => c.id === id) ?? null;
  const [tab, setTab] = useState<Tab>("assessment");

  useEffect(() => {
    void refreshClaim(id);
  }, [id, refreshClaim]);

  // Auto-advance tab when the offer becomes ready while the user watches
  useEffect(() => {
    if (detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION") {
      setTab((prev) => (prev === "assessment" ? "settlement" : prev));
    }
  }, [detail?.claim_status]);

  const meta = detail ? statusMeta(detail.claim_status, detail.escalation_code) : null;
  const events = eventsByClaim[id] ?? [];

  const tabNotice: Partial<Record<Tab, number>> = useMemo(() => {
    if (detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION") return { settlement: 1 };
    return {};
  }, [detail?.claim_status]);

  const activeIdx = TAB_ORDER.indexOf(tab);

  return (
    <>
      <div className="backline">
        <button className="back-button" type="button" onClick={() => router.push("/claims")}>
          ← <span>All claims</span>
        </button>
        <span className="backline-sep">/</span>
        <span>Claim review</span>
        {record && <span className="demo-tag">{record.modality === "PHOTO_PACK" ? "PHOTO PACK" : "VIDEO WALKAROUND"}</span>}
      </div>

      <div className="claim-title-row">
        <div>
          <p className="eyebrow">
            CLAIM {shortId(id)} <span className="eyebrow-divider">·</span> {record ? `SUBMITTED ${timeAgo(record.createdAt).toUpperCase()}` : "LIVE CLAIM"}{" "}
            <span className="eyebrow-divider">·</span> {record?.policyId ?? detail?.policy_id ?? "—"}
          </p>
          <h1>
            {record?.vehicle ?? detail?.telemetry?.actuarial_estimate?.vehicle_make ?? "Evaluating"}{" "}
            <span className="title-muted">/</span> {detail?.telemetry?.actuarial_estimate?.vehicle_year ?? ""}
          </h1>
          <p className="subhead">
            {record?.registration ?? detail?.telemetry?.actuarial_estimate?.registration_number ?? "—"} <span className="subhead-divider">·</span>{" "}
            {detail ? STAGE_LABELS[detail.current_stage] ?? detail.current_stage : "Fetching pipeline state…"}{" "}
            <span className="subhead-divider">·</span> {meta?.description ?? ""}
          </p>
        </div>
        <div className="title-actions">
          <StatusTag detail={detail} />
        </div>
      </div>

      <nav className="workflow-track" aria-label="Claim workflow">
        {["Evidence", "Assessment", "Estimate", "Settlement", "Audit trail"].map((label, i) => {
          const stepTab = TAB_ORDER[Math.min(i, 4)];
          const state = i < activeIdx ? "is-complete" : i === activeIdx ? "is-active" : "";
          return (
            <span key={label} style={{ display: "contents" }}>
              {i > 0 && <span className={`workflow-connector ${i <= activeIdx ? "done" : ""}`} />}
              <button className={`workflow-step ${state}`} type="button" onClick={() => setTab(stepTab)}>
                <span className="step-num">{i < activeIdx ? "✓" : `0${i + 1}`}</span>
                <span>{label}</span>
              </button>
            </span>
          );
        })}
      </nav>

      <nav className="case-tabs" aria-label="Claim detail sections">
        {TAB_ORDER.map((t) => (
          <button key={t} className={`case-tab ${tab === t ? "is-active" : ""}`} type="button" onClick={() => setTab(t)}>
            {t === "estimate" ? "Repair estimate" : t[0].toUpperCase() + t.slice(1)}
            {tabNotice[t] && <span className="tab-notice">{tabNotice[t]}</span>}
          </button>
        ))}
      </nav>

      <div className="case-panel">
        {tab === "assessment" && <AssessmentTab claimId={id} detail={detail} localVideoUrl={record?.localVideoUrl} onOpenSettlement={() => setTab("settlement")} />}
        {tab === "estimate" && <EstimateTab detail={detail} onContinue={() => setTab("settlement")} />}
        {tab === "settlement" && <SettlementTab claimId={id} detail={detail} onDecision={() => setTab("decision")} />}
        {tab === "audit" && <AuditTab claimId={id} detail={detail} />}
        {tab === "decision" && <DecisionTab claimId={id} detail={detail} onBackToSettlement={() => setTab("settlement")} />}
      </div>

      {events.length > 0 && (
        <div className="overview-bottom-note">
          <Icon name="history" />
          <span>
            {events.length} live pipeline event{events.length > 1 ? "s" : ""} received — latest: <b>{events[events.length - 1].event}</b>
          </span>
        </div>
      )}
    </>
  );
}
