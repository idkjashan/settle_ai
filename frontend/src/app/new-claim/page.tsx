"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useClaims } from "@/lib/store";
import { useToast } from "@/components/providers";
import { Icon } from "@/components/icons";
import { PipelineDialog } from "@/components/pipeline-dialog";
import { POLICY_OPTIONS } from "@/lib/rules";
import { shortId } from "@/lib/format";
import type { FastFailResponse } from "@/lib/types";

interface MediaFile {
  file: File;
  previewUrl: string;
  isVideo: boolean;
}

interface PresetContext {
  loadUrls: (urls: string[], isVideo: boolean) => Promise<void>;
  setPolicy: (id: string) => void;
  setNote: (note: string) => void;
}

const PRESETS: { key: string; label: string; run: (ctx: PresetContext) => Promise<void> }[] = [
  {
    key: "corolla",
    label: "Toyota Corolla · Dual-Door Side Impact (Real Houston Video)",
    run: async (ctx) => {
      ctx.setPolicy("POL-TOYOTA-008");
      ctx.setNote("Severe impact dent and crease across driver-side front door and rear left door from side collision.");
      await ctx.loadUrls(["/test_assets/videos/simple/toyota-corolla-side-impact-damage-walkaround-houston.mp4"], true);
    },
  },
  {
    key: "happy",
    label: "Creta White · Door Crease (Benchmark Video)",
    run: async (ctx) => {
      ctx.setPolicy("POL-HAPPY-001");
      ctx.setNote("Creased dent on driver-side front door");
      await ctx.loadUrls(["/test_assets/videos/simple/happy_creta_white_h264.mp4"], true);
    },
  },
  {
    key: "scuff",
    label: "car_001 · Rear Bumper Scuff (Real Video)",
    run: async (ctx) => {
      ctx.setPolicy("POL-HAPPY-001");
      ctx.setNote("Light surface scuff on the rear bumper from a low-speed parking touch.");
      await ctx.loadUrls(["/test_assets/videos/simple/car_001.mp4"], true);
    },
  },
  {
    key: "photopack",
    label: "Photo Pack (5 Multi-Angle Photos)",
    run: async (ctx) => {
      ctx.setPolicy("POL-HAPPY-001");
      ctx.setNote("Creased dent on driver-side front door, photographed from five angles.");
      await ctx.loadUrls(
        [
          "/test_assets/images/keyframes_for_stage2/real_toyota_hilux_white_ute/keyframe_01.jpg",
          "/test_assets/images/keyframes_for_stage2/real_toyota_hilux_white_ute/keyframe_02.jpg",
          "/test_assets/images/keyframes_for_stage2/real_toyota_hilux_white_ute/keyframe_03.jpg",
          "/test_assets/images/keyframes_for_stage2/real_toyota_hilux_white_ute/keyframe_04.jpg",
          "/test_assets/images/keyframes_for_stage2/real_toyota_hilux_white_ute/damage_closeup_primary.jpg",
        ],
        false,
      );
    },
  },
  {
    key: "safety",
    label: "ESC-06 · Windshield Crack (Safety Escalation)",
    run: async (ctx) => {
      ctx.setPolicy("POL-HAPPY-001");
      ctx.setNote("Crack across the front windshield after a stone hit on the highway.");
      await ctx.loadUrls(["/test_assets/videos/simple/car_005.mp4"], true);
    },
  },
  {
    key: "expired",
    label: "ESC-00 · Expired Policy (Fast-Fail)",
    run: async (ctx) => {
      ctx.setPolicy("POL-EXPIRED-002");
      ctx.setNote("Dent on the front left fender from a shopping trolley.");
      await ctx.loadUrls(["/test_assets/videos/simple/car_002.mp4"], true);
    },
  },
];

