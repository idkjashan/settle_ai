"use client";

import { useEffect, useState } from "react";
import { useClaims } from "@/lib/store";
import { AuditTab } from "@/components/workstation/audit";
import { Icon } from "@/components/icons";
import { shortId } from "@/lib/format";

export default function GlobalAuditPage() {
  const { claims, details, refreshClaim } = useClaims();
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    if (!selected && claims.length) setSelected(claims[0].id);
  }, [claims, selected]);

  useEffect(() => {
    if (selected) void refreshClaim(selected);
  }, [selected, refreshClaim]);

  const detail = selected ? details[selected] ?? null : null;

  return (
    <>
      <div className="backline">
        <span className="demo-tag">VERIFIED LEDGER</span>
      </div>

      <div className="page-heading">
        <div>
          <p className="eyebrow">{selected ? `CLAIM ${shortId(selected)}` : "AUDIT LEDGER"}</p>
          <h1>
            Every decision, in order<span className="period">.</span>
          </h1>
          <p className="subhead">A readable record of the evidence reviewed, offer changes, guardrail events, and final outcome.</p>
        </div>
      </div>

      {claims.length === 0 ? (
        <section className="panel">
          <div className="empty-state">
            <div className="empty-icon">
              <Icon name="history" size={24} />
            </div>
            <h3>Nothing to audit yet</h3>
            <p>Claims submitted through the desk appear here with their full cryptographic trail.</p>
          </div>
        </section>
      ) : (
        <>
          <div className="scenario-select-wrap" style={{ maxWidth: 420, marginBottom: 16 }}>
            <label htmlFor="audit-claim-select">Claim</label>
            <select id="audit-claim-select" value={selected ?? ""} onChange={(e) => setSelected(e.target.value)}>
              {claims.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.label} · {c.vehicle} · {c.registration}
                </option>
              ))}
            </select>
          </div>
          <AuditTab claimId={selected as string} detail={detail} />
        </>
      )}
    </>
  );
}
