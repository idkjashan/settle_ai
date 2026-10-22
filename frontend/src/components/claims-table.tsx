"use client";

import Link from "next/link";
import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { useClaims } from "@/lib/store";
import type { ClaimRecord } from "@/lib/store";
import { inr, timeAgo } from "@/lib/format";
import { StatusTag } from "./status-tag";

export interface DisplayClaim extends ClaimRecord {
  vehicleLabel: string;
  regLabel: string;
  damageLabel: string;
  damagePart: string;
  estimate: number | null;
  detail: ReturnType<typeof useClaims>["details"][string] | null;
}

export function useDisplayClaims(): DisplayClaim[] {
  const { claims, details } = useClaims();
  return useMemo(
    () =>
      claims.map((c) => {
        const d = details[c.id] ?? null;
        const est = d?.telemetry?.actuarial_estimate;
        const parts = d?.telemetry?.vlm_inspection?.verified_parts ?? [];
        const primary = parts[0];
        return {
          ...c,
          vehicleLabel: est ? `${est.vehicle_make} ${est.vehicle_model}` : c.vehicle,
          regLabel: est?.registration_number ?? c.registration,
          damageLabel: primary?.primary_damage_class?.replace(/_/g, " ") ?? firstDamageWord(c.note),
          damagePart: primary?.display_part_name?.replace(/_/g, " ") ?? "Pending assessment",
          estimate: est?.summary?.gross_garage_repair_inr ? parseFloat(est.summary.gross_garage_repair_inr) : null,
          detail: d,
        };
      }),
    [claims, details],
  );
}

function firstDamageWord(note: string): string {
  const m = note.match(/(?:creased dent|dent|scratch|scuff|crack|damage)/i);
  return m ? m[0].replace(/\b\w/, (ch) => ch.toUpperCase()) : "Claim intake";
}

export function ClaimsTable({ rows, selectedId }: { rows: DisplayClaim[]; selectedId?: string }) {
  const router = useRouter();
  return (
    <div className="table-scroll">
      <table className="claims-table">
        <thead>
          <tr>
            <th>CLAIM</th>
            <th>VEHICLE</th>
            <th>DAMAGE</th>
            <th>EST. REPAIR</th>
            <th>STATUS</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {rows.map((c) => (
            <tr
                key={c.id}
                className={c.id === selectedId ? "selected-row" : ""}
                style={{ cursor: "pointer" }}
                onClick={() => router.push(`/claims/${c.id}`)}
              >
              <td>
                <Link href={`/claims/${c.id}`} className="claim-id">
                  {c.label}
                </Link>
                <small>{timeAgo(c.createdAt)}</small>
              </td>
              <td>
                <span className="vehicle-name">{c.vehicleLabel}</span>
                <small>{c.regLabel}</small>
              </td>
              <td>
                <span className="table-damage">{c.damageLabel}</span>
                <small>{c.damagePart}</small>
              </td>
              <td className="currency-cell">{c.estimate != null ? inr(c.estimate) : "—"}</td>
              <td>
                <StatusTag detail={c.detail} />
              </td>
              <td className="row-arrow">
                <Link href={`/claims/${c.id}`} aria-label={`Open ${c.label}`}>
                  ↗
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