export default function NewClaimPage() {
  const router = useRouter();
  const showToast = useToast();
  const { addClaim, apiOnline } = useClaims();

  const [media, setMedia] = useState<MediaFile[]>([]);
  const [policyId, setPolicyId] = useState("POL-HAPPY-001");
  const [registration, setRegistration] = useState("MH12DE1433");
  const [vehicleModel, setVehicleModel] = useState("Hyundai Creta");
  const [isCustomVehicle, setIsCustomVehicle] = useState(false);
  const [vehicleMake, setVehicleMake] = useState("Toyota");
  const [vehicleYear, setVehicleYear] = useState(2022);
  const [registeredColor, setRegisteredColor] = useState("SILVER");
  const [incidentDate, setIncidentDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [incidentLocation, setIncidentLocation] = useState("Bengaluru");
  const [note, setNote] = useState("Creased dent on driver-side front door from reversing near concrete parking pillar.");
  const [dragOver, setDragOver] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [skipStage0, setSkipStage0] = useState(false);
  const [skipStage1, setSkipStage1] = useState(false);
  const [failure, setFailure] = useState<FastFailResponse | null>(null);
  const [pipelineClaimId, setPipelineClaimId] = useState<string | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const presetCtx: PresetContext = useMemo(
    () => ({
      loadUrls: async (urls, isVideo) => {
        try {
          const loaded: MediaFile[] = [];
          for (const url of urls) {
            const res = await fetch(url);
            if (!res.ok) throw new Error(`${res.status}`);
            const blob = await res.blob();
            const name = url.split("/").pop() ?? "evidence";
            const type = isVideo ? "video/mp4" : blob.type || "image/jpeg";
            loaded.push({ file: new File([blob], name, { type }), previewUrl: URL.createObjectURL(blob), isVideo });
          }
          setMedia((prev) => [...prev, ...loaded]);
          showToast(`Loaded ${loaded.length} benchmark evidence file${loaded.length > 1 ? "s" : ""}.`);
        } catch {
          showToast("Could not load benchmark asset — is the backend running?");
        }
      },
      setPolicy: (id) => setPolicyId(id),
      setNote: (n) => setNote(n),
    }),
    [showToast],
  );

  const addFiles = useCallback((files: FileList | File[]) => {
    const list = Array.from(files);
    if (!list.length) return;
    setMedia((prev) => [
      ...prev,
      ...list.map((file) => ({
        file,
        previewUrl: URL.createObjectURL(file),
        isVideo: file.type.startsWith("video/"),
      })),
    ]);
  }, []);

  const clearMedia = () => {
    media.forEach((m) => URL.revokeObjectURL(m.previewUrl));
    setMedia([]);
  };

  const removeMedia = (idx: number) => {
    URL.revokeObjectURL(media[idx].previewUrl);
    setMedia((prev) => prev.filter((_, i) => i !== idx));
  };

  const intent = useMemo(() => extractIntent(note), [note]);

  const modality: "VIDEO_WALKAROUND" | "PHOTO_PACK" = media.some((m) => m.isVideo) ? "VIDEO_WALKAROUND" : media.length ? "PHOTO_PACK" : "VIDEO_WALKAROUND";

  const resetVehicleFromPolicy = (id: string) => {
    setPolicyId(id);
    const policy = POLICY_OPTIONS.find((p) => p.id === id);
    if (policy) {
      const regMatch = policy.label.match(/\(([A-Z0-9]{8,12})\)/);
      const modelMatch = policy.label.match(/· ([A-Za-z]+ [A-Za-z]+) \(/);
      if (regMatch) setRegistration(regMatch[1]);
      if (modelMatch) setVehicleModel(modelMatch[1]);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting) return;
    if (!media.length) {
      showToast("Add a walkaround video or photo pack first.");
      return;
    }
    setSubmitting(true);
    setFailure(null);

    try {
      const form = new FormData();
      form.append("policy_id", policyId);
      form.append("capture_source", "FILE_UPLOAD");
      form.append("capture_modality", modality);
      form.append("is_demo_rehearsal", "true");
      form.append("claim_description", note);
      if (skipStage0) form.append("skip_stage_0", "true");
      if (skipStage1) form.append("skip_stage_1", "true");
      if (isCustomVehicle) {
        form.append("vehicle_make", vehicleMake);
        form.append("vehicle_model", vehicleModel);
        form.append("registration_number", registration);
        form.append("manufacturing_year", String(vehicleYear));
        form.append("registered_color", registeredColor);
      }
      if (modality === "PHOTO_PACK") {
        media.filter((m) => !m.isVideo).forEach((m) => form.append("photo_files", m.file, m.file.name));
      } else {
        const video = media.find((m) => m.isVideo);
        if (video) form.append("video_file", video.file, video.file.name);
      }

      const res = await api.uploadClaim(form);
      const uuid = res.claim_id;
      addClaim({
        id: uuid,
        label: shortId(uuid),
        policyId,
        vehicle: vehicleModel,
        registration,
        modality,
        note,
        mediaName: media[0]?.file.name ?? "",
        createdAt: new Date().toISOString(),
        localVideoUrl: media.find((m) => m.isVideo)?.previewUrl,
      });

      if (res.passed) {
        setPipelineClaimId(uuid);
        showToast(`Claim ${shortId(uuid)} accepted — pipeline running.`);
      } else {
        setFailure(res);
        showToast(`Fast-fail gate stopped the claim (${res.escalation_code ?? "ESC-00"}).`);
      }
    } catch (err) {
      showToast(err instanceof Error ? `Upload failed: ${err.message}` : "Upload failed — is the backend running?");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <>
      <div className="backline">
        <button className="back-button" type="button" onClick={() => router.push("/")}>
          ← <span>Overview</span>
        </button>
        <span className="backline-sep">/</span>
        <span>New claim</span>
        <span className="demo-tag">{apiOnline == null ? "CONNECTING…" : apiOnline ? "LIVE PIPELINE" : "OFFLINE"}</span>
      </div>

      <div className="page-heading">
        <div>
          <p className="eyebrow">NEW MOTOR CLAIM · SUBMIT TO AUTONOMOUS ADJUSTER</p>
          <h1>
            Start with the evidence<span className="period">.</span>
          </h1>
          <p className="subhead">An unbroken walkaround video or 3–6 photo pack connects damage to the insured vehicle.</p>
        </div>
      </div>

      <div className="preset-bar">
        <span className="preset-label">
          <Icon name="spark" /> <strong>Benchmark &amp; Test Presets:</strong>
        </span>
        {PRESETS.map((p) => (
          <button key={p.key} type="button" className="preset-btn" onClick={() => void p.run(presetCtx)}>
            {p.label}
          </button>
        ))}
      </div>

      {failure && (
        <div className="failure-banner" role="alert">
          <div className="failure-banner-head">
            <Icon name="shield" size={18} />
            <strong>{failure.remediation?.user_title ?? "Fast-fail gate stopped this claim"}</strong>
            <span className="failure-code">{failure.escalation_code ?? "ESC-00"}</span>
          </div>
          <p>{failure.remediation?.user_message ?? "The evidence did not pass the automated pre-checks."}</p>
          {failure.remediation?.action_items?.length ? (
            <ul>
              {failure.remediation.action_items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : null}
        </div>
      )}

      <form className="intake-layout" onSubmit={handleSubmit}>
        <div className="intake-main">
          <section className="panel upload-panel">
            <div className="panel-topline">
              <div>
                <h2>Upload vehicle media</h2>
                <p>1 unbroken video (5–60s) OR 3–6 photo pack</p>
              </div>
              <span className="required-label">REQUIRED</span>
            </div>
            <label
              className={`dropzone ${dragOver ? "is-dragover" : ""}`}
              onDragOver={(e) => {
                e.preventDefault();
                setDragOver(true);
              }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragOver(false);
                addFiles(e.dataTransfer.files);
              }}
            >
              <input ref={inputRef} type="file" accept="image/*,video/*" multiple style={{ display: "none" }} onChange={(e) => e.target.files && addFiles(e.target.files)} />
              <span className="upload-illustration">
                <Icon name="upload" />
              </span>
              <strong>
                Drop evidence here, or{" "}
                <u
                  onClick={(e) => {
                    e.preventDefault();
                    inputRef.current?.click();
                  }}
                >
                  browse files
                </u>
              </strong>
              <span>MP4 video (5–60s) or 3–6 JPG/PNG photos · Max 20 MB each</span>
              <span className="upload-footnote">
                <Icon name="shield" /> Auto-detects video walkaround vs photo pack modality.
              </span>
            </label>
            <div className="capture-guidance">
              <div className="guidance-icon">
                <Icon name="video" />
              </div>
              <div>
                <strong>Continuous walkaround guidance</strong>
                <p>Start at number plate, show full vehicle, then hold on damage. Film in daylight without scene cuts.</p>
                <div className="guidance-tags">
                  <span>720p minimum</span>
                  <span>5–60 seconds</span>
                  <span>Continuous tracking</span>
                </div>
              </div>
              <button className="button button-outline" type="button" onClick={() => inputRef.current?.click()}>
                <Icon name="camera" /> Browse files
              </button>
            </div>
            {media.length > 0 && (
              <div className="upload-preview">
                <div className="preview-top">
                  <span className="small-caps">SELECTED EVIDENCE · {media.length}</span>
                  <button type="button" className="quiet-link" onClick={clearMedia}>
                    Remove all
                  </button>
                </div>
                <div className="preview-list">
                  {media.map((m, idx) => (
                    <figure className="preview-tile" key={m.previewUrl} style={{ margin: 0 }}>
                      {m.isVideo ? <video src={m.previewUrl} muted playsInline /> : <img src={m.previewUrl} alt={m.file.name} />}
                      <figcaption>{m.file.name}</figcaption>
                      <button type="button" className="remove-btn" aria-label={`Remove ${m.file.name}`} onClick={() => removeMedia(idx)}>
                        ×
                      </button>
                    </figure>
                  ))}
                </div>
              </div>
            )}
          </section>

          <section className="panel claim-context-panel">
            <div className="panel-topline">
              <div>
                <h2>Claim context</h2>
                <p>Policy details &amp; incident narrative</p>
              </div>
              <span className="optional-label">POLICY DATA</span>
            </div>
            <div className="form-grid">
              <div className="field-full" style={{ display: "flex", gap: 10, marginBottom: 8 }}>
                <button
                  type="button"
                  style={{
                    padding: "7px 14px",
                    fontSize: "var(--font-xs)",
                    borderRadius: "var(--radius-sm)",
                    border: !isCustomVehicle ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: !isCustomVehicle ? "var(--accent-glow)" : "var(--surface2)",
                    color: !isCustomVehicle ? "var(--accent)" : "var(--muted)",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                  onClick={() => setIsCustomVehicle(false)}
                >
                  Select Existing Policy
                </button>
                <button
                  type="button"
                  style={{
                    padding: "7px 14px",
                    fontSize: "var(--font-xs)",
                    borderRadius: "var(--radius-sm)",
                    border: isCustomVehicle ? "1px solid var(--accent)" : "1px solid var(--border)",
                    background: isCustomVehicle ? "var(--accent-glow)" : "var(--surface2)",
                    color: isCustomVehicle ? "var(--accent)" : "var(--muted)",
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                  onClick={() => {
                    setIsCustomVehicle(true);
                    setPolicyId("POL-CUSTOM-001");
                    setVehicleMake("Toyota");
                    setVehicleModel("Corolla");
                    setRegistration("TX-COROLLA-22");
                  }}
                >
                  Custom / Enter My Own Vehicle
                </button>
              </div>

              {!isCustomVehicle ? (
                <label className="field-label field-full">
                  Insured policy record <span>*</span>
                  <select value={policyId} onChange={(e) => resetVehicleFromPolicy(e.target.value)} required>
                    {POLICY_OPTIONS.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : (
                <>
                  <label className="field-label">
                    Custom Policy ID <span>*</span>
                    <input
                      value={policyId}
                      onChange={(e) => setPolicyId(e.target.value.toUpperCase())}
                      placeholder="e.g. POL-MYCAR-101"
                      required
                    />
                    <small>Auto-provisioned into database upon upload.</small>
                  </label>
                  <label className="field-label">
                    Vehicle Make <span>*</span>
                    <input
                      value={vehicleMake}
                      onChange={(e) => {
                        setVehicleMake(e.target.value);
                        setVehicleModel(`${e.target.value} ${vehicleModel.split(" ")[1] ?? "Sedan"}`);
                      }}
                      placeholder="e.g. Toyota, Honda, Hyundai"
                      required
                    />
                  </label>
                  <label className="field-label">
                    Vehicle Model <span>*</span>
                    <input
                      value={vehicleModel}
                      onChange={(e) => setVehicleModel(e.target.value)}
                      placeholder="e.g. Corolla, Civic, Creta"
                      required
                    />
                  </label>
                  <label className="field-label">
                    Manufacturing Year <span>*</span>
                    <input
                      type="number"
                      value={vehicleYear}
                      onChange={(e) => setVehicleYear(parseInt(e.target.value) || 2022)}
                      min={2000}
                      max={2026}
                      required
                    />
                  </label>
                  <label className="field-label">
                    Registered Vehicle Color <span>*</span>
                    <select value={registeredColor} onChange={(e) => setRegisteredColor(e.target.value)}>
                      <option value="SILVER">Silver / Grey</option>
                      <option value="WHITE">White</option>
                      <option value="RED">Red</option>
                      <option value="BLACK">Black</option>
                      <option value="BLUE">Blue</option>
                    </select>
                  </label>
                </>
              )}

              <label className="field-label">
                Registration number <span>*</span>
                <input value={registration} onChange={(e) => setRegistration(e.target.value)} required autoComplete="off" />
                <small>Matched against ANPR plate OCR extraction.</small>
              </label>
              {!isCustomVehicle && (
                <label className="field-label">
                  Vehicle make &amp; model <span>*</span>
                  <input value={vehicleModel} onChange={(e) => setVehicleModel(e.target.value)} required />
                </label>
              )}
              <label className="field-label">
                Incident date <span>*</span>
                <input type="date" value={incidentDate} onChange={(e) => setIncidentDate(e.target.value)} required />
              </label>
              <label className="field-label">
                Incident location <span>OPTIONAL</span>
                <input value={incidentLocation} onChange={(e) => setIncidentLocation(e.target.value)} />
              </label>
              <label className="field-label field-full">
                What happened? (Claim Intent Grounding) <span>*</span>
                <textarea rows={3} value={note} onChange={(e) => setNote(e.target.value)} required maxLength={1000} />
                <small>
                  System 1 Intent Grounding extracts claimed parts &amp; damage types in real-time to condition YOLO segmentation &amp;
                  quarantine background road wear.
                </small>
              </label>
              <div className="intent-grounding-box field-full">
                <div className="intent-grounding-head">
                  <Icon name="spark" />
                  <strong>Live Intent Grounding (NLP Extraction)</strong>
                  <span className="intent-status-badge">{intent.parts.length || intent.damages.length ? "Extracted" : "Waiting"}</span>
                </div>
                <div className="intent-chips">
                  {intent.parts.map((p) => (
                    <span className="intent-chip" key={p}>
                      <Icon name="car" /> Part: <b>{p}</b>
                    </span>
                  ))}
                  {intent.damages.map((d) => (
                    <span className="intent-chip" key={d}>
                      <Icon name="shield" /> Damage: <b>{d}</b>
                    </span>
                  ))}
                  <span className="intent-chip">
                    <Icon name="check" /> Focus: <b>Conditioned Masking</b>
                  </span>
                </div>
              </div>
            </div>
          </section>

          <section className="panel model-testing-panel" style={{ marginTop: 18 }}>
            <div className="panel-topline">
              <div>
                <h2>Model Testing Controls</h2>
                <p>Bypass low-level perimeter &amp; continuity gates to directly test YOLO &amp; local VLM models</p>
              </div>
              <span className="optional-label" style={{ color: "var(--accent)" }}>DEV OPTIONS</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 14 }}>
              <label style={{ display: "flex", alignItems: "flex-start", gap: 12, cursor: "pointer", fontSize: "var(--font-sm)", background: "var(--surface2)", padding: "12px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <input
                  type="checkbox"
                  checked={skipStage0}
                  onChange={(e) => setSkipStage0(e.target.checked)}
                  style={{ marginTop: 3, accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <div>
                  <strong style={{ color: "var(--text)" }}>Skip Stage 0: Fast-Fail Perimeter Checks</strong>
                  <p style={{ margin: "3px 0 0", color: "var(--muted)", fontSize: "var(--font-xs)", lineHeight: 1.4 }}>
                    Bypasses container format, duration, bitrate, resolution, and annual claim cap constraints.
                  </p>
                </div>
              </label>

              <label style={{ display: "flex", alignItems: "flex-start", gap: 12, cursor: "pointer", fontSize: "var(--font-sm)", background: "var(--surface2)", padding: "12px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <input
                  type="checkbox"
                  checked={skipStage1}
                  onChange={(e) => setSkipStage1(e.target.checked)}
                  style={{ marginTop: 3, accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <div>
                  <strong style={{ color: "var(--text)" }}>Skip Stage 1: Identity &amp; Video Continuity Checks (Bypass Scene Cuts &amp; Plate OCR)</strong>
                  <p style={{ margin: "3px 0 0", color: "var(--muted)", fontSize: "var(--font-xs)", lineHeight: 1.4 }}>
                    Stops scene cuts (ESC-02) and plate OCR / color mismatches from halting the pipeline. Automatically extracts video keyframes and feeds them directly into Stage 2 YOLO segmentation and Stage 3 local VLM (Ollama minicpm-v:8b).
                  </p>
                </div>
              </label>
            </div>
          </section>
        </div>

        <aside className="intake-aside">
          <section className="panel intake-checklist">
            <p className="eyebrow">BEFORE YOU SEND</p>
            <h3 style={{ fontFamily: "var(--serif)", fontWeight: 500, margin: "0 0 14px" }}>Three things to capture</h3>
            <ol>
              <li>
                <span>01</span>
                <div>
                  <strong>Start at the number plate</strong>
                  <p>Keep the insured vehicle in view throughout.</p>
                </div>
              </li>
              <li>
                <span>02</span>
                <div>
                  <strong>Show the whole vehicle</strong>
                  <p>Move around it slowly, without cutting the clip.</p>
                </div>
              </li>
              <li>
                <span>03</span>
                <div>
                  <strong>Move closer to the damage</strong>
                  <p>Hold still for a clear close-up in daylight.</p>
                </div>
              </li>
            </ol>
            <div className="checklist-callout">
              <Icon name="info" />
              <p>Dark, blurry, edited, or very short clips will be caught by Stage 0 Fast-Fail perimeter checks.</p>
            </div>
          </section>

          <section className="panel model-testing-panel" style={{ marginTop: 18 }}>
            <div className="panel-topline">
              <div>
                <h2>Model Testing Controls</h2>
                <p>Bypass low-level perimeter &amp; continuity gates to directly test YOLO &amp; local VLM models</p>
              </div>
              <span className="optional-label" style={{ color: "var(--accent)" }}>DEV OPTIONS</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 14, marginTop: 14 }}>
              <label style={{ display: "flex", alignItems: "flex-start", gap: 12, cursor: "pointer", fontSize: "var(--font-sm)", background: "var(--surface2)", padding: "12px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <input
                  type="checkbox"
                  checked={skipStage0}
                  onChange={(e) => setSkipStage0(e.target.checked)}
                  style={{ marginTop: 3, accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <div>
                  <strong style={{ color: "var(--text)" }}>Skip Stage 0: Fast-Fail Perimeter Checks</strong>
                  <p style={{ margin: "3px 0 0", color: "var(--muted)", fontSize: "var(--font-xs)", lineHeight: 1.4 }}>
                    Bypasses container format, duration, bitrate, resolution, and annual claim cap constraints.
                  </p>
                </div>
              </label>

              <label style={{ display: "flex", alignItems: "flex-start", gap: 12, cursor: "pointer", fontSize: "var(--font-sm)", background: "var(--surface2)", padding: "12px 14px", borderRadius: "var(--radius-sm)", border: "1px solid var(--border)" }}>
                <input
                  type="checkbox"
                  checked={skipStage1}
                  onChange={(e) => setSkipStage1(e.target.checked)}
                  style={{ marginTop: 3, accentColor: "var(--accent)", width: 16, height: 16 }}
                />
                <div>
                  <strong style={{ color: "var(--text)" }}>Skip Stage 1: Identity &amp; Video Continuity Checks (Bypass Scene Cuts &amp; Plate OCR)</strong>
                  <p style={{ margin: "3px 0 0", color: "var(--muted)", fontSize: "var(--font-xs)", lineHeight: 1.4 }}>
                    Stops scene cuts (ESC-02) and plate OCR / color mismatches from halting the pipeline. Automatically extracts video keyframes and feeds them directly into Stage 2 YOLO segmentation and Stage 3 local VLM (Ollama minicpm-v:8b).
                  </p>
                </div>
              </label>
            </div>
          </section>
          <div className="privacy-note">
            <Icon name="lock" />
            <span>
              <strong>Fraud-immune architecture</strong>
              <small>SHA-256 dedupe, ByteTrack continuity, and OEM pricing.</small>
            </span>
          </div>
        </aside>

        <div className="intake-submit-bar">
          <span>
            <span className="live-dot" /> Ready to submit to the autonomous claims adjuster
          </span>
          <button className="button button-dark" type="submit" disabled={submitting || !media.length}>
            {submitting ? "Uploading…" : "Submit claim & run pipeline"} <span>→</span>
          </button>
        </div>
      </form>

      {pipelineClaimId && (
        <PipelineModal claimId={pipelineClaimId} onClose={() => setPipelineClaimId(null)} onOpenClaim={() => router.push(`/claims/${pipelineClaimId}`)} />
      )}
    </>
  );
}

function PipelineModal({ claimId, onClose, onOpenClaim }: { claimId: string; onClose: () => void; onOpenClaim: () => void }) {
  const [open, setOpen] = useState(true);
  return (
    <div className="modal-backdrop" style={{ display: open ? "flex" : "none" }} onClick={onClose} role="presentation">
      <div onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" style={{ display: "contents" }}>
        <PipelineDialog
          open={open}
          claimId={claimId}
          onClose={() => setOpen(false)}
          onContinue={() => {
            setOpen(false);
            onOpenClaim();
          }}
        />
      </div>
    </div>
  );
}

// ---- Lightweight client-side intent extraction (mirrors backend claim_intent vocabulary) ----

const PART_KEYWORDS: [RegExp, string][] = [
  [/\bfront[- ]?left door\b|\bdriver[- ]side (?:front )?door\b/i, "front_left_door"],
  [/\bfront[- ]?right door\b|\bpassenger[- ]side (?:front )?door\b/i, "front_right_door"],
  [/\brear[- ]left door\b/i, "rear_left_door"],
  [/\brear[- ]right door\b/i, "rear_right_door"],
  [/\bfront bumper\b/i, "front_bumper"],
  [/\brear bumper\b/i, "rear_bumper"],
  [/\bbonnet\b|\bhood\b/i, "bonnet"],
  [/\bboot\b|\btrunk\b|\btailgate\b/i, "boot_door"],
  [/\bwindshield\b|\bwindscreen\b/i, "front_windshield"],
  [/\b(?:front|left|right)? ?(?:head\s?light|headlamp)s?\b/i, "headlight"],
  [/\b(?:tail|rear) ?lights?\b/i, "tail_light"],
  [/\bfender\b|\bwing\b/i, "fender"],
  [/\broof\b/i, "roof"],
  [/\bmirror\b/i, "side_mirror"],
  [/\bgrille\b/i, "grille"],
];

const DAMAGE_KEYWORDS: [RegExp, string][] = [
  [/\bcreased? dent\b/i, "creased_dent"],
  [/\bdent(s|ed)?\b/i, "dent"],
  [/\bscratch(es|ed)?\b/i, "scratch"],
  [/\bscuff(s|ed)?\b/i, "scuff"],
  [/\bcrack(ed)?\b/i, "crack"],
  [/\brust\b|\boxid(ation|ized)?\b/i, "rust"],
  [/\bpebble(s)? (damage|dents?)\b|\bstone (chip|peck)s?\b/i, "stone_peck"],
  [/\bpaint (peel|chip)/i, "paint_peel"],
];

function extractIntent(note: string): { parts: string[]; damages: string[] } {
  const parts = PART_KEYWORDS.filter(([re]) => re.test(note)).map(([, k]) => k);
  const damages = DAMAGE_KEYWORDS.filter(([re]) => re.test(note)).map(([, k]) => k);
  return { parts: [...new Set(parts)].slice(0, 4), damages: [...new Set(damages)].slice(0, 4) };
}
