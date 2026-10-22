"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import { useClaims } from "@/lib/store";
import { useToast } from "@/components/providers";
import { Icon } from "@/components/icons";
import { clockTime, inr } from "@/lib/format";
import type { ClaimDetail, NegotiationSession } from "@/lib/types";

export function SettlementTab({ claimId, detail, onDecision }: { claimId: string; detail: ClaimDetail | null; onDecision: () => void }) {
  const showToast = useToast();
  const { refreshClaim } = useClaims();
  const [session, setSession] = useState<NegotiationSession | null>(null);
  const [loading, setLoading] = useState(false);
  const [counterAmount, setCounterAmount] = useState("");
  const [counterMessage, setCounterMessage] = useState("");
  const [upiId, setUpiId] = useState("");
  const [error, setError] = useState("");

  const loadSession = useCallback(async () => {
    try {
      const s = await api.getNegotiation(claimId);
      setSession(s);
      return s;
    } catch {
      setSession(null);
      return null;
    }
  }, [claimId]);

  useEffect(() => {
    void loadSession();
  }, [loadSession, detail?.claim_status]);

  const sendCounter = async () => {
    setError("");
    const amount = counterAmount.trim() ? parseFloat(counterAmount) : undefined;
    const message = counterMessage.trim() || (amount != null ? `I request ₹${Math.round(amount).toLocaleString("en-IN")} for this damage.` : "Can you review the offer?");
    setLoading(true);
    try {
      await api.negotiate(claimId, message, amount);
      await loadSession();
      setCounterAmount("");
      setCounterMessage("");
      showToast("Counteroffer submitted — signed response received.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Negotiation failed — try again.");
    } finally {
      setLoading(false);
    }
  };

  const acceptOffer = async () => {
    if (!session) return;
    setError("");
    setLoading(true);
    try {
      await api.acceptOffer(claimId, session.active_offer_card, upiId.trim() || undefined);
      await Promise.all([loadSession(), refreshClaim(claimId)]);
      showToast("Settlement accepted — UPI voucher disbursed.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Accept failed — try again.");
    } finally {
      setLoading(false);
    }
  };

  const rejectOffer = async () => {
    setError("");
    setLoading(true);
    try {
      await api.rejectOffer(claimId, "Claimant selected authorized network cashless garage repair.");
      await Promise.all([loadSession(), refreshClaim(claimId)]);
      showToast("Rejected — claim routed to the cashless garage queue.");
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Reject failed — try again.");
    } finally {
      setLoading(false);
    }
  };

  if (!session) {
    return (
      <div className="panel">
        <div className="empty-state">
          <div className="empty-icon">
            <Icon name="spark" size={24} />
          </div>
          <h3>{detail?.escalation_code || detail?.claim_status.startsWith("ESCALATED") ? "No negotiation session" : "Settlement not ready yet"}</h3>
          <p>
            {detail?.telemetry?.actuarial_estimate?.is_ceiling_breached
              ? "The net repair estimate exceeded the ₹25,000 autonomous ceiling (ESC-08), so no cash offer can be negotiated."
              : "The bounded negotiation session opens once actuarial pricing completes and an initial offer card is signed."}
          </p>
        </div>
      </div>
    );
  }

  const band = session.settlement_band;
  const offer = session.active_offer_card;
  const settled = session.session_state === "SETTLED";
  const rejectedGarage = session.session_state === "REJECTED_GARAGE";
  const cap = parseFloat(band.walkaway_cap_inr);
  const initial = parseFloat(band.initial_offer_inr);
  const current = parseFloat(offer.amount_inr);
  const currentPct = cap > 0 ? Math.min(100, (current / cap) * 100) : 0;
  const round = Math.max(1, Math.min(session.current_round + 1, 3));

  return (
    <div className="settlement-layout">
      <section className="panel conversation-panel">
        <div className="conversation-header">
          <div>
            <p className="eyebrow">CUSTOMER CONVERSATION</p>
            <h2>Offer conversation</h2>
          </div>
          <span className="round-badge">
            ROUND {round} OF {settled || rejectedGarage ? "—" : 3}
          </span>
        </div>
        <div className="conversation-context">
          <span className="context-check">
            <Icon name="check" />
          </span>
          <p>
            <strong>Assessment explained</strong>
            <span>
              {detail?.telemetry?.actuarial_estimate
                ? `Repair estimate ${inr(detail.telemetry.actuarial_estimate.summary.gross_garage_repair_inr)}`
                : "Estimate pending"}
            </span>
          </p>
        </div>

        <div className="message-stream" aria-live="polite">
          {/* opening agent message implied by round 0 */}
          <div className="message-row agent-message">
            <span className="message-avatar agent-avatar">A</span>
            <div>
              <div className="message-meta">
                <strong>Auto-Settle</strong>
                <span>offer round 0</span>
              </div>
              <div className="message-bubble">
                We&apos;ve reviewed your evidence. The damage is eligible for a cash settlement of <b>{inr(initial)}</b> today — inside your
                approved range of {inr(band.initial_offer_inr)}–{inr(band.walkaway_cap_inr)}.
              </div>
            </div>
          </div>

          {session.turns.map((turn, i) => (
            <div key={i}>
              <div className="message-row claimant-message">
                <span className="message-avatar claimant-avatar">C</span>
                <div>
                  <div className="message-meta">
                    <strong>Claimant</strong>
                    <span>round {turn.round_num} · {clockTime(turn.timestamp)}</span>
                  </div>
                  <div className="message-bubble">
                    {turn.claimant_message}
                    {turn.parsed_counteroffer_inr && (
                      <>
                        <br />
                        <small style={{ color: "var(--muted)" }}>counteroffer: {inr(turn.parsed_counteroffer_inr)}</small>
                      </>
                    )}
                  </div>
                </div>
              </div>
              <div className="message-row agent-message" style={{ marginTop: 10 }}>
                <span className="message-avatar agent-avatar">A</span>
                <div>
                  <div className="message-meta">
                    <strong>Auto-Settle</strong>
                    <span>{clockTime(turn.timestamp)}</span>
                  </div>
                  <div className="message-bubble">{turn.chatbot_reply}</div>
                </div>
              </div>
            </div>
          ))}

          {!settled && !rejectedGarage && (
            <div className="offer-message">
              <div className="offer-card-mini">
                <div>
                  <span className="small-caps">CASH OFFER · ROUND {offer.round_num}</span>
                  <strong>{inr(offer.amount_inr)}</strong>
                  <small>{offer.is_terminal ? "Final offer — maximum automated approval" : "Within the approved settlement range"}</small>
                </div>
                <span className="signed-mark">
                  <Icon name="lock" /> HMAC
                  <br />
                  SIGNED
                </span>
              </div>
              <div className="offer-actions">
                <button className="button button-green" type="button" onClick={acceptOffer} disabled={loading}>
                  Accept {inr(offer.amount_inr)}
                </button>
                <button className="button button-outline" type="button" onClick={rejectOffer} disabled={loading}>
                  Choose garage repair
                </button>
                <span className="or-divider">or</span>
                <span className="offer-actions-hint">make a counteroffer below</span>
              </div>
              <div className="counter-input-row" style={{ marginTop: 12, maxWidth: 420 }}>
                <span className="rupee-prefix">₹</span>
                <input
                  type="text"
                  inputMode="numeric"
                  placeholder="Your UPI ID for payout (optional)"
                  value={upiId}
                  onChange={(e) => setUpiId(e.target.value)}
                  aria-label="Beneficiary UPI ID"
                  style={{ borderLeft: "none", borderRadius: "0 var(--radius-sm) var(--radius-sm) 0", width: "100%" }}
                />
              </div>
            </div>
          )}
        </div>

        {settled && (
          <div className="settled-banner">
            <span className="settled-icon">
              <Icon name="check" />
            </span>
            <div>
              <strong>Settlement accepted</strong>
              <p>
                Final cash offer: <b>{inr(current)}</b>. UPI voucher disbursed — see the Decision tab for the certificate.
              </p>
            </div>
            <button className="button button-green" type="button" onClick={onDecision}>
              View decision <span>→</span>
            </button>
          </div>
        )}

        {rejectedGarage && (
          <div className="escalated-banner">
            <span className="settled-icon" style={{ background: "var(--amber2)" }}>
              <Icon name="shield" />
            </span>
            <div>
              <strong>Routed to cashless garage</strong>
              <p>The claimant chose an authorized network garage repair. A surveyor dossier has been compiled — see the Decision tab.</p>
            </div>
            <button className="button button-outline" type="button" onClick={onDecision} style={{ marginLeft: "auto" }}>
              View decision <span>→</span>
            </button>
          </div>
        )}

        {!settled && !rejectedGarage && (
          <div className="negotiation-input-wrap">
            <label className="field-label" htmlFor="counter-amount">
              Your counteroffer <span>Optional</span>
            </label>
            <div className="counter-input-row">
              <span className="rupee-prefix">₹</span>
              <input
                id="counter-amount"
                type="number"
                min={1}
                step={100}
                inputMode="numeric"
                placeholder="Enter amount"
                value={counterAmount}
                onChange={(e) => setCounterAmount(e.target.value)}
              />
              <button className="button button-dark" type="button" onClick={sendCounter} disabled={loading}>
                Send counteroffer <span>→</span>
              </button>
            </div>
            <label className="field-label reason-label" htmlFor="counter-reason">
              What would help explain the difference? <span>Optional</span>
            </label>
            <textarea
              id="counter-reason"
              rows={2}
              placeholder="For example: an authorised workshop quoted a higher paint rate."
              value={counterMessage}
              onChange={(e) => setCounterMessage(e.target.value)}
            />
            <p className="input-hint">
              <Icon name="shield" /> Automated offers cannot exceed <strong>{inr(band.walkaway_cap_inr)}</strong>. Up to 3 rounds.
            </p>
            {error && (
              <p className="form-error" role="alert">
                {error}
              </p>
            )}
          </div>
        )}

        <div className="conversation-footer">
          <span>
            <Icon name="lock" /> Offer cards are HMAC-SHA256 signed to the approved range
          </span>
          <span>Real-time bounded FSM negotiation</span>
        </div>
      </section>

      <aside className="settlement-rail">
        <section className="panel live-range-card">
          <div className="panel-topline">
            <div>
              <p className="eyebrow">OFFER BOUNDARY</p>
              <h3>Always inside the line.</h3>
            </div>
            <span className="lock-badge">
              <Icon name="lock" />
            </span>
          </div>
          <div className="range-meter" style={{ background: "var(--panel-bg)", padding: 4, borderRadius: 8 }}>
            <div className="range-line" style={{ background: "var(--line)" }}>
              <span className="range-fill" style={{ width: `${currentPct}%`, background: "var(--green)" }} />
              <i className="range-point point-start" style={{ borderColor: "var(--green)" }} />
              <i className="range-point point-target" style={{ borderColor: "var(--amber2)", left: "53%" }} />
              <i className="range-point point-cap" style={{ borderColor: "var(--red)" }} />
            </div>
            <div className="range-labels" style={{ color: "var(--muted)" }}>
              <span>
                <b style={{ color: "var(--ink)" }}>75%</b>
                {inr(band.initial_offer_inr)}
              </span>
              <span>
                <b style={{ color: "var(--ink)" }}>85%</b>
                {inr(band.target_settlement_inr)}
              </span>
              <span>
                <b style={{ color: "var(--ink)" }}>95%</b>
                {inr(band.walkaway_cap_inr)}
              </span>
            </div>
          </div>
          <div className="range-current">
            <span>Current offer</span>
            <strong>{inr(current)}</strong>
          </div>
          <div className="range-current range-current-muted">
            <span>Maximum automated offer</span>
            <strong>{inr(band.walkaway_cap_inr)}</strong>
          </div>
          <div className="rail-guardrail">
            <Icon name="shield" />
            <p>Anything above {inr(band.walkaway_cap_inr)} is blocked. The claimant can choose a garage repair or human review instead.</p>
          </div>
        </section>

        <section className="panel ncb-rail">
          <p className="eyebrow">CUSTOMER CONTEXT</p>
          <h3>No Claim Bonus</h3>
          {detail?.telemetry?.actuarial_estimate?.ncb_advisory ? (
            <>
              <p>{detail.telemetry.actuarial_estimate.ncb_advisory.advisory_message}</p>
              <p className="ncb-small">
                Estimated NCB loss <strong>{inr(detail.telemetry.actuarial_estimate.ncb_advisory.estimated_ncb_loss_inr)}</strong> · Net benefit{" "}
                {inr(detail.telemetry.actuarial_estimate.ncb_advisory.net_benefit_inr)}
              </p>
            </>
          ) : (
            <p className="ncb-small">NCB advisory appears once actuarial pricing completes.</p>
          )}
        </section>
      </aside>
    </div>
  );
}
