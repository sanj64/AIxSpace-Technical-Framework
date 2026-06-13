# AD-DSS Build Plan — TRL 5 Checklist

**Mission**: Build a fully integrated Spacecraft Health Monitoring — Anomaly Detection & Decision Support System and validate it to TRL 5 (component validation in a relevant environment: realistic mission telemetry replay with noise and injected faults).

**Success Criteria** (must all be true):
1. Every planned module exists with real, working code
2. Single command runs the full pipeline end-to-end
3. TRL 5 evidence: KPIs measured on ≥2 real datasets + thermal scenario
4. Streamlit app launches with one command; scenario replay works
5. pytest passes; coverage ≥75%; ruff + black clean; mypy clean
6. New user can follow README.md to clone, install, run

---

## Phase 0 — Scaffold & Governance
- [x] Create directory tree: `src/ad_dss/{common,core,telemetry,data,models,decision,utils,reports,feedback}/`, `app/`, `config/`, `tests/fixtures/`, `data/{raw,processed,artifacts}/`, `models/`, `docs/`
- [x] Add `__init__.py` to all package directories
- [x] Write `pyproject.toml` (package, scripts, dev deps)
- [x] Write `config/settings.yaml` (fixed YAML; all params, paths, thresholds, seed)
- [x] Write `.github/workflows/ci.yml` (lint → type-check → test → smoke)
- [x] Write `docs/PLAN.md` (this file)
- [x] Write `docs/DECISIONS.md`
- [x] Write `docs/ARCHITECTURE.md`
- [ ] Copy datasets to `data/raw/` (ESA M1/M2/M3 extract, dataset_clean.csv, segments_clean.csv)
- [x] Write `.pre-commit-config.yaml`
- [x] Placeholder test passes
- [ ] **DoD commit**: `feat(scaffold): Phase 0`

**Phase 0 Test Result**: _pending_

---

## Phase 1 — Foundations
- [ ] `src/ad_dss/common/seed.py` — `set_seed(seed)`
- [ ] `src/ad_dss/common/logging_config.py` — `get_logger(name)`
- [ ] `src/ad_dss/common/schemas.py` — `TelemetryFrame, AnomalyResult, RiskResult, Decision, BackupAction, MissionPhase, MissionEvent`
- [ ] `src/ad_dss/telemetry/handler.py` — `TelemetryHandler.load(), generate_synthetic(), to_telemetry_frame()`
- [ ] `src/ad_dss/data/preprocessing.py` — `clean(), interpolate_gaps(), normalize(), create_windows()`
- [ ] `tests/fixtures/telemetry_fixture.csv` — 200-row synthetic CSV
- [ ] `tests/test_handler.py` — 3+ tests
- [ ] `tests/test_preprocessing.py` — 4+ tests
- [ ] All tests green
- [ ] **DoD commit**: `feat(foundations): Phase 1`

**Phase 1 Test Result**: _pending_

---

## Phase 2 — Detection
- [ ] `src/ad_dss/models/anomaly_detector.py` — `AnomalyDetector` (lstm/isolation_forest/zscore unified interface)
- [ ] LSTM AE: port from `_source/Week 6/version_0/models/anomaly_detector.py`
- [ ] Isolation Forest: port from `_source/Week 2.1/anomalydetector.py`
- [ ] Z-score: port from `failure_scenario_case_study.py`
- [ ] `tests/test_anomaly_detector.py` — tests for all three methods
- [ ] All tests green
- [ ] **DoD commit**: `feat(detection): Phase 2`

**Phase 2 Test Result**: _pending_

---

## Phase 3 — Risk & Decision
- [ ] `src/ad_dss/models/risk_predictor.py` — `RiskPredictor` (criticality matrix + phase + persistence + LogReg)
- [ ] `src/ad_dss/decision/decision_logic.py` — `DecisionEngine` (rule + PPO/gymnasium)
- [ ] `src/ad_dss/decision/backup_strategy.py` — `BackupStrategyManager` (config-driven lookup)
- [ ] `tests/test_risk_predictor.py`, `tests/test_decision_logic.py`, `tests/test_backup_strategy.py`
- [ ] All tests green
- [ ] **DoD commit**: `feat(risk-decision): Phase 3`

**Phase 3 Test Result**: _pending_

---

## Phase 4 — Reporting & Visualization
- [ ] `src/ad_dss/utils/visualize.py` — `plot_telemetry(), plot_risk_timeline(), plot_anomaly_scores(), plot_detector_comparison()`
- [ ] `src/ad_dss/reports/generate_report.py` — `generate_report()` → CSV + PDF
- [ ] `tests/test_visualize.py`, `tests/test_generate_report.py`
- [ ] All tests green, PDF produced headlessly
- [ ] **DoD commit**: `feat(reporting): Phase 4`

**Phase 4 Test Result**: _pending_

---

## Phase 5 — Orchestration
- [ ] `src/ad_dss/core/mission_engine.py` — `MissionEngine.run_batch(), run_replay()`, `main()` CLI
- [ ] `tests/test_mission_engine.py`
- [ ] Single command runs full pipeline on real dataset
- [ ] **DoD commit**: `feat(engine): Phase 5`

**Phase 5 Test Result**: _pending_

---

## Phase 6 — Application
- [ ] `app/streamlit_app.py` — scenario selector, playback controls, telemetry panel, risk panel, decision log, report download
- [ ] `tests/test_app_smoke.py` — headless import + single-step smoke test
- [ ] App runs locally
- [ ] **DoD commit**: `feat(app): Phase 6`

**Phase 6 Test Result**: _pending_

---

## Phase 7 — TRL 5 Validation
- [ ] Extract ESA M1/M2/M3 zips to `data/raw/`
- [ ] Run pipeline on dataset_clean.csv + ESA M1 + thermal failure scenario
- [ ] Measure KPIs (precision, recall, F1, ROC-AUC, latency, false-alarm rate, runtime)
- [ ] Baseline comparison: LSTM AE vs IF vs z-score table
- [ ] Reproducibility check: 2× seeded runs → identical outputs
- [ ] Robustness: 20% missing data injection
- [ ] `docs/VALIDATION.md` written with measured results
- [ ] **DoD commit**: `feat(validation): Phase 7`

**Phase 7 KPI Results**: _pending_

---

## Phase 8 — Hardening & Maturity
- [ ] Coverage ≥75% (`pytest --cov`)
- [ ] `mypy src/ad_dss/` clean
- [ ] `ruff + black` clean
- [ ] `README.md` quickstart complete
- [ ] `src/ad_dss/feedback/mission_feedback.py` (optional)
- [ ] CI updated: coverage threshold 75%
- [ ] **DoD commit**: `feat(hardening): Phase 8`

**Phase 8 Test Result**: _pending_

---

## KPI Targets
| KPI | Target | Measured |
|-----|--------|----------|
| F1 (thermal, combined) | ≥ 0.80 | _pending_ |
| Precision | ≥ 0.75 | _pending_ |
| Recall | ≥ 0.85 | _pending_ |
| False alarm rate | ≤ 5/hr | _pending_ |
| Detection latency (samples) | ≤ 30 | _pending_ |
| End-to-end runtime (1800s data) | ≤ 120s | _pending_ |
| Reproducibility | 100% | _pending_ |
| Test coverage | ≥ 75% | _pending_ |
