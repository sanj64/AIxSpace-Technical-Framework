"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";

type LiveUpdate = {
  schema_version: string;
  session_id: string;
  sequence: number;
  emitted_at: string;
  stream_health: {
    state: string;
    source: string;
    speed: number;
    scenario: string;
    reference_update: string;
  };
  sample: {
    sequence: number;
    timestamp: string;
    source: string;
    mission_phase: string;
    channel_order: string[];
    channel_values: Record<string, number | null>;
  };
  risk_packet: {
    packet_id: string;
    event_id: string;
    timestamp: string;
    subsystem: string;
    detector_identity: string;
    artifact_hash: string;
    config_hash: string;
    feature_schema_hash: string;
    score: number | null;
    threshold: number | null;
    margin: number | null;
    anomaly: boolean;
    data_quality_flags: string[];
    system_mode: "NORMAL" | "DEGRADED";
  };
  explanation: {
    explanation_id: string;
    detector_evidence: Record<string, unknown>;
    risk_factor_decomposition: Record<string, unknown>;
    deterministic_policy_trace: Record<string, unknown>;
    feasible_counterfactual: Record<string, unknown>;
    limitations: string[];
    explanation_implementation_version: string;
  };
  recommendation: {
    recommendation_id: string;
    action: "NOMINAL" | "COOLDOWN" | "SAFE_MODE" | "ALERT_ONLY";
    disposition: string;
    rule_set_version: string;
    rule_ids: string[];
  };
  audit_entry_hash: string;
};

type Snapshot = {
  session_id: string;
  service_state: string;
  latest: LiveUpdate | null;
  history: LiveUpdate[];
  available_scenarios: string[];
  allowed_speeds: number[];
};

const channelLabels: Record<string, { label: string; unit: string }> = {
  battery_temperature_c: { label: "Battery temperature", unit: "°C" },
  bus_voltage_v: { label: "Bus voltage", unit: "V" },
  payload_current_a: { label: "Payload current", unit: "A" },
};

const scenarioLabels: Record<string, string> = {
  normal: "Normal operation",
  thermal_rise: "Thermal rise",
  voltage_sag: "Voltage sag",
  payload_spike: "Payload-current spike",
  missing_channel: "Missing channel",
  stale_stream: "Stale telemetry",
};

function number(value: unknown, digits = 2): string {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(digits) : "—";
}

const REPLAY_SOURCE = "esa_adb_mission1_replay";

function humanize(channel: string): string {
  return channel.replaceAll("_", " ");
}

function channelDisplay(channel: string): { label: string; unit: string } {
  return channelLabels[channel] ?? { label: humanize(channel), unit: "" };
}

function SparkBars({ updates, channel }: { updates: LiveUpdate[]; channel: string }) {
  const values = updates.slice(-120).map((item) => item.sample.channel_values[channel]);
  const finite = values.filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const low = finite.length ? Math.min(...finite) : 0;
  const high = finite.length ? Math.max(...finite) : 1;
  const span = Math.max(high - low, Math.abs(high) * 0.08, 0.01);
  return (
    <div className="live-chart" role="img" aria-label={`${channelDisplay(channel).label} live trend`}>
      {values.map((value, index) => {
        const update = updates.slice(-120)[index];
        const height = typeof value === "number" ? 18 + ((value - low) / span) * 76 : 6;
        const alert = update?.risk_packet.anomaly && update.risk_packet.subsystem !== "UNRESOLVED";
        return <i key={`${update?.sequence ?? index}-${channel}`} className={alert ? "alert" : ""} style={{ height: `${Math.max(5, Math.min(96, height))}%` }} />;
      })}
      {!values.length && <span>Waiting for telemetry…</span>}
    </div>
  );
}

