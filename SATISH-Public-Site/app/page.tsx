"use client";

import { useMemo, useState } from "react";

type Incident = {
  id: string;
  time: string;
  action: "COOLDOWN" | "SAFE_MODE";
  riskLevel: "MEDIUM" | "CRITICAL";
  riskValue: number;
  observed: number;
  mean: number;
  std: number;
  zScore: number;
  margin: number;
  persistence: number;
  counterfactual: number;
  ruleId: string;
  arithmetic: string;
};

const threshold = 3.07729343671302;

const incidents: Incident[] = [
  {
    id: "dd1147df",
    time: "15:30 UTC",
    action: "COOLDOWN",
    riskLevel: "MEDIUM",
    riskValue: 1.3,
    observed: 39,
    mean: 20.6112,
    std: 0.228,
    zScore: 80.6697,
    margin: 77.5924,
    persistence: 1,
    counterfactual: 21.3127,
    ruleId: "POL-003",
    arithmetic: "0.666667 × 1.5 × 1.3 = 1.3",
  },
  {
    id: "6960413c",
    time: "15:31 UTC",
    action: "COOLDOWN",
    riskLevel: "MEDIUM",
    riskValue: 1.625,
    observed: 46,
    mean: 21.2155,
    std: 3.3663,
    zScore: 7.3625,
    margin: 4.2852,
    persistence: 2,
    counterfactual: 31.5747,
    ruleId: "POL-003",
    arithmetic: "0.833333 × 1.5 × 1.3 = 1.625",
  },
  {
    id: "a2c03a6d",
    time: "15:32 UTC",
    action: "SAFE_MODE",
    riskLevel: "CRITICAL",
    riskValue: 1.95,
    observed: 54,
    mean: 22.0611,
    std: 5.6358,
    zScore: 5.6671,
    margin: 2.5898,
    persistence: 3,
    counterfactual: 39.4042,
    ruleId: "POL-002",
    arithmetic: "1.0 × 1.5 × 1.3 = 1.95",
  },
  {
    id: "768db4f3",
    time: "15:33 UTC",
    action: "SAFE_MODE",
    riskLevel: "CRITICAL",
    riskValue: 1.95,
    observed: 61,
    mean: 23.1785,
    std: 8.0969,
    zScore: 4.6711,
    margin: 1.5938,
    persistence: 4,
    counterfactual: 48.0951,
    ruleId: "POL-002",
    arithmetic: "1.0 × 1.5 × 1.3 = 1.95",
  },
  {
    id: "5dc54c58",
    time: "15:34 UTC",
    action: "SAFE_MODE",
    riskLevel: "CRITICAL",
    riskValue: 1.95,
    observed: 68,
    mean: 24.5212,
    std: 10.6214,
    zScore: 4.0935,
    margin: 1.0162,
    persistence: 5,
    counterfactual: 57.2062,
    ruleId: "POL-002",
    arithmetic: "1.0 × 1.5 × 1.3 = 1.95",
  },
];

const temperatures = [
  20.4, 20.6, 20.8, 21, 21.1, 20.9, 21.2, 20.7, 21.1, 21.3, 21, 20.9,
  21.1, 21, 20.8, 21.2, 21, 21.1, 39, 46, 54, 61, 68,
];

const artifactHash = "50e5132e0ed2bb823aae42be92414df522bfad449cfba21be414d6a8e1b63542";
const configHash = "4d4c0c008020d94e1eb042e41b5e04982040e3aef17d3c828a7ae2da399b2057";

