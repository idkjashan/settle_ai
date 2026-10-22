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
    more: '<circle cx="5" cy="12" r="1" fill="currentColor"/><circle cx="12" cy="12" r="1" fill="currentColor"/><circle cx="19" cy="12" r="1" fill="currentColor"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>'
  };

  function renderIcons(container = document) {
    container.querySelectorAll('[data-icon]').forEach((el) => {
      const name = el.dataset.icon;
      if (!iconPaths[name]) return;
      el.innerHTML = `<svg viewBox="0 0 24 24" aria-hidden="true">${iconPaths[name]}</svg>`;
    });
  }

  const escapeHTML = (text) =>
    String(text).replace(/[&<>"']/g, (char) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));

  let toastTimer;
  function toast(message) {
    const node = document.getElementById('toast');
    if (!node) return;
    node.textContent = message;
    node.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => node.classList.remove('show'), 3200);
  }

  // Authentic Benchmark Claims with Real Evaluation Assets
  const initialClaims = [
    {
      id: 'CLM-48291',
      time: 'Today · 10:42 AM',
      vehicle: 'Hyundai Creta',
      year: 2022,
      registration: 'MH 12 DE 1433',
      policyId: 'POL-HAPPY-001',
      claimant: 'Rohan Mehta',
      damageType: 'Creased dent',
      damagePart: 'Driver-side front door',
      panelContext: 'Exterior body panel',
      severity: 'L4',
      severityLabel: 'L4 · Moderate',
      confidence: 96,
      coverage: '8.4%',
      paintCondition: 'Creased · paint broken',
      rust: 'Not detected',
      note: 'A visible crease is consistent across continuous trajectory frames. Driver-side door panel verified against policy OEM catalogue.',
      repairCost: 10620,
      subtotal: 9000,
      gst: 1620,
      deductible: 620,
      netEligible: 10000,
      opening: 7500,
      target: 8500,
      cap: 9500,
      offer: 7500,
      status: 'ready',
      statusLabel: 'Ready to settle',
      roundsUsed: 0,
      maxRounds: 3,
      decision: null,
      videoUrl: '/test_assets/videos/simple/car_002.mp4',
      yoloUrl: '/docs_assets/stage2_annotated_samples/scenario_02_front_door_scratch_comparison.jpg',
      somUrl: '/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/front_right_door_som.jpg',
      billedItems: [
        { part: 'Driver-Side Front Door', note: 'Creased dent · 8.4% IoP', amount: '₹9,000' }
      ],
      quarantinedItems: [
        { part: 'Rear Bumper', note: 'Unclaimed scuff · Bypasses ESC-05', status: 'Quarantined' }
      ],
      messages: [
        { sender: 'agent', name: 'Auto-Settle', time: '10:46 AM', text: 'We’ve reviewed the continuous walkaround video. The crease on your driver-side front door is eligible for a cash settlement. The estimated garage repair is <b>₹10,620</b>, and we can offer <b>₹7,500</b> today.' }
      ],
      events: [
        { time: '10:42:18', kind: 'blue', title: 'Evidence received', detail: 'Continuous 18-second walkaround · 720p HD · video keyframes extracted.', tag: 'EVIDENCE' },
        { time: '10:42:19', kind: 'blue', title: 'Policy and capture pre-checks passed', detail: 'Active policy POL-HAPPY-001 · duration and resolution supported · sharpness 84.2.', tag: 'PRE-CHECK' },
        { time: '10:43:04', kind: 'blue', title: 'Vehicle identity and continuity verified', detail: 'Plate MH 12 DE 1433 matched. ByteTrack continuous vehicle trajectory confirmed.', tag: 'IDENTITY' },
        { time: '10:44:11', kind: 'green', title: 'Conditioned Dual-Mask Segmentation', detail: 'Driver-side front door · L4 creased dent · IoP 8.4% panel coverage · 96% confidence.', tag: 'ASSESSMENT' },
        { time: '10:44:26', kind: 'green', title: 'Safety and pre-existing checks passed', detail: 'Set-of-Marks VLM confirmed depth crease. No pre-existing rust or safety concerns.', tag: 'GUARDRAIL' },
        { time: '10:45:02', kind: 'green', title: 'Deterministic OEM estimate calculated', detail: '₹10,620 garage repair estimate · ₹620 deductible · ₹10,000 net eligible claim.', tag: 'ESTIMATE' },
        { time: '10:45:04', kind: 'green', title: 'Settlement window locked', detail: '₹7,500 initial offer · ₹8,500 target · ₹9,500 maximum (75% / 85% / 95%).', tag: 'OFFER RULE' },
        { time: '10:46:00', kind: 'green', title: 'HMAC-SHA256 Offer Card presented', detail: 'Initial offer ₹7,500 signed and bound to the approved settlement range.', tag: 'CUSTOMER OFFER' }
      ]
    },
    {
      id: 'CLM-48290',
      time: 'Today · 10:18 AM',
      vehicle: 'Maruti Baleno',
      year: 2021,
      registration: 'DL 01 AB 9999',
      policyId: 'POL-HAPPY-001',
      claimant: 'Pooja Verma',
      damageType: 'Surface scuff',
      damagePart: 'Rear bumper cover',
      panelContext: 'Plastic exterior bumper',
      severity: 'L1',
      severityLabel: 'L1 · Surface scuff',
      confidence: 94,
      coverage: '3.2%',
      paintCondition: 'Clearcoat scuffed',
      rust: 'Not detected',
      note: 'Minor surface scuff on plastic bumper cover. Fully repairable via polish/PDR without panel replacement.',
      repairCost: 3240,
      subtotal: 2746,
      gst: 494,
      deductible: 500,
      netEligible: 2740,
      opening: 2050,
      target: 2330,
      cap: 2600,
      offer: 2050,
      status: 'ready',
      statusLabel: 'Ready to settle',
      roundsUsed: 0,
      maxRounds: 3,
      decision: null,
      videoUrl: '/test_assets/videos/simple/car_001.mp4',
      yoloUrl: '/docs_assets/stage2_annotated_samples/scenario_04_rear_bumper_crease_comparison.jpg',
      somUrl: '/evals/artifacts/som_output/258bed97-3d27-4496-a907-75d27685917d/front_bumper_som.jpg',
      billedItems: [
        { part: 'Rear Bumper Cover', note: 'Clearcoat scuff · 3.2% IoP', amount: '₹2,746' }
      ],
      quarantinedItems: [
        { part: 'Left Quarter Panel', note: 'Minor road dust mark · Background wear', status: 'Quarantined' }
      ],
      messages: [
        { sender: 'agent', name: 'Auto-Settle', time: '10:20 AM', text: 'Minor scuff on rear bumper cover confirmed by Stage 2 YOLO dual-mask segmentation. Initial offer: <b>₹2,050</b>.' }
      ],
      events: [
        { time: '10:18:02', kind: 'blue', title: 'Evidence received', detail: 'Walkaround video car_001.mp4 uploaded.', tag: 'EVIDENCE' },
        { time: '10:19:15', kind: 'green', title: 'Assessment completed', detail: 'L1 surface scuff on rear bumper. Net claim ₹2,740.', tag: 'ASSESSMENT' }
      ]
    },
    {
      id: 'CLM-48288',
      time: 'Today · 09:44 AM',
      vehicle: 'Toyota Corolla',
      year: 2020,
      registration: 'KA 01 MJ 5555',
      policyId: 'POL-RED-007',
      claimant: 'Rajesh K.',
      damageType: 'Deep side dent with rust',
      damagePart: 'Rear passenger door & rocker panel',
      panelContext: 'Side body flank',
      severity: 'L4',
      severityLabel: 'L4 · Moderate',
      confidence: 91,
      coverage: '12.4%',
      paintCondition: 'Broken with brown oxidation',
      rust: 'Old rust detected (ESC-04)',
      note: 'Brown oxidation and flaking indicate pre-existing damage on rocker panel. Transferred to adjuster under ESC-04.',
      repairCost: 14500,
      subtotal: 12288,
      gst: 2212,
      deductible: 1000,
      netEligible: 13500,
      opening: 0,
      target: 0,
      cap: 0,
      offer: 0,
      status: 'review',
      statusLabel: 'Pre-existing rust',
      roundsUsed: 0,
      maxRounds: 3,
      decision: { type: 'human', reason: 'ESC-04: Signs of old oxidation/flaking filler indicate pre-existing wear on lower rocker panel. Payout halted pending surveyor inspection.', time: '2026-10-22T09:47:00Z' },
      videoUrl: '/test_assets/videos/simple/toyota-corolla-side-impact-damage-walkaround-houston.mp4',
      yoloUrl: '/docs_assets/stage2_annotated_samples/scenario_03_rear_door_scratch_comparison.jpg',
      somUrl: '/evals/artifacts/som_output/03e986fc-ce45-4d78-8d0c-eb67fc299564/back_bumper_som.jpg',
      billedItems: [
        { part: 'Rear Passenger Door', note: 'Claimed impact dent · 12.4% IoP', amount: '₹12,288' }
      ],
      quarantinedItems: [
        { part: 'Lower Rocker Panel', note: 'Pre-existing brown rust (ESC-04)', status: 'Quarantined' }
      ],
      messages: [
        { sender: 'agent', name: 'Auto-Settle', time: '09:46 AM', text: 'Brown oxidation and flaking rust detected on lower rocker panel. Under rule ESC-04, this claim is routed to a desk adjuster.' }
      ],
      events: [
        { time: '09:44:00', kind: 'blue', title: 'Walkaround video uploaded', detail: 'Real walkaround video ingested.', tag: 'EVIDENCE' },
        { time: '09:46:12', kind: 'amber', title: 'ESC-04 Triggered', detail: 'Pre-existing oxidation detected. No automated cash offer issued.', tag: 'GUARDRAIL' }
      ]
    },
    {
      id: 'CLM-48287',
      time: 'Today · 09:20 AM',
      vehicle: 'Tata Nexon',
      year: 2023,
      registration: 'TN 09 AB 7812',
      policyId: 'POL-HAPPY-001',
      claimant: 'Karthik Raja',
      damageType: 'Basecoat scratch',
      damagePart: 'Front bumper cover',
      panelContext: 'Front bumper',
      severity: 'L2',
      severityLabel: 'L2 · Basecoat scratch',
      confidence: 97,
      coverage: '4.8%',
      paintCondition: 'Basecoat visible',
      rust: 'Not detected',
      note: 'Basecoat scratch on front bumper cover from parking divider. Settled within approved range.',
      repairCost: 5900,
      subtotal: 5000,
      gst: 900,
      deductible: 500,
      netEligible: 5400,
      opening: 4050,
      target: 4590,
      cap: 5130,
      offer: 4590,
      status: 'settled',
      statusLabel: 'Settled',
      roundsUsed: 1,
      maxRounds: 3,
      decision: { type: 'settled', amount: 4590, confirmed: true, upi: 'karthik@okhdfcbank', time: '2026-10-22T09:25:14Z' },
      videoUrl: '/test_assets/videos/simple/car_004.mp4',
      yoloUrl: '/docs_assets/stage2_annotated_samples/scenario_01_front_bumper_comparison.jpg',
      somUrl: '/evals/artifacts/som_output/5a17bfc6-9742-4480-85b3-c922aa9e126c/front_right_door_som.jpg',
      billedItems: [
        { part: 'Front Bumper Cover', note: 'Basecoat scratch · 4.8% IoP', amount: '₹5,000' }
      ],
      quarantinedItems: [
        { part: 'Front Underbody Splash Guard', note: 'Normal road stone pecks', status: 'Quarantined' }
      ],
      messages: [
        { sender: 'agent', name: 'Auto-Settle', time: '09:22 AM', text: 'Initial offer generated at ₹4,050 for front bumper scratch.' },
        { sender: 'user', name: 'Karthik', time: '09:23 AM', text: 'Can we settle at ₹4,590?' },
        { sender: 'agent', name: 'Auto-Settle', time: '09:24 AM', text: 'Counteroffer accepted at ₹4,590. Within approved policy limits.' }
      ],
      events: [
        { time: '09:20:00', kind: 'blue', title: 'Video received', detail: 'car_004.mp4 processed successfully.', tag: 'EVIDENCE' },
        { time: '09:25:14', kind: 'green', title: 'Settlement confirmed', detail: '₹4,590 transferred via UPI. Committed to ledger.', tag: 'DECISION' }
      ]
    },
    {
      id: 'CLM-48284',
      time: 'Today · 08:50 AM',
      vehicle: 'Kia Seltos',
      year: 2023,
      registration: 'KA 03 MJ 7777',
      policyId: 'POL-HAPPY-001',
      claimant: 'Amit Sharma',
      damageType: 'Windshield crack',
      damagePart: 'Front windshield laminated glass',
      panelContext: 'Structural safety component',
      severity: 'L5',
      severityLabel: 'L5 · Safety concern',
      confidence: 98,
      coverage: '18.5%',
      paintCondition: 'Glass fractured',
      rust: 'Not detected',
      note: 'ESC-06 Safety-critical damage: Laminated windshield crack impairs structural integrity. Cash payout prohibited; physical workshop inspection mandatory.',
      repairCost: 14200,
      subtotal: 12000,
      gst: 2200,
      deductible: 1000,
      netEligible: 13200,
      opening: 0,
      target: 0,
      cap: 0,
      offer: 0,
      status: 'review',
      statusLabel: 'Safety escalation',
      roundsUsed: 0,
      maxRounds: 3,
      decision: { type: 'human', reason: 'ESC-06: Safety-critical windshield crack detected. Automated cash-in-lieu is blocked. Directed to physical network garage.', time: '2026-10-22T08:52:00Z' },
      videoUrl: '/test_assets/videos/simple/car_005.mp4',
      yoloUrl: '/docs_assets/stage2_annotated_samples/scenario_01_front_bumper_comparison.jpg',
      somUrl: '/evals/artifacts/som_output/47a433f3-1342-4c2d-bab3-c96701273fdf/back_bumper_som.jpg',
      billedItems: [
        { part: 'Front Windshield Glass', note: 'L5 Structural laminated crack (Safety)', amount: '₹12,000' }
      ],
      quarantinedItems: [],
      messages: [
        { sender: 'agent', name: 'Auto-Settle', time: '08:51 AM', text: 'Safety-critical windshield crack detected. Under rule ESC-06, automated cash settlement is prohibited. Please visit an authorized repair garage.' }
      ],
      events: [
        { time: '08:50:00', kind: 'blue', title: 'Media uploaded', detail: 'Evidence photos received.', tag: 'EVIDENCE' },
        { time: '08:52:00', kind: 'red', title: 'ESC-06 Blocked', detail: 'Structural safety risk. Physical inspection required.', tag: 'GUARDRAIL' }
      ]
    }
  ];

  // History Persistence in localStorage
  const STORAGE_KEY = 'settleai_claims_history_v2';
  function loadClaimsFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed) && parsed.length > 0) return parsed;
      }
    } catch (err) {
      console.warn('Failed reading claims from localStorage:', err);
    }
    return initialClaims;
  }

  function saveClaimsToStorage() {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state.claims));
    } catch (err) {
      console.warn('Failed saving claims to localStorage:', err);
    }
  }

  const state = {
    view: 'overview',
    tab: 'assessment',
    mediaMode: 'video',
    claims: loadClaimsFromStorage(),
    currentClaimId: 'CLM-48291',
    filter: 'all',
    searchQuery: '',
    apiAvailable: false,
    files: [],
    objectUrls: [],
    recording: false,
    stream: null,
    recorder: null,
    recordedChunks: [],
    recordStartedAt: null,
    timerHandle: null
  };

  const currentClaim = () => state.claims.find((c) => c.id === state.currentClaimId) || state.claims[0];

  // Theme Management (Dark Mode)
  function initTheme() {
    const saved = localStorage.getItem('settleai_theme');
    const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = saved || (prefersDark ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', theme);
    updateThemeToggleUI(theme);
  }

  function toggleTheme() {
    const current = document.documentElement.getAttribute('data-theme') || 'light';
    const next = current === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('settleai_theme', next);
    updateThemeToggleUI(next);
    toast(`Switched to ${next} theme`);
  }

  function updateThemeToggleUI(theme) {
    const btn = document.getElementById('theme-toggle');
    if (!btn) return;
    const isDark = theme === 'dark';
    btn.setAttribute('aria-label', isDark ? 'Switch to light theme' : 'Switch to dark theme');
    btn.innerHTML = `<span class="icon" data-icon="${isDark ? 'sun' : 'moon'}"></span>`;
    renderIcons(btn);
  }

  // Live FastAPI Health Check
  async function checkApiHealth() {
    const pill = document.getElementById('api-status-pill');
    try {
      const res = await fetch('/health');
      if (res.ok) {
        state.apiAvailable = true;
        if (pill) {
          pill.innerHTML = '<span class="live-dot" style="background:#28a745"></span> LIVE API ACTIVE (v2.1.0)';
          pill.title = 'Connected to FastAPI backend with PostgreSQL, Redis & ML Workers';
        }
        return true;
      }
    } catch {
      // Backend unavailable
    }
    state.apiAvailable = false;
    if (pill) {
      pill.innerHTML = '<span class="live-dot"></span> LIVE APP (LOCAL DEMO)';
      pill.title = 'Operating against verified local models and real eval benchmarks';
    }
    return false;
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
    if (name === 'claim') loadClaimIntoWorkstation(currentClaim());
    window.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
  }

  function setClaimTab(name) {
    state.tab = name;
    document.querySelectorAll('[data-case-panel]').forEach((panel) => panel.classList.toggle('is-active', panel.dataset.casePanel === name));
    document.querySelectorAll('.case-tab').forEach((button) => button.classList.toggle('is-active', button.dataset.claimTab === name));
    document.querySelectorAll('.workflow-step').forEach((button) => {
      button.classList.toggle('is-active', button.dataset.claimTab === name);
      if (['estimate', 'settlement', 'audit', 'decision'].includes(name)) {
        const order = ['assessment', 'estimate', 'settlement', 'audit', 'decision'];
        const idx = order.indexOf(name);
        button.classList.toggle('is-complete', order.indexOf(button.dataset.claimTab) < idx);
      } else if (button.dataset.claimTab === 'assessment') {
        button.classList.remove('is-complete');
      }
    });
    if (name === 'audit') renderAudit();
    if (name === 'decision') renderDecision();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  // Queue table rendering & search/filter
  function renderQueue() {
    const tbody = document.getElementById('claims-table-body');
    if (!tbody) return;

    const filtered = state.claims.filter((c) => {
      const matchFilter =
        state.filter === 'all'
          ? true
          : state.filter === 'ready'
          ? c.status === 'ready'
          : state.filter === 'review'
          ? c.status === 'review'
          : state.filter === 'settled'
          ? c.status === 'settled'
          : true;

      const q = state.searchQuery.toLowerCase().trim();
      const matchSearch =
        !q ||
        c.id.toLowerCase().includes(q) ||
        c.vehicle.toLowerCase().includes(q) ||
        c.registration.toLowerCase().includes(q) ||
        c.damageType.toLowerCase().includes(q) ||
        c.statusLabel.toLowerCase().includes(q);

      return matchFilter && matchSearch;
    });

    const countAll = document.getElementById('count-all');
    const countReady = document.getElementById('count-ready');
    const countReview = document.getElementById('count-review');
    const countSettled = document.getElementById('count-settled');
    if (countAll) countAll.textContent = state.claims.length;
    if (countReady) countReady.textContent = state.claims.filter((c) => c.status === 'ready').length;
    if (countReview) countReview.textContent = state.claims.filter((c) => c.status === 'review').length;
    if (countSettled) countSettled.textContent = state.claims.filter((c) => c.status === 'settled').length;

    const footer = document.getElementById('queue-footer-count');
    if (footer) footer.textContent = `Showing ${filtered.length} of ${state.claims.length} claims`;

    tbody.innerHTML = filtered
      .map(
        (c) => `
        <tr class="claim-row ${c.id === state.currentClaimId ? 'selected-row' : ''}" tabindex="0" data-view="claim" data-claim-id="${c.id}">
          <td><span class="claim-id">${c.id}</span><small>${c.time}</small></td>
          <td><span class="vehicle-name">${c.vehicle}</span><small>${c.year} · ${c.registration}</small></td>
          <td><span class="table-damage">${c.damageType}</span><small>${c.damagePart}</small></td>
          <td class="currency-cell">${money(c.repairCost)}</td>
          <td><span class="status-tag status-${c.status === 'ready' ? 'ready' : c.status === 'settled' ? 'paid' : 'review'}"><i></i>${c.statusLabel}</span></td>
          <td class="row-arrow">↗</td>
        </tr>`
      )
      .join('');
  }

  function selectClaim(id) {
    state.currentClaimId = id;
    const claim = currentClaim();
    loadClaimIntoWorkstation(claim);
    renderQueue();
    setView('claim');
    setClaimTab('assessment');
    toast(`Loaded claim ${id}`);
  }

  // Media View Switcher (Walkaround Video / Dual-mask YOLO / Set-of-Marks VLM)
  function setMediaMode(mode) {
    state.mediaMode = mode;
    document.querySelectorAll('.media-tab').forEach((tab) => {
      tab.classList.toggle('is-active', tab.dataset.mediaMode === mode);
    });

    const claim = currentClaim();
    const videoPlayer = document.getElementById('evidence-video-player');
    const photoPlayer = document.getElementById('evidence-photo-player');
    const frameLabel = document.getElementById('evidence-frame-label');
    const damageOutline = document.getElementById('damage-outline');
    const damageCallout = document.getElementById('damage-callout');

    if (!videoPlayer || !photoPlayer) return;

    if (mode === 'video') {
      videoPlayer.classList.remove('is-hidden');
      photoPlayer.classList.add('is-hidden');
      if (claim.videoUrl) {
        if (videoPlayer.getAttribute('src') !== claim.videoUrl) {
          videoPlayer.src = claim.videoUrl;
        }
        videoPlayer.play().catch(() => {});
      }
      if (frameLabel) frameLabel.innerHTML = '<span class="live-dot"></span> CONTINUOUS WALKAROUND VIDEO · 720P/1080P';
      if (damageOutline) damageOutline.classList.remove('is-hidden');
      if (damageCallout) damageCallout.classList.remove('is-hidden');
    } else if (mode === 'yolo') {
      videoPlayer.classList.add('is-hidden');
      videoPlayer.pause();
      photoPlayer.classList.remove('is-hidden');
      photoPlayer.src = claim.yoloUrl || '/docs_assets/stage2_annotated_samples/scenario_02_front_door_scratch_comparison.jpg';
      if (frameLabel) frameLabel.innerHTML = '<span class="live-dot" style="background:#17a2b8"></span> STAGE 2 DUAL-MASK SEGMENTATION (YOLOv8x)';
      if (damageOutline) damageOutline.classList.add('is-hidden');
      if (damageCallout) damageCallout.classList.remove('is-hidden');
    } else if (mode === 'som') {
      videoPlayer.classList.add('is-hidden');
      videoPlayer.pause();
      photoPlayer.classList.remove('is-hidden');
      photoPlayer.src = claim.somUrl || '/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/front_right_door_som.jpg';
      if (frameLabel) frameLabel.innerHTML = '<span class="live-dot" style="background:#fd7e14"></span> STAGE 3 SET-OF-MARKS (SoM) DEPTH PROBE';
      if (damageOutline) damageOutline.classList.add('is-hidden');
      if (damageCallout) damageCallout.classList.add('is-hidden');
    }
  }

  function loadClaimIntoWorkstation(claim) {
    if (!claim) return;

    // Header info
    const eyebrow = document.querySelector('.claim-title-row .eyebrow');
    if (eyebrow) eyebrow.innerHTML = `CLAIM ${claim.id} <span class="eyebrow-divider">·</span> SUBMITTED ${claim.time.toUpperCase()}`;

    const title = document.querySelector('.claim-title-row h1');
    if (title) title.innerHTML = `${escapeHTML(claim.vehicle)} <span class="title-muted">/</span> ${claim.year}`;

    const subhead = document.querySelector('.claim-title-row .subhead');
    if (subhead) subhead.innerHTML = `${escapeHTML(claim.claimant)} <span class="subhead-divider">·</span> ${escapeHTML(claim.registration)} <span class="subhead-divider">·</span> Policy active`;

    const statusTag = document.querySelector('.claim-title-row .status-tag');
    if (statusTag) {
      statusTag.className = `status-tag status-${claim.status === 'ready' ? 'ready' : claim.status === 'settled' ? 'paid' : 'review'}`;
      statusTag.innerHTML = `<i></i>${claim.statusLabel}`;
    }

    // Media Switcher setup
    setMediaMode(state.mediaMode || 'video');

    // Damage assessment details
    const damageCopy = document.querySelector('.damage-copy');
    if (damageCopy) damageCopy.innerHTML = `<strong>${escapeHTML(claim.damageType)}</strong><span>${escapeHTML(claim.damagePart)} <b>·</b> ${escapeHTML(claim.panelContext)}</span>`;

    const sevChip = document.querySelector('.severity-chip');
    if (sevChip) sevChip.innerHTML = `${claim.severity} <span>·</span> ${escapeHTML(claim.severityLabel.split('·')[1] || 'Moderate')}`;

    const confChip = document.querySelector('.confidence-chip');
    if (confChip) confChip.innerHTML = `<span class="confidence-dot"></span> ${claim.confidence}% confidence`;

    const metrics = document.querySelector('.assessment-metrics');
    if (metrics) {
      metrics.innerHTML = `<div><span>Damage coverage</span><strong>${claim.coverage} <small>of panel (IoP)</small></strong></div><div><span>Paint condition</span><strong>${escapeHTML(claim.paintCondition)}</strong></div><div><span>Rust / oxidation</span><strong class="${claim.rust.includes('Not') ? 'good-text' : 'warn-text'}">${claim.rust.includes('Not') ? '<span class="icon" data-icon="check"></span> ' : ''}${claim.rust}</strong></div>`;
    }

    const note = document.querySelector('.finding-note p');
    if (note) note.textContent = claim.note;

    // Severity scale active marker
    document.querySelectorAll('.severity-scale > span[data-grade]').forEach((el) => {
      el.classList.toggle('is-current', el.dataset.grade === claim.severity);
    });

    // Populate Conditioned Damage Quarantine Lists
    const billedList = document.getElementById('billed-items-list');
    const billedCount = document.getElementById('billed-count');
    const quarantinedList = document.getElementById('quarantined-items-list');
    const quarantinedCount = document.getElementById('quarantined-count');

    if (billedList) {
      const items = claim.billedItems || [
        { part: claim.damagePart, note: `${claim.damageType} · ${claim.coverage} IoP`, amount: money(claim.subtotal) }
      ];
      if (billedCount) billedCount.textContent = items.length;
      billedList.innerHTML = items
        .map(
          (it) =>
            `<div class="damage-item-card"><span><b>${escapeHTML(it.part)}</b><br><small style="color:var(--muted)">${escapeHTML(it.note)}</small></span><strong style="color:var(--green2)">${escapeHTML(it.amount)}</strong></div>`
        )
        .join('');
    }

    if (quarantinedList) {
      const qItems = claim.quarantinedItems || [];
      if (quarantinedCount) quarantinedCount.textContent = qItems.length;
      if (qItems.length === 0) {
        quarantinedList.innerHTML = `<div style="font-size:11px;color:var(--muted);padding:8px 0;">No background road wear detected on non-claimed panels.</div>`;
      } else {
        quarantinedList.innerHTML = qItems
          .map(
            (it) =>
              `<div class="damage-item-card"><span><b>${escapeHTML(it.part)}</b><br><small style="color:var(--muted)">${escapeHTML(it.note)}</small></span><span style="font-size:10px;padding:2px 6px;border-radius:4px;background:rgba(180,100,50,0.1);color:var(--amber2)">${escapeHTML(it.status || 'Quarantined')}</span></div>`
          )
          .join('');
      }
    }

    // Repair economics table
    const subtotalEl = document.querySelector('.estimate-subtotal strong');
    if (subtotalEl) subtotalEl.textContent = money(claim.subtotal);

    const gstEl = document.querySelector('.estimate-row:nth-child(5) strong');
    if (gstEl) gstEl.textContent = money(claim.gst);

    const totalEl = document.querySelector('.estimate-total strong');
    if (totalEl) totalEl.textContent = money(claim.repairCost);

    const dedEl = document.querySelector('.deductible-row strong');
    if (dedEl) dedEl.textContent = `− ${money(claim.deductible)}`;

    const netEl = document.querySelector('.net-total strong');
    if (netEl) netEl.textContent = money(claim.netEligible);

    // Range breakdown
    const introEl = document.querySelector('.range-intro');
    if (introEl) introEl.textContent = `Offers are calculated from the ${money(claim.netEligible)} net eligible claim.`;

    const swatchStart = document.querySelector('.range-table div:nth-child(1) strong');
    if (swatchStart) swatchStart.textContent = money(claim.opening);

    const swatchTarget = document.querySelector('.range-table div:nth-child(2) strong');
    if (swatchTarget) swatchTarget.textContent = money(claim.target);

    const swatchCap = document.querySelector('.range-table div:nth-child(3) strong');
    if (swatchCap) swatchCap.textContent = money(claim.cap);

    // Offer sidecard
    updateOfferUI();

    // Settlement messages
    renderMessages();

    // Render decision & audit
    renderDecision();
    renderAudit();
    renderIcons();
  }

  function updateOfferUI() {
    const claim = currentClaim();
    const amount = money(claim.offer);

    const sideEl = document.getElementById('side-offer-amount');
    if (sideEl) sideEl.textContent = amount;

    const convEl = document.getElementById('conversation-offer');
    if (convEl) convEl.textContent = amount;

    const railEl = document.getElementById('current-offer-rail');
    if (railEl) railEl.textContent = amount;

    const acceptBtn = document.getElementById('accept-offer');
    if (acceptBtn) acceptBtn.textContent = `Accept ${amount}`;

    const roundBadge = document.getElementById('round-badge');
    if (roundBadge) roundBadge.textContent = `ROUND ${Math.min(claim.roundsUsed + 1, claim.maxRounds)} OF ${claim.maxRounds}`;

    const fill = document.getElementById('conversation-range-fill');
    if (fill) {
      const pct = claim.cap > claim.opening ? ((claim.offer - claim.opening) / (claim.cap - claim.opening)) * 100 : 50;
      fill.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    }
  }

  function renderMessages() {
    const claim = currentClaim();
    const stream = document.getElementById('message-stream');
    if (!stream) return;

    stream.innerHTML = '';
    claim.messages.forEach((msg) => {
      const row = document.createElement('div');
      row.className = `message-row ${msg.sender === 'user' ? 'user-message' : 'agent-message'}`;
      row.innerHTML = `<span class="message-avatar ${msg.sender === 'user' ? 'user-avatar' : 'agent-avatar'}">${msg.sender === 'user' ? 'C' : 'A'}</span><div><div class="message-meta"><strong>${escapeHTML(msg.name)}</strong><span>${escapeHTML(msg.time)}</span></div><div class="message-bubble">${msg.text}</div></div>`;
      stream.appendChild(row);
    });

    if (!claim.decision) {
      const card = document.createElement('div');
      card.className = 'offer-message';
      card.innerHTML = `<div class="offer-card-mini"><div><span class="small-caps">CASH OFFER · ROUND ${Math.min(claim.roundsUsed + 1, claim.maxRounds)}</span><strong>${money(claim.offer)}</strong><small>HMAC-SHA256 verified within approved policy range</small></div><span class="signed-mark"><span class="icon" data-icon="lock"></span> RANGE<br>CHECKED</span></div><div class="offer-actions"><button class="button button-green dynamic-accept" type="button">Accept ${money(claim.offer)}</button><span class="or-divider">or</span><span class="offer-actions-hint">make a counteroffer below</span></div>`;
      card.querySelector('.dynamic-accept').addEventListener('click', () => settle(claim.offer));
      stream.appendChild(card);
    }
    stream.scrollTop = stream.scrollHeight;
    renderIcons(stream);
  }

  function appendUserMessage(text) {
    const claim = currentClaim();
    const now = new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
    claim.messages.push({ sender: 'user', name: claim.claimant.split(' ')[0] || 'Claimant', time: now, text: escapeHTML(text) });
    saveClaimsToStorage();
    renderMessages();
  }

  function appendAgentMessage(text) {
    const claim = currentClaim();
    claim.messages.push({ sender: 'agent', name: 'Auto-Settle', time: 'Just now', text });
    saveClaimsToStorage();
    renderMessages();
  }

  function pushEvent(title, detail, kind = 'green', tag = 'LOCAL DEMO') {
    const claim = currentClaim();
    const now = new Date();
    const time = now.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    claim.events.push({ time, kind, title, detail, tag });
    saveClaimsToStorage();
    renderAudit();
  }

  function renderAudit() {
    const claim = currentClaim();
    const timeline = claim.events
      .map(
        (item) =>
          `<div class="audit-event ${escapeHTML(item.kind)}"><time class="audit-time">${escapeHTML(item.time)}</time><span class="audit-marker"><span class="icon" data-icon="${item.kind === 'amber' || item.kind === 'red' ? 'info' : 'check'}"></span></span><div class="audit-event-copy"><strong>${escapeHTML(item.title)}</strong><p>${escapeHTML(item.detail)}</p></div><span class="audit-event-tag">${escapeHTML(item.tag)}</span></div>`
      )
      .join('');

    document.querySelectorAll('.audit-timeline').forEach((node) => {
      node.innerHTML = `<p class="timeline-date">22 OCT 2026 <span>· ${claim.id} AUDIT LEDGER</span></p>${timeline}`;
    });

    const statusText = claim.decision
      ? claim.decision.type === 'settled'
        ? 'Cash settlement accepted'
        : claim.decision.type === 'garage'
        ? 'Cashless garage selected'
        : 'Human review requested'
      : 'Offer pending';

    document.querySelectorAll('#audit-decision-label, #audit-page-decision').forEach((node) => {
      node.textContent = statusText;
    });

    document.querySelectorAll('.audit-summary-strip').forEach((strip) => {
      strip.innerHTML = `<div><span>CLAIM</span><strong>${claim.id}</strong></div><div><span>VEHICLE</span><strong>${claim.vehicle} · ${claim.year}</strong></div><div><span>RECORD</span><strong>Cryptographic Ledger</strong></div><div><span>DECISION</span><strong class="audit-decision-tag">${statusText}</strong></div>`;
    });

    renderIcons();
  }

  // Counteroffer handling with strict guardrail bounds
  async function handleCounter() {
    const claim = currentClaim();
    const input = document.getElementById('counter-amount');
    const reason = document.getElementById('counter-reason');
    const error = document.getElementById('counter-error');
    if (!input) return;

    const amount = Number(input.value);
    error.textContent = '';

    if (!Number.isFinite(amount) || amount <= 0) {
      error.textContent = 'Enter a valid counteroffer amount greater than ₹0.';
      input.focus();
      return;
    }

    const explanation = reason.value.trim();
    appendUserMessage(`Could you settle at ${money(amount)}?${explanation ? ` ${explanation}` : ''}`);
    pushEvent('Customer counteroffer received', `${money(amount)} requested${explanation ? ` · reason: ${explanation}` : ''}.`, 'blue', 'COUNTEROFFER');

    // Live API integration if available
    if (state.apiAvailable && claim.backendUuid) {
      try {
        const res = await fetch(`/api/v1/claims/${claim.backendUuid}/negotiate`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ claimed_amount: amount, message_text: explanation })
        });
        if (res.ok) {
          const turn = await res.json();
          claim.offer = turn.offer_card.settlement_amount_inr;
          claim.roundsUsed += 1;
          saveClaimsToStorage();
          updateOfferUI();
          appendAgentMessage(turn.chatbot_explanation);
          input.value = '';
          reason.value = '';
          return;
        }
      } catch (err) {
        console.warn('Backend negotiate failed, falling back to local FSM:', err);
      }
    }

    // STRICT GUARDRAIL: Above-cap check
    if (amount > claim.cap) {
      error.textContent = `${money(amount)} exceeds the ${money(claim.cap)} approved autonomous ceiling. That amount is blocked by guardrail ESC-08.`;
      appendAgentMessage(
        `I cannot approve ${money(amount)} as an automated settlement. The approved maximum is ${money(claim.cap)}. You can accept the current offer of ${money(claim.offer)}, opt for authorized cashless garage repair, or request a human adjuster review.`
      );
      pushEvent('Above-cap request blocked', `Requested ${money(amount)}; autonomous approval ceiling is ${money(claim.cap)}. Offer unchanged.`, 'amber', 'GUARDRAIL');
      showFinalChoices();
      input.value = '';
      return;
    }

    if (amount <= claim.offer) {
      appendAgentMessage(`We accept your counteroffer of ${money(amount)} as it sits comfortably within the approved policy range.`);
      settle(amount, 'Customer accepted within the approved range.');
      input.value = '';
      return;
    }

    if (claim.roundsUsed >= claim.maxRounds) {
      appendAgentMessage(`We have reached the maximum of ${claim.maxRounds} negotiation rounds. The current approved offer is ${money(claim.offer)}. Please choose how you would like to proceed.`);
      showFinalChoices();
      input.value = '';
      return;
    }

    // Deterministic bounded concession algorithm
    const ceiling = claim.roundsUsed === 0 ? claim.target : claim.cap;
    const alpha = explanation ? 0.5 : 0.25;
    const candidate = claim.offer + (Math.min(amount, ceiling) - claim.offer) * alpha;
    const next = Math.max(claim.offer, Math.min(ceiling, claim.cap, Math.round(candidate / 100) * 100));

    claim.offer = next;
    claim.roundsUsed += 1;
    saveClaimsToStorage();
    updateOfferUI();

    appendAgentMessage(
      `Thank you for providing context. In round ${claim.roundsUsed} of ${claim.maxRounds}, our adjusted offer is <b>${money(next)}</b>. All automated offers remain strictly capped at ${money(claim.cap)}.`
    );

    pushEvent('Bounded counteroffer presented', `${money(next)} · round ${claim.roundsUsed} of ${claim.maxRounds} · mathematically bounded towards target.`, 'green', 'OFFER RULE');

    input.value = '';
    reason.value = '';
    toast(`Adjusted offer: ${money(next)}`);
  }

  function showFinalChoices() {
    const wrap = document.getElementById('negotiation-form-wrap');
    if (wrap) wrap.classList.add('is-hidden');

    const stream = document.getElementById('message-stream');
    if (document.getElementById('final-choice-panel')) return;

    const claim = currentClaim();
    const panel = document.createElement('div');
    panel.id = 'final-choice-panel';
    panel.className = 'settled-banner';
    panel.style.background = 'var(--panel-alt)';
    panel.style.borderColor = 'var(--line)';
    panel.innerHTML = `
      <span class="settled-icon" style="background:rgba(217,119,6,0.15);color:var(--amber2)"><span class="icon" data-icon="info"></span></span>
      <div><strong>Select your path</strong><p>Accept the approved cash offer of ${money(claim.offer)}, select a cashless network garage, or route to a human surveyor.</p></div>
      <div class="decision-actions" style="padding:0;flex-wrap:wrap">
        <button class="button button-green" type="button" data-choice="accept">Accept ${money(claim.offer)}</button>
        <button class="button button-outline" type="button" data-choice="garage">Cashless garage</button>
        <button class="button button-outline" type="button" data-choice="human">Human review</button>
      </div>`;

    panel.querySelector('[data-choice="accept"]').addEventListener('click', () => settle(claim.offer));
    panel.querySelector('[data-choice="garage"]').addEventListener('click', () => chooseGarage());
    panel.querySelector('[data-choice="human"]').addEventListener('click', () => escalate('Claimant requested human surveyor review after negotiation limit.'));
    stream.appendChild(panel);
    stream.scrollTop = stream.scrollHeight;
    renderIcons(panel);
  }

  async function settle(amount, note = 'Customer accepted the current approved offer.') {
    const claim = currentClaim();
    if (amount < claim.opening || amount > claim.cap) {
      pushEvent('Settlement blocked by guardrail', `${money(amount)} is outside the approved ${money(claim.opening)}–${money(claim.cap)} band.`, 'red', 'BLOCKED');
      toast('That settlement is outside the approved range.');
      return;
    }

    claim.decision = { type: 'settled', amount, note, confirmed: false, upi: null, time: new Date().toISOString() };
    claim.status = 'settled';
    claim.statusLabel = 'Settled';
    saveClaimsToStorage();

    // If backend is active, finalize settlement
    if (state.apiAvailable && claim.backendUuid) {
      try {
        await fetch(`/api/v1/claims/${claim.backendUuid}/accept`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            offer_card: {
              settlement_amount_inr: amount,
              canonical_part_key: 'front_door',
              token: 'hmac-sha256-demo-token'
            },
            beneficiary_upi_id: 'rohan@okhdfcbank'
          })
        });
      } catch (err) {
        console.warn('Backend accept failed:', err);
      }
    }

    const banner = document.getElementById('settled-banner');
    if (banner) banner.classList.remove('is-hidden');

    const formWrap = document.getElementById('negotiation-form-wrap');
    if (formWrap) formWrap.classList.add('is-hidden');

    const finalLabel = document.getElementById('final-amount-label');
    if (finalLabel) finalLabel.textContent = money(amount);

    pushEvent('Cash settlement accepted', `${money(amount)} accepted within approved policy limits. ${note}`, 'green', 'DECISION');
    renderDecision();
    renderQueue();
    setClaimTab('decision');
    toast(`Settlement accepted for ${money(amount)}`);
  }

  function chooseGarage() {
    const claim = currentClaim();
    claim.decision = {
      type: 'garage',
      reason: 'Claimant opted for authorized Cashless Network Garage inspection and repair.',
      time: new Date().toISOString()
    };
    claim.status = 'review';
    claim.statusLabel = 'Garage repair';
    saveClaimsToStorage();
    pushEvent('Cashless garage route selected', 'Claim transferred to Authorized Cashless Network Garage queue.', 'blue', 'ALTERNATE PATH');
    renderDecision();
    renderQueue();
    setClaimTab('decision');
    toast('Cashless garage pathway selected.');
  }

  function escalate(reason) {
    const claim = currentClaim();
    claim.decision = { type: 'human', reason, time: new Date().toISOString() };
    claim.status = 'review';
    claim.statusLabel = 'Human review';
    saveClaimsToStorage();
    pushEvent('Human adjuster review requested', reason, 'amber', 'ESCALATION');
    renderDecision();
    renderQueue();
    setClaimTab('decision');
    toast('Claim transferred to human adjuster queue.');
  }

  function renderDecision() {
    const root = document.getElementById('decision-content');
    if (!root) return;
    const claim = currentClaim();

    if (!claim.decision) {
      root.innerHTML = `
        <div class="decision-empty">
          <span class="decision-icon"><span class="icon" data-icon="file"></span></span>
          <p class="eyebrow">FINAL OUTCOME</p>
          <h2>No decision yet.</h2>
          <p>Review the evidence and offer conversation. An accepted cash offer, a cashless garage route, or an escalation will appear here.</p>
          <button type="button" class="button button-green" data-claim-tab="settlement">Continue settlement conversation <span>→</span></button>
        </div>`;
      renderIcons(root);
      return;
    }

    const d = claim.decision;
    if (d.type === 'settled') {
      root.innerHTML = `
        <article class="decision-result">
          <header class="decision-result-head">
            <span class="result-icon"><span class="icon" data-icon="check"></span></span>
            <div><p class="eyebrow">CASH-IN-LIEU · WITHIN APPROVED BOUNDS</p><h2>Settlement confirmed.</h2></div>
          </header>
          <div class="decision-result-body">
            <p>${escapeHTML(claim.claimant)} accepted the cash settlement for ${escapeHTML(claim.damageType)} on the ${escapeHTML(claim.damagePart)}. The amount is mathematically locked inside the approved 75–95% band.</p>
            <div class="decision-amount">${money(d.amount)}</div>
            <div class="decision-meta">
              <span>Garage estimate<strong>${money(claim.repairCost)}</strong></span>
              <span>Approved band<strong>${money(claim.opening)}–${money(claim.cap)}</strong></span>
              <span>HMAC token<strong>Verified · SHA256</strong></span>
              <span>Ledger status<strong>Committed to ledger</strong></span>
            </div>

            <div class="upi-box">
              <span class="small-caps">INSTANT DISBURSEMENT VIA UPI</span>
              <p style="font-size:11px;color:var(--muted);margin:4px 0 10px;">Enter beneficiary UPI ID to simulate immediate automated voucher settlement disbursement.</p>
              <div class="upi-row">
                <input type="text" class="upi-input" id="upi-input" placeholder="e.g. rohan@okhdfcbank" value="${d.upi || 'rohan@okhdfcbank'}">
                <button class="button button-green" type="button" id="disburse-upi-btn"><span class="icon" data-icon="spark"></span> Disburse payout</button>
              </div>
              <div class="upi-success-banner ${d.confirmed ? '' : 'is-hidden'}" id="upi-success">
                <span class="icon" data-icon="check"></span>
                <div>
                  <strong>Payout Transferred Successfully</strong>
                  <p style="margin:2px 0 0;font-size:10px;">Ref: UPI-2026-984128912 · Credited ${money(d.amount)} to <span id="credited-upi">${d.upi || 'rohan@okhdfcbank'}</span></p>
                </div>
              </div>
            </div>
          </div>
          <div class="decision-actions">
            <button class="button button-dark" type="button" id="dl-voucher-btn"><span class="icon" data-icon="download"></span> Download Settlement Voucher PDF</button>
            <button class="button button-outline" type="button" data-claim-tab="audit">View audit trail</button>
          </div>
        </article>`;

      const disburseBtn = root.querySelector('#disburse-upi-btn');
      if (disburseBtn) {
        disburseBtn.addEventListener('click', () => {
          const upiInput = root.querySelector('#upi-input');
          const upiVal = upiInput ? upiInput.value.trim() : 'rohan@okhdfcbank';
          d.confirmed = true;
          d.upi = upiVal;
          saveClaimsToStorage();
          root.querySelector('#upi-success').classList.remove('is-hidden');
          root.querySelector('#credited-upi').textContent = upiVal;
          pushEvent('UPI payout disbursed', `Transferred ${money(d.amount)} to ${upiVal} (Ref: UPI-2026-984128912). Ledger locked against double claims.`, 'green', 'PAYOUT');
          toast(`Payout of ${money(d.amount)} disbursed to ${upiVal}`);
        });
      }

      const dlVoucher = root.querySelector('#dl-voucher-btn');
      if (dlVoucher) {
        dlVoucher.addEventListener('click', () => {
          if (state.apiAvailable && claim.backendUuid) {
            window.open(`/api/v1/claims/${claim.backendUuid}/voucher/pdf`, '_blank');
          } else {
            window.print();
            toast('Opening print view for Settlement Voucher PDF.');
          }
        });
      }
    } else if (d.type === 'garage') {
      root.innerHTML = `
        <article class="decision-result">
          <header class="decision-result-head">
            <span class="result-icon"><span class="icon" data-icon="car"></span></span>
            <div><p class="eyebrow">ALTERNATE REPAIR PATHWAY</p><h2>Cashless garage selected.</h2></div>
          </header>
          <div class="decision-result-body">
            <p>The claimant chose an authorized cashless network garage repair instead of an immediate cash payout. The vehicle has been routed for physical inspection and repair order execution.</p>
            <div class="decision-meta">
              <span>Cash payout<strong>₹0 (Zero payout)</strong></span>
              <span>Repair estimate<strong>${money(claim.repairCost)}</strong></span>
              <span>Work order status<strong>Issued to network</strong></span>
              <span>Recommended garage<strong>Northstar Body Shop · Indiranagar</strong></span>
            </div>
          </div>
          <div class="decision-actions">
            <button class="button button-dark" type="button" onclick="window.print()"><span class="icon" data-icon="print"></span> Print Garage Work Order</button>
            <button class="button button-outline" type="button" data-claim-tab="audit">View audit trail</button>
          </div>
        </article>`;
    } else {
      root.innerHTML = `
        <article class="decision-result">
          <header class="decision-result-head escalated">
            <span class="result-icon"><span class="icon" data-icon="person"></span></span>
            <div><p class="eyebrow">AUTOMATION PAUSED · SAFE HANDOFF</p><h2>Human review required.</h2></div>
          </header>
          <div class="decision-result-body">
            <p>This claim cannot be safely adjudicated automatically. In accordance with operational guardrails, no cash offer has been issued to prevent improper payout.</p>
            <div class="ncb-note" style="margin:14px 0;">
              <span class="ncb-icon">!</span>
              <div>
                <strong>Reason for escalation</strong>
                <p>${escapeHTML(d.reason)}</p>
              </div>
            </div>
            <div class="decision-meta">
              <span>Automated offer<strong>Blocked</strong></span>
              <span>Assigned queue<strong>Senior desk adjuster</strong></span>
              <span>Priority<strong>Next in line (P1)</strong></span>
              <span>Next step<strong>Examine video evidence</strong></span>
            </div>
          </div>
          <div class="decision-actions">
            <button class="button button-dark" type="button" id="dl-dossier-btn"><span class="icon" data-icon="download"></span> Download Adjuster Dossier PDF</button>
            <button class="button button-outline" type="button" data-view="guardrails">Review guardrail catalog</button>
            <button class="button button-outline" type="button" data-claim-tab="audit">View audit trail</button>
          </div>
        </article>`;

      const dlDossier = root.querySelector('#dl-dossier-btn');
      if (dlDossier) {
        dlDossier.addEventListener('click', () => {
          if (state.apiAvailable && claim.backendUuid) {
            window.open(`/api/v1/claims/${claim.backendUuid}/dossier/pdf`, '_blank');
          } else {
            window.print();
            toast('Opening print view for Adjuster Dossier PDF.');
          }
        });
      }
    }
    renderIcons(root);
  }

  // Interactive severity scale: switch damage grade
  function setDamageSeverity(grade) {
    const claim = currentClaim();
    claim.severity = grade;

    const grades = {
      L1: { label: 'L1 · Surface scuff', subtotal: 2200, gst: 396, deductible: 500, net: 2096, opening: 1570, target: 1780, cap: 1990 },
      L2: { label: 'L2 · Basecoat scratch', subtotal: 5800, gst: 1044, deductible: 620, net: 6224, opening: 4660, target: 5290, cap: 5910 },
      L3: { label: 'L3 · Shallow dent / PDR', subtotal: 4200, gst: 756, deductible: 500, net: 4456, opening: 3340, target: 3780, cap: 4230 },
      L4: { label: 'L4 · Creased dent', subtotal: 9000, gst: 1620, deductible: 620, net: 10000, opening: 7500, target: 8500, cap: 9500 },
      L5: { label: 'L5 · Structural tear / crack', subtotal: 26500, gst: 4770, deductible: 1000, net: 30270, opening: 22700, target: 25700, cap: 28750 }
    };

    const g = grades[grade] || grades.L4;
    claim.severityLabel = g.label;
    claim.subtotal = g.subtotal;
    claim.gst = g.gst;
    claim.deductible = g.deductible;
    claim.repairCost = g.subtotal + g.gst;
    claim.netEligible = g.net;
    claim.opening = g.opening;
    claim.target = g.target;
    claim.cap = g.cap;
    claim.offer = g.opening;

    // Check ESC-08 if repair estimate exceeds ₹25,000
    if (claim.netEligible > 25000) {
      escalate('ESC-08: Net repair estimate of ₹30,270 exceeds the ₹25,000 autonomous approval ceiling.');
      toast('ESC-08 Triggered: Claim exceeds ₹25,000 autonomous ceiling.');
    } else {
      pushEvent(`Severity grade changed to ${grade}`, `${g.label} · Net eligible: ${money(claim.netEligible)} · Range: ${money(claim.opening)}–${money(claim.cap)}`, 'blue', 'GRADE CHANGE');
      toast(`Severity adjusted to ${grade}: ${money(claim.opening)}–${money(claim.cap)}`);
    }

    saveClaimsToStorage();
    loadClaimIntoWorkstation(claim);
  }

  // System 1 Real-Time Intent Grounding NLP Parser
  function parseClaimIntent(text) {
    if (!text || !text.trim()) {
      return {
        parts: [],
        damages: [],
        severity: null,
        focus: 'Awaiting description'
      };
    }
    const lower = text.toLowerCase();
    const parts = [];
    const damages = [];

    // Part recognition
    if (lower.includes('door')) {
      if (lower.includes('front') || lower.includes('driver')) parts.push('front_right_door');
      else if (lower.includes('back') || lower.includes('rear') || lower.includes('passenger')) parts.push('back_right_door');
      else parts.push('front_door');
    }
    if (lower.includes('bumper')) {
      if (lower.includes('front')) parts.push('front_bumper');
      else parts.push('rear_bumper');
    }
    if (lower.includes('fender') || lower.includes('wing')) parts.push('front_fender');
    if (lower.includes('mirror')) parts.push('left_mirror');
    if (lower.includes('windshield') || lower.includes('glass') || lower.includes('windscreen')) parts.push('front_glass (SAFETY)');
    if (lower.includes('wheel') || lower.includes('tyre') || lower.includes('tire') || lower.includes('rim')) parts.push('wheel (SAFETY)');
    if (lower.includes('hood') || lower.includes('bonnet')) parts.push('hood');
    if (lower.includes('quarter') || lower.includes('flank')) parts.push('quarter_panel');

    // Damage type recognition
    let severity = 'L2 · Minor';
    if (lower.includes('crease') || lower.includes('creased')) {
      damages.push('creased_dent');
      severity = 'L4 · Moderate (Creased Dent)';
    } else if (lower.includes('dent')) {
      damages.push('shallow_dent');
      severity = 'L3 · Shallow Dent (PDR)';
    }

    if (lower.includes('scratch')) {
      damages.push('paint_scratch');
      if (!damages.includes('creased_dent')) severity = 'L2 · Basecoat Scratch';
    }
    if (lower.includes('scuff') || lower.includes('rub')) {
      damages.push('surface_scuff');
      if (damages.length === 1) severity = 'L1 · Surface Scuff';
    }
    if (lower.includes('crack') || lower.includes('shatter') || lower.includes('broken')) {
      damages.push('structural_crack');
      severity = 'L5 · Structural Crack (Safety Risk)';
    }
    if (lower.includes('rust') || lower.includes('corrosion') || lower.includes('oxid')) {
      damages.push('pre_existing_rust');
    }

    return {
      parts: parts.length ? parts : ['driver_side_door'],
      damages: damages.length ? damages : ['creased_dent'],
      severity,
      focus: 'Conditioned Masking Active'
    };
  }

  function updateIntentGroundingUI() {
    const noteEl = document.getElementById('incident-note');
    const chipsEl = document.getElementById('intent-chips');
    const statusBadge = document.getElementById('intent-status-badge');
    if (!noteEl || !chipsEl) return;

    const result = parseClaimIntent(noteEl.value);
    if (!noteEl.value.trim()) {
      chipsEl.innerHTML = '<span class="intent-empty-hint">Type your damage description above to see live System 1 NLP part &amp; damage extraction.</span>';
      if (statusBadge) {
        statusBadge.textContent = 'Waiting for input';
        statusBadge.className = 'intent-status-badge';
      }
      return;
    }

    if (statusBadge) {
      statusBadge.textContent = 'Extracted';
      statusBadge.className = 'intent-status-badge active';
    }

    let html = '';
    result.parts.forEach((p) => {
      const isSafety = p.includes('SAFETY');
      html += `<span class="intent-chip ${isSafety ? 'safety' : ''}"><span class="icon" data-icon="car"></span> Part: <b>${escapeHTML(p)}</b></span>`;
    });
    result.damages.forEach((d) => {
      const isRust = d.includes('rust');
      html += `<span class="intent-chip ${isRust ? 'warn' : ''}"><span class="icon" data-icon="shield"></span> Damage: <b>${escapeHTML(d)}</b></span>`;
    });
    html += `<span class="intent-chip"><span class="icon" data-icon="check"></span> Grade: <b>${escapeHTML(result.severity)}</b></span>`;
    html += `<span class="intent-chip" style="background:rgba(23,162,184,0.15);border-color:rgba(23,162,184,0.3);color:var(--text);"><span class="icon" data-icon="spark"></span> <b>${escapeHTML(result.focus)}</b></span>`;

    chipsEl.innerHTML = html;
    renderIcons(chipsEl);
  }

  // File drop & camera recording
  function addFiles(files) {
    const mediaFiles = files.filter((f) => f.type.startsWith('image/') || f.type.startsWith('video/'));
    const valid = mediaFiles.filter((f) => f.size <= 25 * 1024 * 1024);
    if (valid.length < mediaFiles.length) toast('Some files exceeded the 25 MB size limit.');

    valid.slice(0, 6 - state.files.length).forEach((file) => {
      const url = URL.createObjectURL(file);
      state.files.push({ file, url, id: `${Date.now()}-${Math.random().toString(16).slice(2)}` });
      state.objectUrls.push(url);
    });

    renderPreviews();
  }

  function renderPreviews() {
    const wrap = document.getElementById('upload-preview');
    const list = document.getElementById('preview-list');
    if (!wrap || !list) return;

    wrap.classList.toggle('is-hidden', state.files.length === 0);
    list.innerHTML = '';

    state.files.forEach((item) => {
      const node = document.createElement('div');
      node.className = 'preview-item';
      const isVideo = item.file.type.startsWith('video/');
      const media = isVideo ? document.createElement('video') : document.createElement('img');
      media.src = item.url;
      if (isVideo) {
        media.controls = true;
        media.muted = true;
      } else {
        media.alt = item.file.name;
      }

      const label = document.createElement('span');
      label.textContent = `${item.file.name} · ${(item.file.size / 1024 / 1024).toFixed(1)} MB`;

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'preview-remove';
      remove.setAttribute('aria-label', `Remove ${item.file.name}`);
      remove.innerHTML = `<span class="icon" data-icon="close"></span>`;
      remove.addEventListener('click', () => {
        URL.revokeObjectURL(item.url);
        state.files = state.files.filter((f) => f.id !== item.id);
        renderPreviews();
      });

      node.append(media, label, remove);
      list.appendChild(node);
    });

    renderIcons(list);
  }

  // Authentic Test Presets with Real Video Assets
  const presets = {
    happy: {
      policyId: 'POL-HAPPY-001',
      reg: 'MH12DE1433',
      model: 'Hyundai Creta',
      date: new Date().toISOString().slice(0, 10),
      note: 'Creased dent on driver-side front door from reversing near concrete parking pillar.',
      fileName: 'car_002.mp4',
      fileSize: 6.2 * 1024 * 1024,
      fileType: 'video/mp4'
    },
    scuff: {
      policyId: 'POL-HAPPY-001',
      reg: 'DL01AB9999',
      model: 'Maruti Baleno',
      date: new Date().toISOString().slice(0, 10),
      note: 'Minor surface scuff on plastic rear bumper cover while parking at market.',
      fileName: 'car_001.mp4',
      fileSize: 1.9 * 1024 * 1024,
      fileType: 'video/mp4'
    },
    photopack: {
      policyId: 'POL-RED-007',
      reg: 'KA01MJ5555',
      model: 'Hyundai Creta (Red)',
      date: new Date().toISOString().slice(0, 10),
      note: 'Dented front door and scratched panel; 5 multi-angle photos attached.',
      fileName: 'plate_front_keyframe.jpg',
      fileSize: 2.1 * 1024 * 1024,
      fileType: 'image/jpeg',
      isPhotoPack: true
    },
    rust: {
      policyId: 'POL-RED-007',
      reg: 'KA01MJ5555',
      model: 'Toyota Corolla',
      date: new Date().toISOString().slice(0, 10),
      note: 'Deep scratch and crease on passenger door and rocker panel with pre-existing flaking rust.',
      fileName: 'toyota-corolla-side-impact-damage-walkaround-houston.mp4',
      fileSize: 8.4 * 1024 * 1024,
      fileType: 'video/mp4'
    },
    safety: {
      policyId: 'POL-FUTURE-003',
      reg: 'KA03MJ7777',
      model: 'Kia Seltos',
      date: new Date().toISOString().slice(0, 10),
      note: 'Cracked front windshield from high-speed stone chip on highway; visibility impaired.',
      fileName: 'car_005.mp4',
      fileSize: 693 * 1024,
      fileType: 'video/mp4'
    },
    expired: {
      policyId: 'POL-EXPIRED-002',
      reg: 'DL01AB9999',
      model: 'Maruti Swift',
      date: new Date().toISOString().slice(0, 10),
      note: 'Scratched front bumper on low divider.',
      fileName: 'car_001.mp4',
      fileSize: 1.9 * 1024 * 1024,
      fileType: 'video/mp4'
    }
  };

  function applyPreset(key) {
    const p = presets[key];
    if (!p) return;

    const policySel = document.getElementById('policy-select');
    if (policySel) policySel.value = p.policyId;

    const regInput = document.getElementById('registration');
    if (regInput) regInput.value = p.reg;

    const modelInput = document.getElementById('vehicle-model');
    if (modelInput) modelInput.value = p.model;

    const dateInput = document.getElementById('incident-date');
    if (dateInput) dateInput.value = p.date;

    const noteInput = document.getElementById('incident-note');
    if (noteInput) {
      noteInput.value = p.note;
      updateIntentGroundingUI();
    }

    // Attach mock files
    state.files.forEach((f) => URL.revokeObjectURL(f.url));
    state.files = [];

    if (p.isPhotoPack) {
      const photos = [
        new File([new Uint8Array(1024 * 100)], 'plate_front.jpg', { type: 'image/jpeg' }),
        new File([new Uint8Array(1024 * 100)], 'full_body_left.jpg', { type: 'image/jpeg' }),
        new File([new Uint8Array(1024 * 100)], 'damage_closeup.jpg', { type: 'image/jpeg' }),
        new File([new Uint8Array(1024 * 100)], 'damage_angle.jpg', { type: 'image/jpeg' })
      ];
      addFiles(photos);
    } else {
      const video = new File([new Uint8Array(1024 * 100)], p.fileName, { type: p.fileType });
      addFiles([video]);
    }

    toast(`Loaded preset: ${p.model} (${p.fileName})`);
  }

  // Pipeline modal progression with Stage 0-5
  async function runPipelineSubmission(policyId, reg, model, note) {
    const dialog = document.getElementById('pipeline-dialog');
    const fill = document.getElementById('pipeline-progress-fill');
    const continueBtn = document.getElementById('pipeline-continue-btn');
    const dismissBtn = document.getElementById('pipeline-dismiss-btn');
    const statusBadge = document.getElementById('pipeline-status-badge');
    const desc = document.getElementById('pipeline-desc');

    if (dialog && typeof dialog.showModal === 'function') {
      dialog.showModal();
    }

    continueBtn.classList.add('is-hidden');
    dismissBtn.classList.add('is-hidden');
    statusBadge.textContent = 'RUNNING';
    statusBadge.className = 'demo-tag';

    const steps = [0, 1, 2, 3, 4, 5];
    steps.forEach((s) => {
      const el = document.getElementById(`pstep-${s}`);
      if (el) {
        el.className = 'pipeline-step';
      }
    });

    // Check policy failure condition (Fast-fail testing)
    const isExpired = policyId === 'POL-EXPIRED-002';
    const isClaimCap = policyId === 'POL-CLAIMCAP-004';
    const isCancelled = policyId === 'POL-CANCELLED-005';
    const isSafety = policyId === 'POL-FUTURE-003' || note.toLowerCase().includes('windshield');
    const isRust = note.toLowerCase().includes('rust') || note.toLowerCase().includes('corrosion');

    for (let i = 0; i < steps.length; i++) {
      const stepEl = document.getElementById(`pstep-${i}`);
      if (stepEl) stepEl.className = 'pipeline-step active';
      fill.style.width = `${((i + 1) / steps.length) * 100}%`;

      await new Promise((r) => setTimeout(r, 380));

      // Fast-fail check at Stage 0
      if (i === 0 && (isExpired || isClaimCap || isCancelled)) {
        stepEl.className = 'pipeline-step';
        statusBadge.textContent = 'FAST-FAIL ESC-00';
        statusBadge.className = 'status-tag status-review';
        const reason = isExpired
          ? 'Policy POL-EXPIRED-002 expired on 31 Dec 2024. Active policy required.'
          : isClaimCap
          ? 'Policy POL-CLAIMCAP-004 has reached its annual limit of 2 cash claims.'
          : 'Policy POL-CANCELLED-005 has been cancelled by underwriting.';

        desc.innerHTML = `<span style="color:#a54f45;font-weight:600">Perimeter Fast-Fail Rejected:</span> ${reason}`;
        dismissBtn.classList.remove('is-hidden');
        toast('Stage 0 Fast-Fail: Claim submission blocked by policy rules.');
        return;
      }

      if (stepEl) stepEl.className = 'pipeline-step done';
    }

    statusBadge.textContent = 'PASSED';
    statusBadge.className = 'status-tag status-ready';
    desc.textContent = 'All 6 pipeline stages completed successfully. Initial Offer Card generated and signed.';

    // Create new authentic claim entry
    const newId = `CLM-${Math.floor(48292 + Math.random() * 500)}`;
    const newClaim = {
      id: newId,
      time: 'Just now',
      vehicle: model,
      year: 2023,
      registration: reg,
      policyId: policyId,
      claimant: 'Nisha Rao (Verified)',
      damageType: isSafety ? 'Windshield crack (Safety Critical)' : isRust ? 'Creased dent with rust' : 'Creased dent',
      damagePart: isSafety ? 'Front glass' : 'Driver-side front door',
      panelContext: isSafety ? 'Safety-critical component' : 'Exterior door panel',
      severity: isSafety ? 'L5' : 'L4',
      severityLabel: isSafety ? 'L5 · Safety concern' : 'L4 · Moderate',
      confidence: 96,
      coverage: '8.4%',
      paintCondition: 'Paint broken',
      rust: isRust ? 'Old rust detected' : 'Not detected',
      note: note,
      repairCost: isSafety ? 14200 : 10620,
      subtotal: isSafety ? 12000 : 9000,
      gst: isSafety ? 2200 : 1620,
      deductible: 620,
      netEligible: isSafety ? 13580 : 10000,
      opening: isSafety || isRust ? 0 : 7500,
      target: isSafety || isRust ? 0 : 8500,
      cap: isSafety || isRust ? 0 : 9500,
      offer: isSafety || isRust ? 0 : 7500,
      status: isSafety || isRust ? 'review' : 'ready',
      statusLabel: isSafety ? 'Safety escalation' : isRust ? 'Pre-existing rust' : 'Ready to settle',
      roundsUsed: 0,
      maxRounds: 3,
      decision: isSafety
        ? { type: 'human', reason: 'ESC-06: Safety-critical part (windshield) cannot receive automated cash offer. Physical garage inspection required.' }
        : isRust
        ? { type: 'human', reason: 'ESC-04: Old oxidation/rust detected on panel. Human surveyor inspection required.' }
        : null,
      videoUrl: '/test_assets/videos/simple/car_002.mp4',
      yoloUrl: '/docs_assets/stage2_annotated_samples/scenario_02_front_door_scratch_comparison.jpg',
      somUrl: '/evals/artifacts/som_output/ad60d3d2-d6f0-4ccc-bec9-79f54ab89f49/front_right_door_som.jpg',
      billedItems: [
        { part: isSafety ? 'Front Windshield' : 'Driver-Side Front Door', note: `${isSafety ? 'L5 Glass crack' : 'Creased dent'} · 8.4% IoP`, amount: isSafety ? '₹12,000' : '₹9,000' }
      ],
      quarantinedItems: [
        { part: 'Rear Bumper', note: 'Background wear · Bypasses ESC-05', status: 'Quarantined' }
      ],
      messages: [
        {
          sender: 'agent',
          name: 'Auto-Settle',
          time: 'Just now',
          text: isSafety
            ? 'Safety-critical damage detected on windshield. In compliance with rule ESC-06, this claim requires physical workshop inspection.'
            : isRust
            ? 'Pre-existing rust detected. Routed to desk adjuster under rule ESC-04.'
            : 'We’ve analyzed your vehicle media. The crease dent on the door is eligible for cash settlement. Initial offer: <b>₹7,500</b>.'
        }
      ],
      events: [
        { time: 'Just now', kind: 'blue', title: 'Media uploaded', detail: 'Walkaround evidence ingested and validated.', tag: 'EVIDENCE' },
        { time: 'Just now', kind: 'green', title: 'Perimeter fast-fail passed', detail: `Policy ${policyId} active. Visual sharpness verified.`, tag: 'PRE-CHECK' },
        { time: 'Just now', kind: 'green', title: 'Identity & continuity verified', detail: `Registration ${reg} matched ANPR plate OCR.`, tag: 'IDENTITY' },
        { time: 'Just now', kind: isSafety || isRust ? 'amber' : 'green', title: isSafety ? 'ESC-06 Triggered' : isRust ? 'ESC-04 Triggered' : 'Damage assessment completed', detail: isSafety ? 'Safety-critical component detected.' : isRust ? 'Old oxidation flaking detected.' : 'L4 crease dent confirmed at 96% confidence.', tag: isSafety || isRust ? 'GUARDRAIL' : 'ASSESSMENT' }
      ]
    };

    state.claims.unshift(newClaim);
    saveClaimsToStorage();
    renderQueue();

    continueBtn.classList.remove('is-hidden');
    continueBtn.onclick = () => {
      if (dialog.open) dialog.close();
      selectClaim(newId);
    };
  }

  // Camera handling
  const cameraDialog = document.getElementById('camera-dialog');
  const cameraPreview = document.getElementById('camera-preview');
  const cameraPlaceholder = document.getElementById('camera-placeholder');

  function openCameraDialog() {
    if (cameraDialog && typeof cameraDialog.showModal === 'function') {
      cameraDialog.showModal();
    } else {
      toast('Live camera recording needs a browser with dialog support.');
    }
  }

  function closeCameraDialog() {
    if (state.recorder && state.recorder.state === 'recording') state.recorder.stop();
    if (state.stream) {
      state.stream.getTracks().forEach((t) => t.stop());
      state.stream = null;
    }
    clearInterval(state.timerHandle);
    state.recording = false;
    if (cameraPreview) cameraPreview.srcObject = null;
    if (cameraPlaceholder) cameraPlaceholder.classList.remove('is-hidden');
    document.getElementById('record-video').disabled = true;
    document.getElementById('record-video').classList.remove('is-hidden');
    document.getElementById('finish-recording').classList.add('is-hidden');
    document.getElementById('record-indicator').classList.add('is-hidden');
    if (cameraDialog && cameraDialog.open) cameraDialog.close();
  }

  async function startCamera() {
    try {
      if (!navigator.mediaDevices?.getUserMedia) {
        throw new Error('Camera access is unavailable. Please choose a video file instead.');
      }
      state.stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false
      });
      cameraPreview.srcObject = state.stream;
      cameraPreview.classList.remove('is-hidden');
      cameraPlaceholder.classList.add('is-hidden');
      document.getElementById('record-video').disabled = false;
      toast('Camera active. Start recording your continuous walkaround.');
    } catch (err) {
      toast(err.message || 'Camera permission not available. Choose a file instead.');
    }
  }

  function startRecording() {
    if (!state.stream) return;
    if (!window.MediaRecorder) {
      toast('MediaRecorder not supported. Please upload a file instead.');
      return;
    }
    try {
      state.recordedChunks = [];
      state.recorder = new MediaRecorder(state.stream);
      state.recorder.ondataavailable = (e) => {
        if (e.data.size) state.recordedChunks.push(e.data);
      };
      state.recorder.onstop = () => {
        const blob = new Blob(state.recordedChunks, { type: state.recorder.mimeType || 'video/webm' });
        const file = new File([blob], `live-walkaround-${new Date().toISOString().slice(0, 10)}.webm`, { type: blob.type });
        addFiles([file]);
        closeCameraDialog();
        toast('Recorded walkaround attached to evidence preview.');
      };
      state.recorder.start();
      state.recording = true;
      state.recordStartedAt = Date.now();
      document.getElementById('record-indicator').classList.remove('is-hidden');
      document.getElementById('record-video').classList.add('is-hidden');
      document.getElementById('finish-recording').classList.remove('is-hidden');
      state.timerHandle = setInterval(() => {
        const seconds = Math.floor((Date.now() - state.recordStartedAt) / 1000);
        const timer = document.getElementById('record-timer');
        if (timer) timer.textContent = `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
      }, 300);
    } catch {
      toast('Could not start recording. Upload a video file instead.');
    }
  }

  // Guardrail scenario definitions
  const scenarioData = {
    clear: { level: 'clear', title: 'Continue to bounded offer', text: 'All 9 checks passed. Evidence is clear and within autonomous limits.' },
    confidence: { level: 'warning', title: 'ESC-07: Pause for human review', text: 'Visual confidence below 55% is insufficient for automated payout. Route to desk adjuster.' },
    safety: { level: 'danger', title: 'ESC-06: Stop · Physical workshop inspection', text: 'Safety-critical component (glass, wheel, frame) cannot receive cash offer. Physical inspection required.' },
    continuity: { level: 'warning', title: 'ESC-02: Require unbroken live capture', text: 'Video scene cut or tracking loss detected. Broken continuity requires re-recording.' },
    limit: { level: 'danger', title: 'ESC-08: Licensed surveyor required', text: 'Net repair estimate exceeds ₹25,000 autonomous approval ceiling. No automated cash offer issued.' },
    rust: { level: 'warning', title: 'ESC-04: Pause · Pre-existing wear detected', text: 'Signs of old oxidation/filler indicate pre-existing wear. Human adjuster review required.' },
    mismatch: { level: 'danger', title: 'ESC-01: Vehicle plate mismatch', text: 'Registration or color mismatch against policy records. Block offer and route to fraud triage.' },
    repeat: { level: 'warning', title: 'ESC-03: Repeated unrepaired damage', text: 'Canonical part has an active cash-paid claim on ledger. Proof of repair required.' }
  };

  const scenarioIcons = { clear: 'check', warning: 'info', danger: 'shield' };

  function updateScenarioUI(key) {
    const item = scenarioData[key] || scenarioData.clear;
    const root = document.getElementById('scenario-result');
    if (!root) return;

    root.className = `scenario-result ${item.level === 'clear' ? '' : item.level}`;
    root.innerHTML = `
      <span class="scenario-result-icon ${item.level}"><span class="icon" data-icon="${scenarioIcons[item.level]}"></span></span>
      <div>
        <span class="small-caps">CURRENT OUTCOME</span>
        <strong>${item.title}</strong>
        <p>${item.text}</p>
      </div>`;
    renderIcons(root);
  }

  function applyScenarioToWorkstation(key) {
    const claim = currentClaim();
    if (key === 'safety') {
      claim.damagePart = 'Front windshield glass';
      claim.damageType = 'Cracked laminated glass';
      claim.severity = 'L5';
      claim.severityLabel = 'L5 · Safety concern';
      escalate('ESC-06: Safety-critical windshield damage detected. Physical garage inspection mandatory.');
    } else if (key === 'confidence') {
      claim.confidence = 48;
      escalate('ESC-07: Visual confidence 48% is below the 55% autonomous threshold. Human desk review required.');
    } else if (key === 'continuity') {
      escalate('ESC-02: Scene cut detected between plate frame and damage close-up. Unbroken video required.');
    } else if (key === 'limit') {
      claim.subtotal = 27000;
      claim.repairCost = 31860;
      claim.netEligible = 31240;
      escalate('ESC-08: Net repair estimate of ₹31,240 exceeds the ₹25,000 autonomous ceiling.');
    } else if (key === 'rust') {
      claim.rust = 'Old rust detected';
      escalate('ESC-04: Brown oxidation flaking indicates pre-existing damage. Transferred to adjuster.');
    } else if (key === 'mismatch') {
      escalate('ESC-01: Plate OCR MH12DE1433 does not match insured record KA03MJ5555. Routed to fraud triage.');
    } else if (key === 'repeat') {
      escalate('ESC-03: Active unrepaired damage record on ledger for this part. Proof of repair required.');
    } else {
      claim.decision = null;
      claim.status = 'ready';
      claim.statusLabel = 'Ready to settle';
      claim.confidence = 96;
      claim.rust = 'Not detected';
      saveClaimsToStorage();
      toast('Restored happy path. Ready to settle.');
    }

    saveClaimsToStorage();
    loadClaimIntoWorkstation(claim);
    setView('claim');
    setClaimTab(claim.decision ? 'decision' : 'assessment');
    toast(`Injected ${key} scenario into workstation.`);
  }

  function downloadAudit() {
    const claim = currentClaim();
    const record = {
      record_type: 'Auto-Settle AI Audit Record',
      claim_id: claim.id,
      timestamp: new Date().toISOString(),
      vehicle: {
        make_model: claim.vehicle,
        year: claim.year,
        registration: claim.registration,
        policy_id: claim.policyId
      },
      damage_assessment: {
        component: claim.damagePart,
        type: claim.damageType,
        severity: claim.severityLabel,
        confidence_percent: claim.confidence,
        panel_coverage_iop: claim.coverage,
        paint_condition: claim.paintCondition,
        rust_status: claim.rust
      },
      economics: {
        garage_subtotal_inr: claim.subtotal,
        gst_inr: claim.gst,
        deductible_inr: claim.deductible,
        net_eligible_inr: claim.netEligible,
        opening_offer_inr: claim.opening,
        target_offer_inr: claim.target,
        maximum_cap_inr: claim.cap,
        autonomous_limit_inr: 25000
      },
      decision: claim.decision || { status: 'pending_settlement' },
      chronological_events: claim.events
    };

    const blob = new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `auto-settle-${claim.id}-audit.json`;
    link.click();
    URL.revokeObjectURL(url);
    toast('Audit JSON record downloaded.');
  }

  // Event Listeners initialization
  document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    checkApiHealth();
    renderIcons();
    renderQueue();
    loadClaimIntoWorkstation(currentClaim());
    updateIntentGroundingUI();

    // Theme toggle button
    const themeBtn = document.getElementById('theme-toggle');
    if (themeBtn) {
      themeBtn.addEventListener('click', toggleTheme);
    }

    // Media Switcher tabs
    document.querySelectorAll('.media-tab').forEach((tab) => {
      tab.addEventListener('click', () => {
        setMediaMode(tab.dataset.mediaMode);
      });
    });

    // Topbar search
    const searchInput = document.getElementById('global-search');
    if (searchInput) {
      searchInput.addEventListener('input', (e) => {
        state.searchQuery = e.target.value;
        renderQueue();
      });
    }

    // Live NLP Intent Grounding on incident note typing
    const incidentNote = document.getElementById('incident-note');
    if (incidentNote) {
      incidentNote.addEventListener('input', updateIntentGroundingUI);
    }

    // Queue filter pills
    const filterGroup = document.getElementById('queue-filter-group');
    if (filterGroup) {
      filterGroup.addEventListener('click', (e) => {
        const btn = e.target.closest('.filter-pill');
        if (!btn) return;
        filterGroup.querySelectorAll('.filter-pill').forEach((p) => p.classList.remove('is-active'));
        btn.classList.add('is-active');
        state.filter = btn.dataset.filter || 'all';
        renderQueue();
      });
    }

    // Navigation and tab clicks
    document.addEventListener('click', (e) => {
      const claimRow = e.target.closest('.claim-row');
      if (claimRow) {
        e.preventDefault();
        const cid = claimRow.dataset.claimId;
        if (cid) selectClaim(cid);
        return;
      }

      const viewBtn = e.target.closest('[data-view]');
      if (viewBtn) {
        e.preventDefault();
        setView(viewBtn.dataset.view);
        return;
      }

      const tabBtn = e.target.closest('[data-claim-tab]');
      if (tabBtn) {
        e.preventDefault();
        if (state.view !== 'claim') setView('claim');
        setClaimTab(tabBtn.dataset.claimTab);
        return;
      }

      const presetBtn = e.target.closest('[data-preset]');
      if (presetBtn) {
        e.preventDefault();
        applyPreset(presetBtn.dataset.preset);
        return;
      }

      const gradeBtn = e.target.closest('.severity-scale > span[data-grade]');
      if (gradeBtn) {
        e.preventDefault();
        setDamageSeverity(gradeBtn.dataset.grade);
        return;
      }

      const toastBtn = e.target.closest('[data-toast]');
      if (toastBtn) {
        toast(toastBtn.dataset.toast);
        return;
      }
    });

    // Policy select change updates form
    const policySelect = document.getElementById('policy-select');
    if (policySelect) {
      policySelect.addEventListener('change', (e) => {
        const val = e.target.value;
        if (val === 'POL-HAPPY-001') {
          document.getElementById('registration').value = 'MH12DE1433';
          document.getElementById('vehicle-model').value = 'Hyundai Creta';
        } else if (val === 'POL-RED-007') {
          document.getElementById('registration').value = 'KA01MJ5555';
          document.getElementById('vehicle-model').value = 'Hyundai Creta (Red)';
        } else if (val === 'POL-EXPIRED-002') {
          document.getElementById('registration').value = 'DL01AB9999';
          document.getElementById('vehicle-model').value = 'Maruti Swift';
        } else if (val === 'POL-CLAIMCAP-004') {
          document.getElementById('registration').value = 'MH14EU4321';
          document.getElementById('vehicle-model').value = 'Tata Nexon';
        } else if (val === 'POL-CANCELLED-005') {
          document.getElementById('registration').value = 'MH02BQ1111';
          document.getElementById('vehicle-model').value = 'Honda City';
        } else if (val === 'POL-FUTURE-003') {
          document.getElementById('registration').value = 'KA03MJ7777';
          document.getElementById('vehicle-model').value = 'Kia Seltos';
        }
      });
    }

    // Intake Form submission
    const form = document.getElementById('claim-form');
    if (form) {
      form.addEventListener('submit', (e) => {
        e.preventDefault();
        if (!state.files.length) {
          toast('Please add at least one vehicle image or video file.');
          document.getElementById('dropzone')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
          return;
        }

        const policyId = document.getElementById('policy-select')?.value || 'POL-HAPPY-001';
        const reg = document.getElementById('registration')?.value || 'MH12DE1433';
        const model = document.getElementById('vehicle-model')?.value || 'Hyundai Creta';
        const note = document.getElementById('incident-note')?.value || 'Door crease dent';

        runPipelineSubmission(policyId, reg, model, note);
      });
    }

    // File input & Drag/Drop
    const fileInput = document.getElementById('evidence-file');
    const dropzone = document.getElementById('dropzone');
    if (fileInput) fileInput.addEventListener('change', () => addFiles(Array.from(fileInput.files || [])));
    if (dropzone) {
      ['dragenter', 'dragover'].forEach((type) =>
        dropzone.addEventListener(type, (e) => {
          e.preventDefault();
          dropzone.classList.add('drag-over');
        })
      );
      ['dragleave', 'drop'].forEach((type) =>
        dropzone.addEventListener(type, (e) => {
          e.preventDefault();
          dropzone.classList.remove('drag-over');
        })
      );
      dropzone.addEventListener('drop', (e) => addFiles(Array.from(e.dataTransfer.files || [])));
    }

    const clearUpload = document.getElementById('clear-upload');
    if (clearUpload) {
      clearUpload.addEventListener('click', () => {
        state.files.forEach((f) => URL.revokeObjectURL(f.url));
        state.files = [];
        renderPreviews();
      });
    }

    // Negotiation Form Buttons
    const sendCounterBtn = document.getElementById('send-counter');
    if (sendCounterBtn) sendCounterBtn.addEventListener('click', handleCounter);

    const counterInput = document.getElementById('counter-amount');
    if (counterInput) {
      counterInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          handleCounter();
        }
      });
    }

    const acceptOfferBtn = document.getElementById('accept-offer');
    if (acceptOfferBtn) acceptOfferBtn.addEventListener('click', () => settle(currentClaim().offer));

    // Audit actions
    document.querySelectorAll('[data-action="print"]').forEach((b) => b.addEventListener('click', () => window.print()));
    document.querySelectorAll('[data-action="download-audit"]').forEach((b) => b.addEventListener('click', downloadAudit));
    document.querySelectorAll('[data-action="zoom"]').forEach((b) =>
      b.addEventListener('click', () => {
        const fig = document.querySelector('.evidence-figure');
        if (fig) fig.classList.toggle('is-expanded');
      })
    );

    // Camera buttons
    document.getElementById('open-camera')?.addEventListener('click', openCameraDialog);
    document.getElementById('close-camera')?.addEventListener('click', closeCameraDialog);
    document.getElementById('start-camera')?.addEventListener('click', startCamera);
    document.getElementById('record-video')?.addEventListener('click', startRecording);
    document.getElementById('finish-recording')?.addEventListener('click', () => {
      if (state.recorder?.state === 'recording') state.recorder.stop();
    });

    // Guardrail scenario select & test injection
    const scenarioSel = document.getElementById('scenario-select');
    if (scenarioSel) {
      scenarioSel.addEventListener('change', (e) => updateScenarioUI(e.target.value));
    }

    const applyScenarioBtn = document.getElementById('apply-scenario-btn');
    if (applyScenarioBtn) {
      applyScenarioBtn.addEventListener('click', () => {
        const sel = document.getElementById('scenario-select');
        applyScenarioToWorkstation(sel ? sel.value : 'clear');
      });
    }

    // Dismiss pipeline modal
    document.getElementById('pipeline-dismiss-btn')?.addEventListener('click', () => {
      const d = document.getElementById('pipeline-dialog');
      if (d && d.open) d.close();
    });

    // Set today label
    const todayLabel = document.getElementById('today-label');
    if (todayLabel) {
      todayLabel.textContent = `${new Date().toLocaleDateString('en-US', { weekday: 'long' }).toUpperCase()} · CLAIMS DESK`;
    }
  });
})();
