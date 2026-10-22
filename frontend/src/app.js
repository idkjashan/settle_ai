(() => {
  'use strict';

  const money = (value) => `₹${Math.round(value).toLocaleString('en-IN')}`;
  const iconPaths = {
    grid: '<rect x="3" y="3" width="7" height="7" rx="1.2"/><rect x="14" y="3" width="7" height="7" rx="1.2"/><rect x="3" y="14" width="7" height="7" rx="1.2"/><rect x="14" y="14" width="7" height="7" rx="1.2"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h8"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    shield: '<path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z"/><path d="m9 12 2 2 4-4"/>',
    history: '<path d="M3 12a9 9 0 1 0 2.64-6.36L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    search: '<circle cx="10.8" cy="10.8" r="6.8"/><path d="m16 16 4.5 4.5"/>',
    help: '<circle cx="12" cy="12" r="9"/><path d="M9.6 9a2.5 2.5 0 1 1 4.3 1.7c-1.1 1.1-1.9 1.4-1.9 3M12 17.5h.01"/>',
    inbox: '<path d="M4 4h16v16H4z"/><path d="M4 13h4l2 3h4l2-3h4"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    check: '<path d="m5 12 4 4L19 6"/>',
    person: '<circle cx="12" cy="8" r="4"/><path d="M5 21a7 7 0 0 1 14 0"/>',
    filter: '<path d="M4 6h16M7 12h10m-7 6h4"/>',
    spark: '<path d="m12 3 1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3Z"/><path d="m19 16 .8 2.2L22 19l-2.2.8L19 22l-.8-2.2L16 19l2.2-.8L19 16Z"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    lock: '<rect x="4" y="10" width="16" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3M12 14v3"/>',
    car: '<path d="m5 11 1.5-5h11L19 11l2 2v5h-2v-2H5v2H3v-5z"/><path d="M6 11h12M6.5 14h.01M17.5 14h.01"/>',
    database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    play: '<path d="m8 5 11 7-11 7z"/>',
    expand: '<path d="M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3"/>',
    video: '<rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 10 4-3v10l-4-3z"/>',
    upload: '<path d="M12 16V4m-5 5 5-5 5 5"/><path d="M4 16v4h16v-4"/>',
    camera: '<path d="M4 7h3l2-3h6l2 3h3a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z"/><circle cx="12" cy="13" r="4"/>',
    close: '<path d="m6 6 12 12M18 6 6 18"/>',
    record: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3" fill="currentColor" stroke="none"/>',
    print: '<path d="M7 8V3h10v5M7 17H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-3"/><path d="M7 14h10v7H7zM18 11h.01"/>',
    download: '<path d="M12 3v12m-5-5 5 5 5-5"/><path d="M4 17v4h16v-4"/>',
    more: '<circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/>'
  };
  document.querySelectorAll('[data-icon]').forEach((el) => {
    const name = el.dataset.icon;
    if (!iconPaths[name]) return;
    el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name]}</svg>`;
  });

  const state = {
    view: 'overview',
    tab: 'assessment',
    opening: 7500,
    target: 8500,
    cap: 9500,
    offer: 7500,
    roundsUsed: 0,
    maxRounds: 3,
    decision: null,
    events: [],
    files: [],
    objectUrls: [],
    recording: false,
    stream: null,
    recorder: null,
    recordedChunks: [],
    recordStartedAt: null,
    timerHandle: null
  };

  const auditEvents = [
    {time:'10:42:18', kind:'blue', title:'Evidence received', detail:'Continuous 18-second walkaround · 1080p · sample media record.', tag:'EVIDENCE'},
    {time:'10:42:19', kind:'blue', title:'Policy and capture pre-checks passed', detail:'Active policy · supported duration and resolution · lighting/sharpness check passed.', tag:'PRE-CHECK'},
    {time:'10:43:04', kind:'blue', title:'Vehicle identity and continuity verified', detail:'Plate KA 03 •• 4921 matched the sample vehicle. One tracked vehicle; no scene cut detected.', tag:'IDENTITY'},
    {time:'10:44:11', kind:'green', title:'Damage assessment completed', detail:'Driver-side front door · L4 creased dent · 8.4% panel coverage · 96% confidence.', tag:'ASSESSMENT'},
    {time:'10:44:26', kind:'green', title:'Safety and pre-existing checks passed', detail:'No rust, panel-gap shift, or safety-critical damage visible in the sample evidence.', tag:'GUARDRAIL'},
    {time:'10:45:02', kind:'green', title:'Repair estimate calculated', detail:'₹10,620 garage repair estimate · ₹620 deductible · ₹10,000 net eligible claim.', tag:'ESTIMATE'},
    {time:'10:45:04', kind:'green', title:'Settlement window locked', detail:'₹7,500 initial offer · ₹8,500 target · ₹9,500 maximum (75% / 85% / 95%).', tag:'OFFER RULE'},
    {time:'10:46:00', kind:'green', title:'Initial cash offer presented', detail:'Offer card bound to the approved settlement range. This is an illustrative UI state.', tag:'CUSTOMER OFFER'}
  ];
  const escapeHTML = (text) => String(text).replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  let toastTimer;
  function toast(message) {
    const node = document.getElementById('toast');
    node.textContent = message;
    node.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove('show'), 3000);
  }
  function setView(name) {
    const target = document.getElementById(`view-${name}`);
    if (!target) return;
    state.view = name;
    document.querySelectorAll('.view').forEach((view) => view.classList.toggle('is-active', view === target));
    document.querySelectorAll('.nav-item').forEach((button) => {
      const selected = button.dataset.view === name || (name === 'audit' && button.dataset.view === 'audit');
      button.classList.toggle('is-active', selected);
    });
    document.querySelectorAll('.mobile-nav-item').forEach((button) => button.classList.toggle('is-active', button.dataset.view === name));
    const context = document.getElementById('topbar-context');
    if (context) context.textContent = target.dataset.title || 'Overview';
    if (name === 'audit') renderAudit();
    window.scrollTo({top:0, behavior:window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth'});
  }
  function setClaimTab(name) {
    state.tab = name;
    document.querySelectorAll('[data-case-panel]').forEach((panel) => panel.classList.toggle('is-active', panel.dataset.casePanel === name));
    document.querySelectorAll('.case-tab').forEach((button) => button.classList.toggle('is-active', button.dataset.claimTab === name));
    document.querySelectorAll('.workflow-step').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.claimTab === name);
      if (['estimate','settlement','audit','decision'].includes(name)) {
        const idx = ['assessment','estimate','settlement','audit','decision'].indexOf(name);
        const stepName = ['assessment','estimate','settlement','audit','decision'][idx];
        button.classList.toggle('is-complete', ['assessment','estimate','settlement','audit'].indexOf(button.dataset.claimTab) < idx);
      } else if (button.dataset.claimTab === 'assessment') button.classList.remove('is-complete');
    });
    if (name === 'audit') renderAudit();
    if (name === 'decision') renderDecision();
    window.scrollTo({top:0, behavior:'smooth'});
  }
  document.addEventListener('click', (event) => {
    const viewControl = event.target.closest('[data-view]');
    if (viewControl) {
      event.preventDefault();
      const view = viewControl.dataset.view;
      setView(view);
      if (view === 'claim') setClaimTab('assessment');
      return;
    }
    const tabControl = event.target.closest('[data-claim-tab]');
    if (tabControl) {
      event.preventDefault();
      if (state.view !== 'claim') setView('claim');
      setClaimTab(tabControl.dataset.claimTab);
      return;
    }
    const actionControl = event.target.closest('[data-action]');
    if (actionControl) handleAction(actionControl.dataset.action, actionControl);
  });
  document.querySelectorAll('.claim-row').forEach((row) => row.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); setView('claim'); setClaimTab('assessment'); }
  }));
  function pushEvent(title, detail, kind='green', tag='LOCAL DEMO') {
    const now = new Date();
    state.events.push({time:now.toLocaleTimeString('en-GB',{hour:'2-digit',minute:'2-digit',second:'2-digit'}),kind,title,detail,tag});
    renderAudit();
  }
  function renderAudit() {
    const all = [...auditEvents, ...state.events];
    const timeline = all.map((item, index) => `<div class="audit-event ${escapeHTML(item.kind)}"><time class="audit-time">${escapeHTML(item.time)}</time><span class="audit-marker"><span class="icon" data-icon="${item.kind === 'amber' || item.kind === 'red' ? 'info' : 'check'}"></span></span><div class="audit-event-copy"><strong>${escapeHTML(item.title)}</strong><p>${escapeHTML(item.detail)}</p></div><span class="audit-event-tag">${escapeHTML(item.tag)}</span></div>`).join('');
    document.querySelectorAll('.audit-timeline').forEach((node) => { node.innerHTML = `<p class="timeline-date">22 OCT 2026 <span>· SAMPLE CLAIM ACTIVITY</span></p>${timeline}`; });
    document.querySelectorAll('#audit-decision-label,#audit-page-decision').forEach((node) => { node.textContent = state.decision ? (state.decision.type === 'settled' ? 'Cash settlement accepted' : state.decision.type === 'garage' ? 'Cashless garage selected' : 'Human review requested') : 'Offer pending'; });
    document.querySelectorAll('.audit-timeline [data-icon]').forEach((el) => { const name=el.dataset.icon; el.innerHTML=`<svg viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name]||iconPaths.check}</svg>`; });
  }
  function recordCustomerMessage(text) {
    const stream = document.getElementById('message-stream');
    const row = document.createElement('div');
    row.className = 'message-row user-message';
    row.innerHTML = `<span class="message-avatar user-avatar">RM</span><div><div class="message-meta"><span>10:47 AM</span><strong>Rohan</strong></div><div class="message-bubble">${escapeHTML(text)}</div></div>`;
    stream.appendChild(row);
    stream.scrollTop = stream.scrollHeight;
  }
  function recordAgentMessage(text) {
    const stream = document.getElementById('message-stream');
    const row = document.createElement('div');
    row.className = 'message-row agent-message';
    row.innerHTML = `<span class="message-avatar agent-avatar">A</span><div><div class="message-meta"><strong>Auto-Settle</strong><span>Just now</span></div><div class="message-bubble">${escapeHTML(text)}</div></div>`;
    stream.appendChild(row);
    stream.scrollTop = stream.scrollHeight;
  }
  function updateOfferUI() {
    const amount = money(state.offer);
    document.getElementById('side-offer-amount').textContent = amount;
    document.getElementById('conversation-offer').textContent = amount;
    document.getElementById('current-offer-rail').textContent = amount;
    document.getElementById('accept-offer').textContent = `Accept ${amount}`;
    document.getElementById('round-badge').textContent = `ROUND ${Math.min(state.roundsUsed + 1,3)} OF 3`;
    const fill = document.getElementById('conversation-range-fill');
    if (fill) fill.style.width = `${Math.max(0, Math.min(100, (state.offer-state.opening)/(state.cap-state.opening)*100))}%`;
  }
  function appendOfferCard(roundNumber) {
    const stream = document.getElementById('message-stream');
    const card = document.createElement('div');
    card.className = 'offer-message';
    card.innerHTML = `<div class="offer-card-mini"><div><span class="small-caps">CASH OFFER · ROUND ${roundNumber}</span><strong>${money(state.offer)}</strong><small>Within your approved settlement range</small></div><span class="signed-mark"><span class="icon" data-icon="lock"><svg viewBox="0 0 24 24">${iconPaths.lock}</svg></span> RANGE<br>CHECKED</span></div><div class="offer-actions"><button class="button button-green dynamic-accept" type="button">Accept ${money(state.offer)}</button><span class="or-divider">or</span><span class="offer-actions-hint">make a counteroffer below</span></div>`;
    card.querySelector('.dynamic-accept').addEventListener('click', () => settle(state.offer));
    stream.appendChild(card);
    stream.scrollTop = stream.scrollHeight;
  }
  function handleCounter() {
    const input = document.getElementById('counter-amount');
    const reason = document.getElementById('counter-reason');
    const error = document.getElementById('counter-error');
    const amount = Number(input.value);
    error.textContent = '';
    if (!Number.isFinite(amount) || amount <= 0) { error.textContent = 'Enter a counteroffer greater than ₹0.'; input.focus(); return; }
    const explanation = reason.value.trim();
    recordCustomerMessage(`Could you settle at ${money(amount)}?${explanation ? ` ${explanation}` : ''}`);
    pushEvent('Customer counteroffer received', `${money(amount)} requested${explanation ? ` · reason: ${explanation}` : ''}.`, 'blue', 'COUNTEROFFER');
    if (amount > state.cap) {
      error.textContent = `${money(amount)} is above the ₹9,500 approved ceiling. That amount cannot be issued as an automated offer.`;
      recordAgentMessage(`I can’t issue ${money(amount)} as a cash settlement. The approved maximum is ${money(state.cap)}. You can accept the current offer, ask for human review, or choose a cashless garage repair.`);
      pushEvent('Above-cap request blocked', `Requested ${money(amount)}; automated limit remains ${money(state.cap)}. Offer was not changed.`, 'amber', 'GUARDRAIL');
      showFinalChoices();
      input.value = '';
      return;
    }
    if (amount <= state.offer) {
      recordAgentMessage(`We can accept your counteroffer of ${money(amount)} because it remains within the approved range.`);
      settle(amount, 'Customer accepted at a lower amount.');
      input.value = '';
      return;
    }
    if (state.roundsUsed >= state.maxRounds) {
      recordAgentMessage(`We’ve reached the limit of ${state.maxRounds} negotiation rounds. The current approved offer is ${money(state.offer)}. You can accept it, choose a cashless garage, or request a human adjuster.`);
      showFinalChoices();
      input.value = '';
      return;
    }
    const ceiling = state.roundsUsed === 0 ? state.target : state.cap;
    const alpha = explanation ? 0.5 : 0.25;
    const candidate = state.offer + (Math.min(amount, ceiling) - state.offer) * alpha;
    const next = Math.max(state.offer, Math.min(ceiling, state.cap, Math.round(candidate / 100) * 100));
    state.offer = next;
    state.roundsUsed += 1;
    updateOfferUI();
    recordAgentMessage(`Thanks for explaining. The first counteroffer moves toward the approved target. The new offer is ${money(next)}. The range is unchanged, and the ₹9,500 limit still applies.`);
    appendOfferCard(Math.min(state.roundsUsed + 1,3));
    pushEvent('Bounded counteroffer presented', `${money(next)} · round ${state.roundsUsed} of 3 · capped at 85% target on the first response and 95% maximum thereafter.`, 'green', 'OFFER RULE');
    input.value = '';
    reason.value = '';
    toast(`New approved offer: ${money(next)}`);
  }
  document.getElementById('send-counter').addEventListener('click', handleCounter);
  document.getElementById('counter-amount').addEventListener('keydown', (event) => { if (event.key === 'Enter') { event.preventDefault(); handleCounter(); } });
  document.getElementById('accept-offer').addEventListener('click', () => settle(state.offer));
  function showFinalChoices() {
    const wrap = document.getElementById('negotiation-form-wrap');
    wrap.classList.add('is-hidden');
    const stream = document.getElementById('message-stream');
    if (document.getElementById('final-choice-panel')) return;
    const panel = document.createElement('div');
    panel.id = 'final-choice-panel';
    panel.className = 'settled-banner';
    panel.style.background = '#fbf6ed';
    panel.style.borderColor = '#eadfc9';
    panel.innerHTML = `<span class="settled-icon" style="background:#f2e8d6;color:#9b7540"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths.info}</svg></span></span><div><strong>Choose the next step</strong><p>Accept ${money(state.offer)}, request human review, or continue with a cashless garage.</p></div><div class="decision-actions" style="padding:0;flex-wrap:wrap"><button class="button button-green" type="button" data-choice="accept">Accept offer</button><button class="button button-outline" type="button" data-choice="human">Human review</button><button class="button button-outline" type="button" data-choice="garage">Cashless garage</button></div>`;
    panel.querySelector('[data-choice="accept"]').addEventListener('click', () => settle(state.offer));
    panel.querySelector('[data-choice="human"]').addEventListener('click', () => escalate('Customer requested human review after the offer limit was reached.'));
    panel.querySelector('[data-choice="garage"]').addEventListener('click', () => chooseGarage());
    stream.appendChild(panel);
    stream.scrollTop = stream.scrollHeight;
  }
  function settle(amount, note='Customer accepted the current approved offer.') {
    if (amount < state.opening || amount > state.cap) {
      pushEvent('Settlement blocked by range guardrail', `${money(amount)} is outside the approved ₹7,500–₹9,500 band.`, 'red', 'BLOCKED');
      toast('That settlement is outside the approved range.');
      return;
    }
    state.decision = {type:'settled', amount, note, confirmed:false, time:new Date().toISOString()};
    document.getElementById('final-amount-label').textContent = money(amount);
    document.getElementById('negotiation-form-wrap').classList.add('is-hidden');
    document.getElementById('settled-banner').classList.remove('is-hidden');
    document.getElementById('accept-offer').disabled = true;
    pushEvent('Cash settlement accepted', `${money(amount)} accepted within the approved range. ${note}`, 'green', 'DECISION');
    renderDecision();
    setClaimTab('decision');
    toast('Accepted amount is inside the approved range.');
  }
  function escalate(reason) {
    state.decision = {type:'human', reason, time:new Date().toISOString()};
    pushEvent('Human review requested', reason, 'amber', 'ESCALATION');
    renderDecision();
    setClaimTab('decision');
    toast('This sample claim is now in the human-review state.');
  }
  function chooseGarage() {
    state.decision = {type:'garage', reason:'Customer chose cashless garage repair instead of cash-in-lieu.', time:new Date().toISOString()};
    pushEvent('Cashless garage path selected', state.decision.reason, 'blue', 'ALTERNATE PATH');
    renderDecision();
    setClaimTab('decision');
    toast('Cashless garage path selected in the demo.');
  }
  function renderDecision() {
    const root = document.getElementById('decision-content');
    if (!state.decision) {
      root.innerHTML = `<div class="decision-empty"><span class="decision-icon"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths.file}</svg></span></span><p class="eyebrow">FINAL OUTCOME</p><h2>No decision yet.</h2><p>Review the evidence and offer conversation. An accepted cash offer or a human escalation will appear here with the next steps.</p><button class="button button-green" type="button" data-claim-tab="settlement">Continue settlement <span>→</span></button></div>`;
      return;
    }
    const d = state.decision;
    if (d.type === 'settled') {
      root.innerHTML = `<article class="decision-result"><header class="decision-result-head"><span class="result-icon"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths.check}</svg></span></span><div><p class="eyebrow">CASH-IN-LIEU · WITHIN APPROVED RANGE</p><h2>Offer accepted.</h2></div></header><div class="decision-result-body"><p>Rohan accepted the cash settlement for the assessed driver-side door damage. The amount is within the approved 75–95% range.</p><div class="decision-amount">${money(d.amount)}</div><div class="decision-meta"><span>Garage estimate<strong>₹10,620</strong></span><span>Eligible range<strong>₹7,500–₹9,500</strong></span><span>Offer status<strong>${d.confirmed ? 'Confirmed locally' : 'Awaiting confirmation'}</strong></span></div><p><strong>Next:</strong> ${d.confirmed ? 'The local demo state is confirmed. A real payout is not connected.' : 'Confirm the sample outcome to update the demo audit trail.'}</p></div><div class="decision-actions">${d.confirmed ? '<span class="status-tag status-ready"><i></i>Demo confirmation saved</span>' : '<button class="button button-green" type="button" data-action="confirm-settlement">Confirm sample settlement <span>→</span></button>'}<button class="button button-outline" type="button" data-claim-tab="audit">View audit trail</button></div></article>`;
    } else if (d.type === 'garage') {
      root.innerHTML = `<article class="decision-result"><header class="decision-result-head"><span class="result-icon"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths.car}</svg></span></span><div><p class="eyebrow">ALTERNATE REPAIR PATH</p><h2>Cashless garage selected.</h2></div></header><div class="decision-result-body"><p>The customer chose a network garage instead of a cash-in-lieu payout. The claim should continue through the garage inspection and repair process.</p><div class="decision-meta"><span>Cash payout<strong>None</strong></span><span>Repair estimate<strong>₹10,620</strong></span><span>Next step<strong>Garage inspection</strong></span></div></div><div class="decision-actions"><button class="button button-outline" type="button" data-claim-tab="audit">View audit trail</button></div></article>`;
    } else {
      root.innerHTML = `<article class="decision-result"><header class="decision-result-head escalated"><span class="result-icon"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths.person}</svg></span></span><div><p class="eyebrow">AUTOMATION PAUSED · NO CASH OFFER</p><h2>Human review needed.</h2></div></header><div class="decision-result-body"><p>This claim cannot safely be decided automatically. No new amount has been approved. The customer should receive a clear next step rather than an unsupported decision.</p><div class="ncb-note"><span class="ncb-icon">!</span><div><strong>Reason for escalation</strong><p>${escapeHTML(d.reason)}</p></div></div><div class="decision-meta"><span>Offer outside cap<strong>Blocked</strong></span><span>Human queue<strong>Claims adjuster</strong></span><span>Next step<strong>Review evidence</strong></span></div><p><strong>Customer message:</strong> “We’re sending this claim to a specialist so we can review it carefully. We’ll update you with the next step.”</p></div><div class="decision-actions"><button class="button button-outline" type="button" data-claim-tab="audit">View audit trail</button><button class="button button-outline" type="button" data-view="guardrails">Review guardrails</button></div></article>`;
    }
  }
  function handleAction(action) {
    if (action === 'print') { window.print(); return; }
    if (action === 'download-audit') { downloadAudit(); return; }
    if (action === 'zoom') {
      const figure = document.querySelector('.evidence-figure');
      figure.classList.toggle('is-expanded');
      toast(figure.classList.contains('is-expanded') ? 'Evidence expanded. Activate again to restore.' : 'Evidence restored.');
      return;
    }
    if (action === 'confirm-settlement') {
      if (!state.decision || state.decision.type !== 'settled') return;
      state.decision.confirmed = true;
      pushEvent('Sample settlement confirmed locally', `${money(state.decision.amount)} · no payout or network request is connected.`, 'green', 'DEMO CONFIRMATION');
      renderDecision();
      toast('Sample decision confirmed locally; no payout was sent.');
    }
  }
  function downloadAudit() {
    const record = {
      record_type:'illustrative_frontend_demo',
      claim_id:'CLM-48291',
      vehicle:{make_model:'Hyundai Creta',year:2022,registration_masked:'KA 03 •• 4921'},
      damage:{component:'Driver-side front door',type:'Creased dent',severity:'L4 · moderate',panel_coverage_percent:8.4,confidence_percent:96},
      estimate:{garage_repair_inr:10620,deductible_inr:620,net_eligible_inr:10000,opening_offer_inr:7500,target_offer_inr:8500,maximum_offer_inr:9500,autonomous_repair_limit_inr:25000},
      decision:state.decision ? {...state.decision, amount_inr:state.decision.amount} : {status:'pending'},
      events:[...auditEvents,...state.events],
      disclaimer:'Illustrative local frontend state. Not a signed, persistent, or legally authoritative claim record.'
    };
    const blob = new Blob([JSON.stringify(record,null,2)],{type:'application/json'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'auto-settle-CLM-48291-audit-demo.json';
    link.click();
    URL.revokeObjectURL(url);
    toast('Illustrative audit JSON downloaded.');
  }

  const fileInput = document.getElementById('evidence-file');
  const dropzone = document.getElementById('dropzone');
  fileInput.addEventListener('change', () => addFiles(Array.from(fileInput.files || [])));
  ['dragenter','dragover'].forEach((type) => dropzone.addEventListener(type, (event) => {event.preventDefault();dropzone.classList.add('drag-over');}));
  ['dragleave','drop'].forEach((type) => dropzone.addEventListener(type, (event) => {event.preventDefault();dropzone.classList.remove('drag-over');}));
  dropzone.addEventListener('drop', (event) => addFiles(Array.from(event.dataTransfer.files || [])));
  function addFiles(files) {
    const mediaFiles = files.filter((file) => file.type.startsWith('image/') || file.type.startsWith('video/'));
    const rejected = files.length - mediaFiles.length;
    const tooLarge = mediaFiles.filter((file) => file.size > 20 * 1024 * 1024);
    const valid = mediaFiles.filter((file) => file.size <= 20 * 1024 * 1024);
    if (tooLarge.length) toast('Each file must be 20 MB or smaller. Oversized media was not added.');
    if (state.files.length + valid.length > 6) toast('Up to 6 evidence files can be previewed at once.');
    valid.slice(0, Math.max(0, 6 - state.files.length)).forEach((file) => {
      const url = URL.createObjectURL(file);
      state.files.push({file,url,id:`${Date.now()}-${Math.random().toString(16).slice(2)}`});
      state.objectUrls.push(url);
    });
    if (rejected) toast('Only image or video files can be previewed.');
    renderPreviews();
  }
  function renderPreviews() {
    const section = document.getElementById('upload-preview');
    const list = document.getElementById('preview-list');
    section.classList.toggle('is-hidden', state.files.length === 0);
    list.innerHTML = '';
    state.files.forEach((item) => {
      const node = document.createElement('div');
      node.className = 'preview-item';
      const media = item.file.type.startsWith('video/') ? document.createElement('video') : document.createElement('img');
      media.src = item.url;
      if (media.tagName === 'VIDEO') { media.controls = true; media.muted = true; }
      else media.alt = `Preview of ${item.file.name}`;
      const label = document.createElement('span');
      label.textContent = `${item.file.name} · ${(item.file.size/1024/1024).toFixed(1)} MB`;
      const remove = document.createElement('button');
      remove.type = 'button'; remove.className = 'preview-remove'; remove.setAttribute('aria-label',`Remove ${item.file.name}`);
      remove.innerHTML = `<span class="icon"><svg viewBox="0 0 24 24">${iconPaths.close}</svg></span>`;
      remove.addEventListener('click', () => {URL.revokeObjectURL(item.url);state.files=state.files.filter((file)=>file.id!==item.id);renderPreviews();});
      node.append(media,label,remove);list.appendChild(node);
    });
  }
  document.getElementById('clear-upload').addEventListener('click', () => {state.files.forEach((item)=>URL.revokeObjectURL(item.url));state.files=[];renderPreviews();});

  const form = document.getElementById('claim-form');
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    if (!state.files.length) {toast('Add at least one vehicle image or video before continuing.');document.getElementById('dropzone').scrollIntoView({behavior:'smooth',block:'center'});return;}
    const old = document.getElementById('intake-result');
    if (old) old.remove();
    const result = document.createElement('section');
    result.id='intake-result';result.className='panel';result.style.cssText='grid-column:1/-1;padding:15px;display:flex;align-items:center;gap:12px;border-color:#dfe8dc;background:#f2f6ef';
    result.innerHTML=`<span class="large-status-icon"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths.check}</svg></span></span><div style="flex:1"><strong style="font-size:11px">Evidence ready for review</strong><p style="font-size:9px;color:#788579;margin:3px 0 0">${state.files.length} local file${state.files.length===1?'':'s'} selected for ${escapeHTML(document.getElementById('vehicle-model').value)}. This prototype does not run automated analysis.</p></div><button type="button" class="button button-green" id="open-sample-review">Explore the sample assessment <span>→</span></button>`;
    document.querySelector('.intake-submit-bar').before(result);
    document.getElementById('open-sample-review').addEventListener('click',()=>{setView('claim');setClaimTab('assessment');});
    pushEvent('New evidence previewed locally',`${state.files.length} selected file(s); no server upload or analysis was run.`,'blue','INTAKE DEMO');
    toast('Evidence preview is ready. No data was sent.');
  });

  const cameraDialog=document.getElementById('camera-dialog');
  const cameraPreview=document.getElementById('camera-preview');
  const cameraPlaceholder=document.getElementById('camera-placeholder');
  const openCamera=document.getElementById('open-camera');
  openCamera.addEventListener('click',()=>{if(typeof cameraDialog.showModal==='function')cameraDialog.showModal();else toast('Live capture needs a browser with dialog support.');});
  document.getElementById('close-camera').addEventListener('click',closeCamera);
  cameraDialog.addEventListener('click',(event)=>{if(event.target===cameraDialog)closeCamera();});
  document.getElementById('start-camera').addEventListener('click',async()=>{
    try{
      if(!navigator.mediaDevices?.getUserMedia)throw new Error('Camera access is unavailable here. Try a secure browser page or choose a file instead.');
      state.stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:'environment'},width:{ideal:1280},height:{ideal:720}},audio:false});
      cameraPreview.srcObject=state.stream;cameraPreview.classList.remove('is-hidden');cameraPlaceholder.classList.add('is-hidden');document.getElementById('record-video').disabled=false;toast('Camera preview is ready.');
    }catch(error){toast(error.message||'Camera permission was not available. Choose a file instead.');}
  });
  document.getElementById('record-video').addEventListener('click',()=>{
    if(!state.stream)return;
    if(!window.MediaRecorder){toast('Video recording is not supported in this browser. You can still upload a video.');return;}
    try{
      state.recordedChunks=[];state.recorder=new MediaRecorder(state.stream);state.recorder.ondataavailable=(event)=>{if(event.data.size)state.recordedChunks.push(event.data);};
      state.recorder.onstop=()=>{const blob=new Blob(state.recordedChunks,{type:state.recorder.mimeType||'video/webm'});const file=new File([blob],`walkaround-${new Date().toISOString().slice(0,10)}.webm`,{type:blob.type});addFiles([file]);document.getElementById('finish-recording').classList.add('is-hidden');document.getElementById('record-video').classList.remove('is-hidden');document.getElementById('record-indicator').classList.add('is-hidden');closeCamera();toast('Recorded video added to your local evidence preview.');};
      state.recorder.start();state.recording=true;state.recordStartedAt=Date.now();document.getElementById('record-indicator').classList.remove('is-hidden');document.getElementById('record-video').classList.add('is-hidden');document.getElementById('finish-recording').classList.remove('is-hidden');
      state.timerHandle=setInterval(()=>{const seconds=Math.floor((Date.now()-state.recordStartedAt)/1000);document.getElementById('record-timer').textContent=`${String(Math.floor(seconds/60)).padStart(2,'0')}:${String(seconds%60).padStart(2,'0')}`;},300);
    }catch(error){toast('Could not start recording. Use the upload option instead.');}
  });
  document.getElementById('finish-recording').addEventListener('click',()=>{if(state.recorder?.state==='recording')state.recorder.stop();});
  function closeCamera(){
    if(state.recorder?.state==='recording')state.recorder.stop();
    if(state.stream){state.stream.getTracks().forEach((track)=>track.stop());state.stream=null;}
    clearInterval(state.timerHandle);state.recording=false;cameraPreview.srcObject=null;cameraPreview.classList.add('is-hidden');cameraPlaceholder.classList.remove('is-hidden');
    document.getElementById('record-video').disabled=true;document.getElementById('record-video').classList.remove('is-hidden');document.getElementById('finish-recording').classList.add('is-hidden');document.getElementById('record-indicator').classList.add('is-hidden');
    if(cameraDialog.open)cameraDialog.close();
  }

  const scenarioData={
    clear:{level:'clear',title:'Continue to bounded offer',text:'Evidence is clear and the claim remains inside the autonomous limit.'},
    confidence:{level:'warning',title:'Pause for human review',text:'Below 55% confidence is not enough to make a safe automated decision. Route to a desk adjuster.'},
    safety:{level:'danger',title:'Stop · physical inspection',text:'A safety-critical part cannot receive a cash-in-lieu offer. Route the claimant to a garage inspection.'},
    continuity:{level:'warning',title:'Re-record live evidence',text:'Video continuity failed. Do not connect the close-up to this vehicle; request one unbroken browser-camera capture.'},
    limit:{level:'danger',title:'Licensed surveyor required',text:'A net repair estimate above ₹25,000 is outside autonomous approval. No cash offer is issued.'},
    rust:{level:'warning',title:'Pause · possible pre-existing damage',text:'Possible rust is uncertain evidence, not a fraud finding. Escalate for a human review.'}
  };
  const scenarioIcons={clear:'check',warning:'info',danger:'shield'};
  document.getElementById('scenario-select').addEventListener('change',(event)=>{
    const item=scenarioData[event.target.value];const root=document.getElementById('scenario-result');
    root.className=`scenario-result ${item.level==='clear'?'':item.level}`;
    root.innerHTML=`<span class="scenario-result-icon ${item.level}"><span class="icon"><svg viewBox="0 0 24 24">${iconPaths[scenarioIcons[item.level]]}</svg></span></span><div><span class="small-caps">CURRENT OUTCOME</span><strong>${item.title}</strong><p>${item.text}</p></div>`;
  });

  const dateNode=document.getElementById('today-label');
  if(dateNode){const now=new Date();dateNode.textContent=`${now.toLocaleDateString('en-US',{weekday:'long'}).toUpperCase()} · CLAIMS DESK`;}
  updateOfferUI();
  renderAudit();
  document.querySelector('.evidence-figure').addEventListener('click',(event)=>{if(event.target.closest('.zoom-control'))return;});
  document.querySelector('.evidence-figure').classList.remove('is-expanded');
})();
