# SATISH AD-DSS Operator Demo Instructions

<ground_truth>
Verify each of these against the code before relying on it; they were
established by a manual audit on 2026-07-18.

REPO STATE
- `v1-polished` is real, working code: src/ad_dss package (~1,900 lines),
  unified AnomalyDetector (LSTM AE / IsolationForest / rolling z-score),
  RiskPredictor, PPO+gymnasium DecisionEngine, BackupStrategyManager,
  Streamlit app, CI workflow, 101 tests, ~90% coverage.
- `main` is a stale earlier state. Ignore it entirely.
- docs/VALIDATION.md on this branch is honest: on the synthetic thermal
  scenario, precision 1.000 but recall 0.322, F1 0.487, latency 31 samples —
  3 of 9 KPI targets failed. Root causes documented: rolling z-score
  re-adapts to slow drift; IsolationForest contamination (0.05) set far below
  true anomaly rate.
- The README top section claims "TRL 5". This claim was formally WITHDRAWN by
  the project charter (assessment of record: TRL 4 partial). Fixing this is
  Phase 2.
- AI-FP/failure_predictor.py, AD-RRA/risk_allocator.py, and AI-DSS/DSS_.ipynb
  are superseded legacy stubs that contradict src/ad_dss. They must be
  archived, not left in place.
- A separate notebook (SATISH_Pipeline_FIXED.ipynb, in Colab/Drive, NOT in
  this repo) is the Technical Frameworks track's active work: it already has
  probability calibration, severity-weighted PPO reward, and feature-name
  semantics. Do NOT reimplement those here; your outputs must not conflict
  with it. Where you need a contract with it, use the Risk Packet schema
  concept (see DATA FACTS / charter constraints).

DATASET FACTS (ESA Anomaly Dataset, Zenodo 12528696, CC BY 3.0 IGO)
- Real telemetry from 3 ESA missions; missions 1 and 2 form the ESA-ADB
  benchmark: 76 + 100 = 176 channels, already grouped by ESA into 6 named
  subsystems (the subsystem map is a SHIPPED LOOKUP in channels_cleaned.csv —
  never derive it).
- 844 annotated events, only 148 are anomalies; the rest are RARE NOMINAL
  events (mode changes, commanded transitions). The ESA-ADB paper warns that
  naive detectors flag rare nominal events as anomalies, corrupting
  precision. Any scoring you implement must state explicitly how rare
  nominal events are counted, in writing, before results are produced.
- Anomaly density ~1.8% → headline curve metric is AUC-PR, never AUC-ROC
  (charter decision R4).
- Anomalies are time INTERVALS. Evaluation must be event-wise per ESA-ADB
  (a prediction counts if it overlaps the ground-truth interval), with
  corrected event-wise F0.5 as the benchmark-standard headline score —
  operators weight precision over recall because false alarms erode trust.
  Point-wise F1 on this data misrepresents performance; do not headline it.
- The raw telemetry (11.6GB, 3 zips) is NOT in the repo — only metadata
  (channels/labels/anomaly_types CSVs) is. Downloading is Phase 3.

CHARTER CONSTRAINTS (SATISH Charter v4, the technical authority)
- Action space is FIXED at exactly four actions: NOMINAL, COOLDOWN,
  SAFE_MODE, ALERT_ONLY. Everything keys on these; do not invent others.
- The PPO agent RECOMMENDS, never actuates. A deterministic, auditable rule
  engine sits between any learned policy and any action. Reward shaping is
  a training signal, never a safety mechanism.
- Irreversible actions always escalate to a human regardless of model
  confidence. Any upstream failure (NaN output, missing channel, ensemble
  disagreement beyond threshold) forces DEGRADED mode: detection continues,
  autonomy is withdrawn, everything escalates.
- Evidence standard: every reported number names its dataset, model version,
  and configuration. Synthetic results are labelled synthetic, every time.
  Train/calibration/test data never mix.
</ground_truth>

<rules>
1. EVIDENCE OVER ASSERTION. Never mark a phase done without running its
   verification command and recording the actual output. If a number can't
   be produced, write "not measured" — never estimate, never copy a target
   value as if it were a result. This project was previously damaged by
   exactly that failure mode, and the charter now forbids it.
2. STOP-AND-DOCUMENT. If a phase can't be completed as specified, do not
   improvise a workaround that changes the architecture. Write the blocker
   into docs/OPERATOR_DEMO_PLAN.md under "Escalations" and move on.
3. HONEST FRAMING. The correct external phrasing for HITL until Phase 4 is
   verified: "human-in-the-loop is the designed architecture" — NOT "SATISH
   keeps a human in the loop". Mirror this discipline everywhere: describe
   what the code does, not what it is intended to do.
4. Small commits, one concern each, conventional-commit messages. Run the
   test suite before every commit; never commit red.
</rules>
