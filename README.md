# AD-DSS Demo Branch

This branch turns the original research framework into a local mission-control demo.

Compared with `main`, it adds a runnable dashboard that replays spacecraft telemetry, highlights unusual behavior, shows the mission risk level, recommends a response, and creates a simple report. It is meant for demonstration and review before merging into the company GitHub.

Best demo path:

```powershell
cd "C:\Users\benja\OneDrive\Documents\IAC 2025\AIxSpace-Technical-Framework"
$env:PYTHONPATH="src"
.\.demo-venv\Scripts\python.exe -m streamlit run app/streamlit_app.py --server.port 8501
```

Open http://localhost:8501 and choose the `zscore` method for the live demo.

---

# AD-DSS — Spacecraft Anomaly Detection & Decision Support System

> **TRL 5** — Component validation in relevant environment (IAC 2025)
>
> *Built on the AIxSpace Technical Framework for the "AI-Powered Space Mission Risk Prediction" project.*

## Quickstart

### 1. Clone and install

```bash
git clone <repo-url>
cd AIxSpace-Technical-Framework
python -m venv .venv
# Windows
.venv\Scripts\pip install -e ".[dev]"
# Linux/macOS
.venv/bin/pip install -e ".[dev]"
```

### 2. Run the pipeline (batch mode)

```bash
python -m ad_dss.core.mission_engine \
  --data data/raw/segments_clean.csv \
  --method zscore
```

Output: anomaly counts, risk events, SAFE_MODE activations, runtime, and a PDF report in `data/artifacts/reports/`.

### 3. Run the Streamlit app

```bash
streamlit run app/streamlit_app.py
```

Select a scenario (CubeSat/LEO, ESA missions, or Synthetic Thermal Failure), press **▶ Play**, and watch telemetry, anomalies, risk state, and decisions evolve in real time. Use **Generate Report** to download CSV + PDF.

### 4. Run the test suite

```bash
pytest --cov=src/ad_dss --cov-report=term-missing
```

Expected: 101 tests passing, ≥90% coverage.

### 5. Run TRL 5 validation

```bash
python tests/validate_trl5.py
```

Produces `data/artifacts/validation_kpis.csv`, `comparison_metrics_thermal.csv`, and `failure_scenario_thermal.csv`. See `docs/VALIDATION.md` for the full report.

---

## Architecture

```
config/settings.yaml          all parameters, thresholds, mission phases
src/ad_dss/
  common/       seed, logging, typed schemas
  core/         mission_engine — orchestrator (batch + replay)
  telemetry/    handler — CSV/JSON ingest
  data/         preprocessing — clean, normalize, window
  models/       anomaly_detector (LSTM AE / IF / Z-score)
                risk_predictor  (criticality matrix + phase)
  decision/     decision_logic  (rule engine + PPO RL)
                backup_strategy (config-driven fallback tables)
  utils/        visualize — matplotlib + plotly figures
  reports/      generate_report — CSV + PDF
  feedback/     mission_feedback — drift detection + threshold suggestions
app/streamlit_app.py          mission replay console
tests/                        101 unit + integration tests
docs/                         PLAN, DECISIONS, ARCHITECTURE, VALIDATION
```

**Data flow:**
```
config → handler → preprocessing → anomaly_detector → risk_predictor
       → decision_logic → backup_strategy → visualize + generate_report
```

---

## Detection Methods

| Method | Description | Best for |
|--------|-------------|----------|
| `zscore` | Rolling-window z-score | Fast onset detection, zero FA |
| `isolation_forest` | sklearn IsolationForest | Segment/feature anomalies |
| `lstm` | Keras LSTM autoencoder | Complex temporal patterns |

Pass `--method <name>` to the CLI or select in the Streamlit sidebar.

---

## Datasets

Place in `data/raw/`:
- `segments_clean.csv` — CubeSat/LEO telemetry, 303k samples
- `dataset_clean.csv` — ESA feature-level segments, 2k samples
- `ESA-M1/`, `ESA-M2/`, `ESA-M3/` — ESA mission archives

The Synthetic Thermal Failure scenario is generated automatically (no external file needed).

---

## Quality Gates

| Check | Command | Target |
|-------|---------|--------|
| Lint | `ruff check src/ tests/ app/` | 0 errors |
| Format | `black --check src/ tests/ app/` | 0 diffs |
| Types | `mypy src/ad_dss/ --ignore-missing-imports` | 0 errors |
| Tests | `pytest --cov=src/ad_dss --cov-fail-under=75` | ≥75% |

---

## TRL 5 Summary

| KPI | Target | Measured |
|-----|--------|----------|
| Precision (thermal, combined) | ≥ 0.75 | 1.000 ✓ |
| Recall (thermal, combined) | ≥ 0.85 | 0.322 (onset only) |
| FAR / hr | ≤ 5.0 | 0.0 ✓ |
| Detection latency | ≤ 30 samples | 31 (≈31 s) |
| Runtime (303k samples) | ≤ 120 s | 7.93 s ✓ |
| Reproducibility | 100% | 100% ✓ |

See `docs/VALIDATION.md` for the full analysis and TRL 6 roadmap.
