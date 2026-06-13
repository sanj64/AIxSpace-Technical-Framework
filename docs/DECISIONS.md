# Architecture Decision Records (ADR Log)

Format: `ADR-NNN | Date | Status | Decision | Rationale`

---

## ADR-001 | 2026-06-13 | Accepted | Use TensorFlow/Keras exclusively; drop PyTorch

**Context**: The source `test_telemetry_anomaly_dss.py` had a dual-backend (TF + PyTorch) architecture. The brief mandates TF/Keras only.

**Decision**: Remove all PyTorch code. The LSTM autoencoder is implemented in Keras. The RL agent uses `stable-baselines3` which is framework-agnostic.

**Rationale**: Single framework reduces dependency surface, avoids version conflicts, simplifies CI, and the existing Keras LSTM AE is already complete and tested.

---

## ADR-002 | 2026-06-13 | Accepted | Use `gymnasium` (not deprecated `gym`)

**Context**: `gym` is unmaintained since 2022 and does not support NumPy 2.0. The venv shows a warning on import.

**Decision**: Use `import gymnasium as gym` throughout. The AnomalyEnv class uses `gymnasium.Env`, `gymnasium.spaces`.

**Rationale**: `gymnasium` is the community-maintained drop-in replacement; `stable-baselines3` ≥2.0 supports it natively.

---

## ADR-003 | 2026-06-13 | Accepted | PDF generation via matplotlib PdfPages only

**Context**: The report module needs a human-readable PDF. Options: `reportlab`, `fpdf2`, `matplotlib PdfPages`, `weasyprint`.

**Decision**: Use `matplotlib.backends.backend_pdf.PdfPages` to embed figures. Add `fpdf2` as lightweight fallback for text-heavy sections.

**Rationale**: Keeps deps minimal; matplotlib is already required; avoids system-level deps (weasyprint needs Cairo). The report is primarily figure-based anyway.

---

## ADR-004 | 2026-06-13 | Accepted | `segments_clean.csv` as primary training/demo dataset

**Context**: Multiple datasets available (ESA M1/M2/M3, dataset_clean.csv, segments_clean.csv). Need a reliable primary dataset that works without extraction.

**Decision**: Use `segments_clean.csv` (from `AI-FP/`) as primary. It's a pre-cleaned, readily available CSV. ESA M1 (after zip extraction) is used for labelled validation.

**Rationale**: `segments_clean.csv` works out-of-the-box (no zip extraction). ESA M1 has a `labels_cleaned.csv` which provides ground-truth for KPI measurement.

---

## ADR-005 | 2026-06-13 | Accepted | Config-driven architecture; single `config/settings.yaml`

**Context**: The source config had broken YAML indentation in the `failure_scenario:` block (nested keys at wrong indent level).

**Decision**: Rewrite `config/settings.yaml` from scratch with correct YAML structure. All parameters (thresholds, paths, mission phases, model hyperparameters, backup tables) live in this file. No magic numbers in code.

**Rationale**: Single source of truth for configuration; makes parameter sweeps and CI reproducibility trivial.

---

## ADR-006 | 2026-06-13 | Accepted | Python 3.11 target (venv is 3.13)

**Context**: The venv ships Python 3.13.13. The brief says Python 3.11.

**Decision**: Target Python 3.11 syntax in `pyproject.toml` (`requires-python = ">=3.11"`, `target-version = ["py311"]`). The 3.13 venv is fully backward-compatible for 3.11 code.

**Rationale**: Maximises compatibility with CI runners (ubuntu-latest ships 3.11). No 3.12/3.13 exclusive syntax will be used.

---

## ADR-007 | 2026-06-13 | Accepted | LogReg as optional risk classifier (not neural net)

**Context**: The RiskPredictor needs a trainable ML option beyond the rule-based criticality matrix.

**Decision**: `sklearn.linear_model.LogisticRegression` for the optional classifier path. Falls back to criticality matrix if not trained.

**Rationale**: Fast to train, interpretable, no GPU needed, works on small labelled datasets. Sufficient for the rule-supplement role at TRL 5.

---

## ADR-008 | 2026-06-13 | Accepted | ESA M1/M2/M3 zips extracted at build time (not committed)

**Context**: The ESA zip files are >1 MB; the repo has them in `AI-FP/`. Git LFS is not configured.

**Decision**: Extract zips to `data/raw/` at Phase 0 setup (one-time operation). `data/raw/` is in `.gitignore`. Document extraction in README.md.

**Rationale**: Keeps the git tree lean; datasets are reproducible from source zips already in the repo.

---

## ADR-009 | 2026-06-13 | Accepted | LSTM window_size=30 (down from 50 in source)

**Context**: Source `test_telemetry_anomaly_dss.py` used `seq_len=50`. `segments_clean.csv` has limited rows per segment.

**Decision**: Default `window_size=30` in `config/settings.yaml`. Configurable; tests use `window_size=10` for speed.

**Rationale**: Shorter windows work with smaller data batches; still captures temporal patterns; matches 30s of 1Hz telemetry (one orbital maneuver step).

---

## ADR-010 | 2026-06-13 | Accepted | Headless-safe visualization (Agg backend)

**Context**: CI and Streamlit server both need headless plot generation.

**Decision**: All plot functions in `utils/visualize.py` call `matplotlib.use("Agg")` guard and return `Figure` objects without calling `plt.show()`.

**Rationale**: Prevents hanging in headless environments; caller (app or report) decides how to display/save.

---

## Synthetic Fallbacks

If a dataset is unavailable (e.g., zip corrupted), the `TelemetryHandler.generate_synthetic()` method produces a clearly-labeled substitute. Any synthetic data used in validation is explicitly marked `[SYNTHETIC]` in `VALIDATION.md`. No synthetic outputs are presented as real measured results.