export default function LiveMonitor() {
  const [updates, setUpdates] = useState<LiveUpdate[]>([]);
  const [latest, setLatest] = useState<LiveUpdate | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [csrf, setCsrf] = useState("");
  const [lastReceived, setLastReceived] = useState(0);
  const [now, setNow] = useState(0);
  const [connected, setConnected] = useState(false);
  const [controlError, setControlError] = useState("");
  const [streamSource, setStreamSource] = useState("");
  const [scenario, setScenario] = useState("thermal_rise");
  const [soundEnabled, setSoundEnabled] = useState(false);
  const priorAnomaly = useRef(false);

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(timer);
  }, []);

  const beep = useCallback(() => {
    if (!soundEnabled) return;
    const AudioContextClass = window.AudioContext ?? (window as typeof window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AudioContextClass) return;
    const context = new AudioContextClass();
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = 720;
    gain.gain.setValueAtTime(0.08, context.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + 0.22);
    oscillator.connect(gain).connect(context.destination);
    oscillator.start();
    oscillator.stop(context.currentTime + 0.22);
    oscillator.onended = () => void context.close();
  }, [soundEnabled]);

  useEffect(() => {
    let source: EventSource | null = null;
    let cancelled = false;
    Promise.all([
      fetch("/api/v1/live/snapshot", { cache: "no-store" }).then((response) => {
        if (!response.ok) throw new Error("Live engine is not available");
        return response.json() as Promise<Snapshot>;
      }),
      fetch("/api/v1/live/control-token", { cache: "no-store" }).then((response) => response.json() as Promise<{ token: string }>),
    ])
      .then(([snapshot, token]) => {
        if (cancelled) return;
        setSessionId(snapshot.session_id);
        setCsrf(token.token);
        setUpdates(snapshot.history.slice(-900));
        setLatest(snapshot.latest);
        setStreamSource(snapshot.latest?.stream_health.source ?? "");
        setLastReceived(Date.now());
        source = new EventSource("/api/v1/live/events");
        source.onopen = () => setConnected(true);
        source.onmessage = (event) => {
          const update = JSON.parse(event.data) as LiveUpdate;
          setLatest(update);
          setSessionId(update.session_id);
          setStreamSource(update.stream_health.source);
          setLastReceived(Date.now());
          setConnected(true);
          setUpdates((items) => [...items.filter((item) => item.sequence !== update.sequence), update].slice(-900));
        };
        source.onerror = () => setConnected(false);
      })
      .catch((error: unknown) => {
        setControlError(error instanceof Error ? error.message : "Live engine is unavailable");
        setConnected(false);
      });
    return () => {
      cancelled = true;
      source?.close();
    };
  }, []);

  const stale = !connected || !lastReceived || now - lastReceived > 3000;
  const degraded = latest?.risk_packet.system_mode === "DEGRADED";
  const anomalous = Boolean(latest?.risk_packet.anomaly) && !degraded;
  const status = stale ? "disconnected" : degraded ? "degraded" : anomalous ? "anomaly" : "normal";

  useEffect(() => {
    if (status === "anomaly" && !priorAnomaly.current) beep();
    priorAnomaly.current = status === "anomaly";
  }, [beep, status]);

  const statusCopy = {
    normal: ["NORMAL", "NO ANOMALY DETECTED"],
    anomaly: ["ANOMALY DETECTED", "HUMAN REVIEW REQUIRED"],
    degraded: ["DEGRADED", "DATA QUALITY PROBLEM"],
    disconnected: ["STREAM DISCONNECTED", "LIVE STATUS IS UNAVAILABLE"],
  }[status];

  const evidence = latest?.explanation.detector_evidence ?? {};
  const events = useMemo(
    () => updates.filter((item) => item.recommendation.action !== "NOMINAL").slice(-12).reverse(),
    [updates],
  );
  const sampleAge = lastReceived ? Math.max(0, (now - lastReceived) / 1000) : null;
  const recordedReplay = streamSource === REPLAY_SOURCE;
  const injecting = (latest?.stream_health.scenario ?? "") === "injected_demonstration_excursion";
  const sourceLabel = recordedReplay ? "ESA-ADB MISSION1 REPLAY" : "SYNTHETIC TELEMETRY";
  const activeChannels = useMemo(() => {
    const order = latest?.sample.channel_order ?? Object.keys(channelLabels);
    const responsible = String(
      (latest?.explanation.detector_evidence as { responsible_channel?: unknown } | undefined)
        ?.responsible_channel ?? "",
    );
    const ordered =
      responsible && order.includes(responsible)
        ? [responsible, ...order.filter((channel) => channel !== responsible)]
        : order;
    return ordered.slice(0, 12);
  }, [latest]);

  const control = async (action: string, values: Record<string, unknown> = {}) => {
    setControlError("");
    try {
      const response = await fetch("/api/v1/live/control", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-SATISH-CSRF": csrf },
        body: JSON.stringify({ schema_version: "1.0.0", session_id: sessionId, action, ...values }),
      });
      const body = (await response.json()) as { error?: string };
      if (!response.ok) throw new Error(body.error ?? "Control was rejected");
    } catch (error) {
      setControlError(error instanceof Error ? error.message : "Control was rejected");
    }
  };

  const chooseScenario = async (value: string) => {
    setScenario(value);
    await control("select_scenario", { scenario: value });
  };

  return (
    <main className="live-page">
      <header className="live-nav">
        <Link className="brand" href="/" aria-label="Back to SATISH overview"><span className="brand-mark">S</span><span>SATISH</span><small>LOCAL LIVE EVALUATION</small></Link>
        <div className="live-nav-meta"><span><i /> 127.0.0.1 ONLY</span><b>{sourceLabel}</b><Link href="/">Overview</Link></div>
      </header>

      <section className="live-provenance" aria-label="Data provenance and limits">
        <p>
          {recordedReplay
            ? "Streaming a recorded replay of third-party ESA Anomaly Detection Benchmark (Mission1) telemetry. Advisory only · TRL 4 partial · not operational validation. Not affiliated with, endorsed by, or certified by ESA."
            : "Streaming seeded synthetic local telemetry. Advisory only · TRL 4 partial · not operational validation."}
        </p>
      </section>

      {injecting && (
        <section className="live-injection-banner" role="alert" aria-live="assertive">
          <strong>INJECTED DEMONSTRATION EVENT</strong> — a synthetic in-range excursion added
          on request to exercise the detector and explanation path. This is not a real ESA-ADB
          anomaly.
        </section>
      )}

      <section className={`live-status ${status}`} aria-live="assertive" aria-atomic="true">
        <div className="status-symbol" aria-hidden="true">{status === "normal" ? "✓" : status === "anomaly" ? "!" : status === "degraded" ? "△" : "×"}</div>
        <div><span>{statusCopy[0]}</span><strong>{statusCopy[1]}</strong></div>
        <dl>
          <div><dt>Sample age</dt><dd>{sampleAge === null ? "—" : `${sampleAge.toFixed(1)} s`}</dd></div>
          <div><dt>System mode</dt><dd>{latest?.risk_packet.system_mode ?? "UNKNOWN"}</dd></div>
          <div><dt>Sequence</dt><dd>{latest?.sequence ?? "—"}</dd></div>
        </dl>
      </section>

      <section className="live-summary" aria-label="Current anomaly assessment">
        <article className="primary-reading">
          <div className="live-label">CURRENT ASSESSMENT <span>{latest?.sample.timestamp ? new Date(latest.sample.timestamp).toLocaleTimeString() : "WAITING"}</span></div>
          <h1>{status === "normal" ? "Telemetry is within its approved reference." : status === "anomaly" ? `${latest?.risk_packet.subsystem ?? "Telemetry"} anomaly detected.` : status === "degraded" ? "A prerequisite failed. Interpretation is limited." : "Waiting for the local telemetry service."}</h1>
          <div className="reading-grid">
            <div><span>Responsible channel</span><strong>{String(evidence.responsible_channel ?? "—").replaceAll("_", " ")}</strong></div>
            <div><span>Observed value</span><strong>{number(evidence.raw_value)}</strong></div>
            <div><span>Signed Z-score</span><strong>{number(evidence.signed_z_score)}</strong></div>
            <div><span>Threshold</span><strong>{number(latest?.risk_packet.threshold)}</strong></div>
            <div><span>Margin</span><strong>{number(latest?.risk_packet.margin)}</strong></div>
            <div><span>Recommendation</span><strong className="action-value">{latest?.recommendation.action ?? "—"}</strong></div>
          </div>
        </article>
        <aside className="responsibility-card">
          <div className="live-label">HUMAN RESPONSIBILITY <span>ADVISORY ONLY</span></div>
          <strong>{latest?.recommendation.action === "NOMINAL" ? "No disposition required" : "PENDING REVIEW"}</strong>
          <p>No command is transmitted. Viewing or acknowledging this screen is never represented as spacecraft execution.</p>
          <div><span>Rule</span><b>{latest?.recommendation.rule_ids.join(", ") || "—"}</b></div>
          <div><span>Audit</span><b>{latest?.audit_entry_hash ? `VERIFIED ${latest.audit_entry_hash.slice(0, 12)}…` : "WAITING"}</b></div>
        </aside>
      </section>

      <section className="telemetry-grid" aria-label="Live telemetry charts">
        {activeChannels.map((channel) => {
          const meta = channelDisplay(channel);
          const value = latest?.sample.channel_values[channel];
          return <article className="telemetry-card" key={channel}>
            <div className="live-label">{meta.label}<span>LIVE · 120 SAMPLES</span></div>
            <div className="channel-value"><strong>{number(value)}</strong><span>{meta.unit}</span></div>
            <SparkBars updates={updates} channel={channel} />
          </article>;
        })}
      </section>

      <section className="control-panel" aria-label="Stream controls">
        <div><div className="live-label">GUIDED DEMO CONTROLS <span>NO MODEL SETTINGS</span></div><p>{recordedReplay
          ? "Recorded ESA-ADB replay: pause, resume, reset, or change playback speed. You can inject one clearly labelled demonstration excursion to exercise the detector — it is not a real ESA anomaly."
          : "Choose a clearly labelled synthetic scenario, then inject it into the local stream."}</p></div>
        <div className="control-row">
          <button type="button" onClick={() => void control("pause")}>Pause</button>
          <button type="button" onClick={() => void control("resume")}>Resume</button>
          <button type="button" onClick={() => void control("reset")}>Reset</button>
          <label>Speed<select defaultValue="1" onChange={(event) => void control("set_speed", { speed: Number(event.target.value) })}><option value="0.5">0.5×</option><option value="1">1×</option><option value="2">2×</option></select></label>
          {recordedReplay
            ? <button type="button" className="inject-button" onClick={() => void control("inject")}>Inject demonstration event</button>
            : <>
                <label>Scenario<select value={scenario} onChange={(event) => void chooseScenario(event.target.value)}>{Object.entries(scenarioLabels).filter(([key]) => key !== "normal").map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>
                <button type="button" className="inject-button" onClick={() => void control("inject")}>Inject scenario</button>
              </>}
          <button type="button" aria-pressed={soundEnabled} onClick={() => setSoundEnabled((value) => !value)}>Sound {soundEnabled ? "on" : "off"}</button>
        </div>
        {controlError && <p className="control-error" role="alert">{controlError}</p>}
      </section>

      <section className="live-detail-grid">
        <article className="event-panel">
          <div className="live-label">NON-NOMINAL EVENT QUEUE <span>{events.length} SHOWN</span></div>
          <div className="event-table" role="table" aria-label="Recent non-nominal events">
            {events.length === 0 && <p className="empty-state">No non-nominal events in this session.</p>}
            {events.map((event) => <div className="event-row" role="row" key={event.recommendation.recommendation_id}>
              <time>{new Date(event.sample.timestamp).toLocaleTimeString()}</time>
              <b>{event.risk_packet.subsystem}</b>
              <strong>{event.recommendation.action}</strong>
              <span>{event.risk_packet.system_mode}</span>
              <em>PENDING</em>
            </div>)}
          </div>
        </article>

        <details className="explanation-panel" open>
          <summary>Why did SATISH make this recommendation?<span>FAITHFUL EXPLANATION</span></summary>
          <div className="explanation-body">
            <div className="explain-block"><span>Detector evidence</span><dl><div><dt>Raw value</dt><dd>{number(evidence.raw_value, 4)}</dd></div><div><dt>Rolling mean</dt><dd>{number(evidence.rolling_reference_mean, 4)}</dd></div><div><dt>Rolling std</dt><dd>{number(evidence.rolling_reference_std, 4)}</dd></div><div><dt>Signed Z-score</dt><dd>{number(evidence.signed_z_score, 4)}</dd></div><div><dt>Threshold</dt><dd>{number(evidence.threshold, 4)}</dd></div><div><dt>Margin</dt><dd>{number(evidence.margin, 4)}</dd></div></dl></div>
            <div className="explain-block"><span>Risk arithmetic</span><code>{String(latest?.explanation.risk_factor_decomposition.arithmetic ?? "No anomaly risk arithmetic available")}</code><span>Policy trace</span><code>{latest?.recommendation.rule_set_version ?? "—"} → {latest?.recommendation.rule_ids.join(", ") ?? "—"} → {latest?.recommendation.action ?? "—"}</code></div>
            <div className="explain-block"><span>Counterfactual boundary</span><code>{JSON.stringify(latest?.explanation.feasible_counterfactual ?? {})}</code><span>Reference handling</span><code>{latest?.stream_health.reference_update ?? "—"}</code></div>
            <div className="limits-box"><b>Interpretation limits</b>{latest?.explanation.limitations.map((limit) => <p key={limit}>{limit}</p>) ?? <p>Waiting for an explanation packet.</p>}</div>
          </div>
        </details>
      </section>

      <footer className="live-footer"><span>{recordedReplay ? "ESA-ADB MISSION1 REPLAY" : "LOCAL SYNTHETIC STREAM"} · Z-SCORE · TRL 4 PARTIAL</span><p>Not probability. Not confidence. Not causation. Not flight validation. No command path.</p><b>{sessionId || "NO ACTIVE SESSION"}</b></footer>
    </main>
  );
}
