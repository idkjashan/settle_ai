"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";
import { useDisplayClaims, ClaimsTable } from "@/components/claims-table";
import { Icon } from "@/components/icons";

type Filter = "all" | "ready" | "review" | "settled";

function ClaimsInner() {
  const rows = useDisplayClaims();
  const params = useSearchParams();
  const q = (params.get("q") ?? "").toLowerCase();
  const [filter, setFilter] = useState<Filter>("all");

  const filtered = useMemo(
    () =>
      rows.filter((r) => {
        const matchesQuery =
          !q ||
          r.label.toLowerCase().includes(q) ||
          r.vehicleLabel.toLowerCase().includes(q) ||
          r.regLabel.toLowerCase().includes(q) ||
          r.damageLabel.toLowerCase().includes(q) ||
          (r.detail?.claim_status ?? "").toLowerCase().includes(q) ||
          r.note.toLowerCase().includes(q);
        const matchesFilter =
          filter === "all"
            ? true
            : filter === "ready"
              ? r.detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION"
              : filter === "settled"
                ? r.detail?.claim_status === "SETTLED_CASH_IN_LIEU"
                : r.detail
                  ? ["ESCALATED", "ESCALATED_HUMAN_REVIEW"].includes(r.detail.claim_status) || !!r.detail.escalation_code
                  : false;
        return matchesQuery && matchesFilter;
      }),
    [rows, q, filter],
  );

  return (
    <>
      <div className="page-heading">
        <div>
          <p className="eyebrow">CLAIMS DESK</p>
          <h1>
            Every claim, one desk<span className="period">.</span>
          </h1>
          <p className="subhead">Search, filter and open any claim evaluated by the autonomous adjuster.</p>
        </div>
        <Link className="button button-dark" href="/new-claim">
          <Icon name="plus" /> Start a claim
        </Link>
      </div>

      <section className="panel">
        <div className="panel-topline">
          <div>
            <h2>Claim register</h2>
            <p>
              {q ? (
                <>
                  Search results for “{q}” · <Link className="quiet-link" href="/claims">clear</Link>
                </>
              ) : (
                "Live status, synced with the FastAPI pipeline"
              )}
            </p>
          </div>
          <div className="filter-group">
            {(["all", "ready", "review", "settled"] as Filter[]).map((f) => (
              <button key={f} type="button" className={`filter-pill ${filter === f ? "is-active" : ""}`} onClick={() => setFilter(f)}>
                {f[0].toUpperCase() + f.slice(1)} (
                {f === "all"
                  ? rows.length
                  : f === "ready"
                    ? rows.filter((r) => r.detail?.claim_status === "PRICED_READY_FOR_NEGOTIATION").length
                    : f === "settled"
                      ? rows.filter((r) => r.detail?.claim_status === "SETTLED_CASH_IN_LIEU").length
                      : rows.filter((r) => r.detail && (["ESCALATED", "ESCALATED_HUMAN_REVIEW"].includes(r.detail.claim_status) || !!r.detail.escalation_code)).length}
                )
              </button>
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <Icon name="file" size={24} />
            </div>
            <h3>{rows.length === 0 ? "No claims yet" : "Nothing matches"}</h3>
            <p>
              {rows.length === 0
                ? "Submit your first claim — a walkaround video is all the pipeline needs."
                : "Try a different search term or filter."}
            </p>
            {rows.length === 0 && (
              <Link className="button button-dark" href="/new-claim">
                <Icon name="plus" /> Start a claim
              </Link>
            )}
          </div>
        ) : (
          <>
            <ClaimsTable rows={filtered} />
            <div className="panel-footer">
              <span>
                Showing {filtered.length} of {rows.length} claims
              </span>
            </div>
          </>
        )}
      </section>
    </>
  );
}

export default function ClaimsPage() {
  return (
    <Suspense fallback={null}>
      <ClaimsInner />
    </Suspense>
  );
}