function Stat({ value, label, tone }: { value: string; label: string; tone?: string }) {
  return (
    <div className={`stat ${tone ?? ""}`}>
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

export default function Home() {
  const [selectedId, setSelectedId] = useState("a2c03a6d");
  const incident = useMemo(
    () => incidents.find((item) => item.id === selectedId) ?? incidents[2],
    [selectedId],
  );

  const isCritical = incident.action === "SAFE_MODE";

  return (
    <main>
      <nav className="nav" aria-label="Primary navigation">
        <a className="brand" href="#top" aria-label="SATISH home">
          <span className="brand-mark" aria-hidden="true">S</span>
          <span>SATISH</span>
          <small>COMMERCIAL EVALUATION</small>
        </a>
        <div className="nav-links">
          <a href="/live">Live monitor</a>
          <a href="#replay">Replay</a>
          <a href="#explainability">Explainability</a>
          <a href="#boundary">Product boundary</a>
        </div>
        <span className="status-pill"><i /> ESA-ADB Mission1 replay</span>
      </nav>

      <section className="hero" id="top">
        <div className="hero-copy">
          <div className="eyebrow">EXPLAINABLE SPACE OPERATIONS · ADVISORY ONLY</div>
          <h1>See every recommendation.<br /><em>Trace every reason.</em></h1>
          <p>
            SATISH turns read-only telemetry into evidence-backed contingency
            recommendations that remain pending until a human takes responsibility.
          </p>
          <div className="hero-actions">
            <a className="button primary" href="/live">Open live monitor</a>
            <a className="button ghost" href="#replay">Explore the replay</a>
            <a className="button ghost" href="#boundary">Read the limits</a>
          </div>
          <p className="hero-note">
            The live monitor replays third-party ESA Anomaly Detection Benchmark
            (Mission1) telemetry; the walkthrough below is an illustrative example of the
            explanation format, not that replay. This is not operational validation, flight
            software, or a certification claim, and is not affiliated with or endorsed by ESA.
          </p>
        </div>
        <div className="orbit-card" aria-label="Advisory telemetry flow">
          <div className="orbit-grid" aria-hidden="true" />
          <div className="orbit-core">
            <span>READ ONLY</span>
            <strong>TELEMETRY</strong>
          </div>
          <div className="orbit-node node-one"><b>01</b> Quality</div>
          <div className="orbit-node node-two"><b>02</b> Detect</div>
          <div className="orbit-node node-three"><b>03</b> Explain</div>
          <div className="orbit-node node-four"><b>04</b> Human</div>
          <div className="boundary-stamp">NO COMMAND PATH</div>
        </div>
      </section>

      <section className="metrics" aria-label="Demo summary">
        <Stat value="05" label="Non-nominal recommendations" />
        <Stat value="05" label="Human dispositions pending" tone="amber" />
        <Stat value="100%" label="Explanation coverage" tone="cyan" />
        <Stat value="50 / 50" label="Audit records verified" />
      </section>

      <section className="flow-strip" aria-label="SATISH advisory workflow">
        {[
          "Read-only telemetry",
          "Quality gate",
          "Z-score detector",
          "Risk arithmetic",
          "Policy trace",
          "Human disposition",
        ].map((label, index) => (
          <div key={label} className="flow-step">
            <span>{String(index + 1).padStart(2, "0")}</span>
            <b>{label}</b>
          </div>
        ))}
      </section>

      <section className="demo-section" id="replay">
        <div className="section-heading">
          <div>
            <div className="eyebrow">SIGNED REPLAY · RUN 3F0FA1C9</div>
            <h2>Follow one decision end to end.</h2>
          </div>
          <p>
            Select any non-nominal event. This is an illustrative walkthrough of the
            explanation format — not the ESA-ADB replay, which streams on the{" "}
            <a href="/live">live monitor</a>.
          </p>
        </div>

        <div className="console-shell">
          <aside className="incident-list" aria-label="Illustrative replay events">
            <div className="panel-label">EVENT QUEUE <span>5 PENDING</span></div>
            {incidents.map((item, index) => (
              <button
                type="button"
                key={item.id}
                className={`incident ${item.id === selectedId ? "selected" : ""}`}
                onClick={() => setSelectedId(item.id)}
                aria-pressed={item.id === selectedId}
              >
                <span className="incident-index">0{index + 1}</span>
                <span>
                  <b>{item.action}</b>
                  <small>{item.time} · POWER</small>
                </span>
                <i className={item.action === "SAFE_MODE" ? "critical-dot" : "medium-dot"} />
              </button>
            ))}
            <div className="public-lock">
              <span aria-hidden="true">◇</span>
              <p><b>Showcase view is read-only</b>No disposition can be recorded here.</p>
            </div>
          </aside>

          <div className="console-main">
            <div className={`recommendation-banner ${isCritical ? "critical" : "medium"}`}>
              <div>
                <span>{incident.riskLevel} · {incident.time}</span>
                <strong>{incident.action}</strong>
              </div>
              <p>
                {isCritical
                  ? "Contingency recommendation — elevated human review required"
                  : "Cooldown recommendation — human review required"}
              </p>
              <b>PENDING</b>
            </div>

            <div className="operator-grid">
              <article className="panel signal-panel">
                <div className="panel-label">WHAT HAPPENED <span>POWER</span></div>
                <h3>Battery temperature departed its causal reference.</h3>
                <div className="signal-chart" role="img" aria-label={`Battery temperature rose to ${incident.observed} degrees Celsius`}>
                  <div className="chart-threshold"><span>anomaly sequence</span></div>
                  {temperatures.map((value, index) => (
                    <i
                      key={`${value}-${index}`}
                      className={index >= 18 ? "alert-bar" : ""}
                      style={{ height: `${Math.max(7, (value / 72) * 100)}%` }}
                    />
                  ))}
                </div>
                <div className="signal-values">
                  <span><b>{incident.observed.toFixed(1)}°C</b> observed</span>
                  <span><b>{incident.mean.toFixed(2)}°C</b> rolling mean</span>
                  <span><b>{incident.std.toFixed(2)}°C</b> rolling σ</span>
                </div>
              </article>

              <article className="panel evidence-panel">
                <div className="panel-label">WHY IT TRIGGERED <span>Z-SCORE</span></div>
                <div className="score-row">
                  <div><strong>{incident.zScore.toFixed(2)}</strong><span>signed Z-score</span></div>
                  <span className="greater">&gt;</span>
                  <div><strong>{threshold.toFixed(2)}</strong><span>calibrated threshold</span></div>
                </div>
                <div className="gauge" aria-label={`Z-score margin ${incident.margin.toFixed(2)}`}>
                  <i style={{ width: `${Math.min(100, (incident.zScore / Math.max(incident.zScore, 8)) * 100)}%` }} />
                  <b style={{ left: `${Math.min(92, (threshold / Math.max(incident.zScore, 8)) * 100)}%` }}>threshold</b>
                </div>
                <p className="plain-note">
                  The score is statistical distance—not probability, confidence,
                  certainty, or a causal effect.
                </p>
              </article>
            </div>

            <div className="explanation-grid" id="explainability">
              <article className="panel risk-panel">
                <div className="panel-label">RISK ARITHMETIC <span>VISIBLE BY DESIGN</span></div>
                <div className="formula">
                  <div><b>{Math.min(1, 0.5 + 0.5 * (incident.persistence / 3)).toFixed(2)}</b><span>persistence</span></div>
                  <em>×</em>
                  <div><b>1.50</b><span>POWER criticality</span></div>
                  <em>×</em>
                  <div><b>1.30</b><span>commissioning</span></div>
                  <em>=</em>
                  <div className={isCritical ? "critical-result" : "medium-result"}><b>{incident.riskValue.toFixed(3)}</b><span>{incident.riskLevel}</span></div>
                </div>
                <div className="threshold-row">
                  <span>medium ≥ 1.20</span>
                  <span>critical ≥ 1.80</span>
                  <b>{incident.arithmetic}</b>
                </div>
              </article>

              <article className="panel policy-panel">
                <div className="panel-label">DETERMINISTIC POLICY <span>RULE SET 1.0.0</span></div>
                <ol className="rule-trace">
                  <li><i>FALSE</i><span>SYS-001</span> system mode is degraded</li>
                  <li><i>FALSE</i><span>POL-001</span> anomaly equals false</li>
                  <li className="matched"><i>TRUE</i><span>{incident.ruleId}</span> risk level is {incident.riskLevel}</li>
                </ol>
                <div className="policy-result">
                  <span>RESULT</span>
                  <strong>{incident.action}</strong>
                  <small>recommendation only</small>
                </div>
              </article>

              <article className="panel counterfactual-panel">
                <div className="panel-label">WHAT WOULD CHANGE IT <span>COUNTERFACTUAL</span></div>
                <p>Under this exact rolling reference, the nearest non-anomalous boundary is:</p>
                <strong>≤ {incident.counterfactual.toFixed(2)}°C</strong>
                <div className="boundary-line"><i /></div>
                <small>
                  Mathematical threshold boundary only. It does not claim that changing
                  temperature causes a particular spacecraft outcome.
                </small>
              </article>

              <article className="panel human-panel">
                <div className="panel-label">HUMAN RESPONSIBILITY <span>REQUIRED</span></div>
                <div className="pending-state"><i /> PENDING DISPOSITION</div>
                <p>
                  In a governed customer deployment, a named operator must accept,
                  reject, or defer and provide a rationale. Acknowledgement is never
                  represented as command execution.
                </p>
                <div className="disabled-actions" aria-label="Disabled public disposition controls">
                  <span>Accept</span><span>Reject</span><span>Defer</span>
                </div>
              </article>
            </div>

            <details className="audit-drawer">
              <summary>Inspect evidence identity and audit status <span>VERIFIED 50 / 50</span></summary>
              <div className="audit-grid">
                <p><span>Detector</span><b>causal_zscore:1.0.0</b></p>
                <p><span>Explanation</span><b>satish-xai:1.0.0</b></p>
                <p><span>Artifact SHA-256</span><code>{artifactHash}</code></p>
                <p><span>Config SHA-256</span><code>{configHash}</code></p>
                <p><span>Audit chain</span><b>Valid · 50 signed records</b></p>
                <p><span>Source</span><b>Illustrative walkthrough · see /live for the ESA-ADB Mission1 replay</b></p>
              </div>
            </details>
          </div>
        </div>
      </section>

      <section className="principles" id="boundary">
        <div className="section-heading">
          <div>
            <div className="eyebrow">PUBLIC CLAIMS BOUNDARY</div>
            <h2>Useful because its limits are visible.</h2>
          </div>
          <p>
            The local site demonstrates the review experience. Commercial delivery
            remains subject to customer-specific legal, export, security, and validation gates.
          </p>
        </div>
        <div className="principle-grid">
          <article><span>01</span><h3>No actuation</h3><p>No command transmission, spacecraft control, or acknowledgement-as-execution path exists in this demonstration.</p></article>
          <article><span>02</span><h3>Faithful explanation</h3><p>Raw values, baseline, threshold, risk factors, rule trace, counterfactual, and limitations stay attached to each recommendation.</p></article>
          <article><span>03</span><h3>Human accountability</h3><p>Every non-nominal recommendation remains open until a named operator records a reasoned disposition in the governed product.</p></article>
          <article><span>04</span><h3>Honest evidence</h3><p>This is a TRL 4 partial evaluation system. Benchmark-replay results do not establish operational accuracy or flight readiness.</p></article>
        </div>
      </section>

      <section className="evaluation-callout">
        <div>
          <span>PAID EVALUATION SCOPE</span>
          <h2>Historical replay first.<br />Read-only live telemetry later.</h2>
        </div>
        <p>
          Customer-specific configuration, acceptance criteria, support, data handling,
          and permitted claims must be approved before delivery. Government, defence,
          controlled missions, and spacecraft actuation remain outside this public offering.
        </p>
      </section>

      <footer>
        <div className="brand footer-brand"><span className="brand-mark" aria-hidden="true">S</span><span>SATISH</span></div>
        <p>
          ESA-ADB Mission1 replay on the live monitor · illustrative walkthrough here ·
          Advisory only · Third-party ESA Anomaly Detection Benchmark data, not affiliated
          with or endorsed by ESA · No ESA, NASA, NIST, or government endorsement or
          certification is claimed.
        </p>
        <span>v0.9 evaluation preview · TRL 4 partial</span>
      </footer>
    </main>
  );
}
