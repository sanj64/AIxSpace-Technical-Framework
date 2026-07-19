# Operator Demo Execution Plan

Branch: `v1-operator-demo`

This file is the recovery plan for the SATISH AD-DSS operator-demo work. Keep it updated with the actual commands and outputs used to verify each phase.

## Phase 0 - Persistent Instructions And Plan

Status: complete

Expected files touched:

- `AGENTS.md`
- `docs/OPERATOR_DEMO_PLAN.md`

Risks:

- The local environment may not have the full Python dependency stack needed to run the complete suite before the first commit.
- CI currently triggers only for `trl5-build`, `main`, and PRs to `main`; branch CI behavior must be checked separately.

Verification command:

```bash
pytest --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v
```

Actual output:

- `python -m pytest --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v`
  - Result: collection failed before tests ran because `ad_dss` was not importable without installing the package or setting `PYTHONPATH=src`.
- `set PYTHONPATH=src&& python -m pytest --basetemp=.pytest-tmp --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v`
  - Environment: Windows, Python 3.13.13, pytest 8.3.4. CI uses Python 3.11, so this is not CI-equivalent.
  - Result: red, `8 failed, 93 passed in 143.70s`; coverage passed at `86.65%`.
  - Failures: four `tests/test_app_smoke.py` failures from local Streamlit/Starlette import state (`ImportError: cannot import name 'DEFAULT_EXCLUDED_CONTENT_TYPES' from 'starlette.middleware.gzip'`, followed by `DeltaGeneratorSingleton instance already exists`), and four `tests/test_decision_logic.py` RL failures because `gymnasium` and `stable-baselines3` are not available in the local environment.
- `.venv\Scripts\python.exe -m pip install -e .[dev]`
  - Result: installed the repo and dev dependency set into a repo-local virtual environment.
- `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v`
  - Environment: Windows, Python 3.13.13, pytest 9.1.1. CI uses Python 3.11, so this is still not CI-equivalent, but it uses an isolated project dependency set.
  - Result: green, `101 passed in 280.57s`; coverage passed at `90.28%`.

## Phase 1 - Clean, True Base

Status: complete

Expected files touched:

- `archive/README.md`
- `.gitignore`
- `docs/ARTIFACT_REGENERATION.md`
- `AI-FP/failure_predictor.py` moved under `archive/`
- `AD-RRA/risk_allocator.py` moved under `archive/`
- `AI-DSS/DSS_.ipynb` moved under `archive/`
- `Quantum/` moved under `archive/`
- `Thermal/` moved under `archive/`
- `.gitignore`
- README or docs with regeneration commands for generated artifacts

Risks:

- Generated artifacts may already be tracked and large; removal from tracking must preserve local reproducibility instructions.
- The stray-space filename `ESA- M3(preprocessed).zip` may exist only in history or only in local artifacts; do not invent a rename if the file is absent.
- Archive moves may require import-path checks to confirm no active code still references legacy stubs.

Verification commands:

```bash
pytest --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v
ruff check src/ tests/ app/
black --check src/ tests/ app/
mypy src/ad_dss/ --ignore-missing-imports
git status --short
```

Actual output:

- Legacy implementation directories moved under `archive/`; `archive/README.md` states they are superseded by `src/ad_dss` and retained for history only.
- Generated/runtime artifacts removed from Git tracking while preserved locally: top-level `data/`, top-level `models/`, `src/ad_dss.egg-info/`, and legacy AI-FP CSV/ZIP payloads.
- Added `.gitignore` coverage for `data/`, `models/`, `reports/`, local venvs, Python caches, coverage output, and legacy AI-FP CSV/ZIP snapshots.
- Added `docs/ARTIFACT_REGENERATION.md` with commands for synthetic validation artifacts and mission replay reports.
- Fixed local stray-space ESA-M3 names; tracked-path check found no `ESA- M3` paths.
- Added ESA Anomaly Dataset attribution in README: Zenodo record `12528696`, CC BY 3.0 IGO.
- Verification:
  - `.venv\Scripts\python.exe -m ruff check src/ tests/ app/` -> `All checks passed!`
  - `.venv\Scripts\python.exe -m black --check src/ tests/ app/` -> `32 files would be left unchanged.`
  - `.venv\Scripts\python.exe -m mypy src/ad_dss/ --ignore-missing-imports` -> `Success: no issues found in 23 source files`
  - `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v` -> `101 passed in 165.39s`, coverage `90.29%`
  - `git ls-files data models` -> no output
  - `git ls-files AI-FP AD-RRA AI-DSS Quantum Thermal` -> no output
  - `git ls-files | rg -n ESA-.M3` -> no output
  - secret-pattern scan with `rg -n -i -e AKIA -e AIza -e PRIVATE_KEY -e password -e api_key -e apikey -e secret -e token AGENTS.md README.md docs src app tests config archive .github pyproject.toml` -> no output

## Phase 2 - Claims Match Reality

Status: complete

Expected files touched:

- `README.md`
- `pyproject.toml`
- Documentation files under `docs/`

Risks:

- Some uses of "TRL 5" may be historical or targets and must be reframed rather than blindly deleted.
- Every metric in the README must trace to `docs/VALIDATION.md` or another named artifact.

Verification commands:

```bash
rg -n "TRL 5|TRL5|flight-qualified|flight qualified|keeps a human in the loop|AUC-ROC|point-wise F1" README.md docs pyproject.toml src app tests
pytest --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v
```

Actual output:

- Reframed active public claims from completed TRL 5 to operator-demo / TRL 4 partial evidence in `README.md` and `pyproject.toml`.
- Reframed validation documentation while preserving measured values:
  - Precision `1.000`
  - Recall `0.322`
  - F1 `0.487`
  - FAR/hr `0.0`
  - Latency `31`
  - Runtime `7.93s`
  - Reproducibility `100%`
- Marked `docs/PLAN.md` as historical build-plan context rather than the current assessment of record.
- Reframed `docs/ARCHITECTURE.md` and `docs/DECISIONS.md` language so the replay environment and rule-supplement role no longer assert completed TRL 5.
- Updated `tests/validate_trl5.py` user-facing summary text from `TRL 5 VALIDATION SUMMARY` to `VALIDATION EVIDENCE SUMMARY`; filename retained for compatibility.
- Verification:
  - `rg -n "TRL 5|TRL5|flight-qualified|flight qualified|keeps a human in the loop|AUC-ROC|point-wise F1" README.md docs pyproject.toml src app tests`
    - Result: command did not run correctly under local `cmd` quoting; `rg` received fragments of the pattern as filenames and exited `2`.
  - `rg -n -e TRL -e AUC-ROC -e flight-qualified -e human README.md docs pyproject.toml src app tests`
    - Result: remaining TRL matches are active TRL 4 partial statements, historical TRL 5 context in `docs/PLAN.md`, and the operator-plan scan command itself. No `AUC-ROC`, `flight-qualified`, or forbidden HITL phrasing remains outside the operator-plan command text.
  - `.venv\Scripts\python.exe -m ruff check src/ tests/ app/` -> `All checks passed!`
  - `.venv\Scripts\python.exe -m black --check src/ tests/ app/` -> `32 files would be left unchanged.`
  - `.venv\Scripts\python.exe -m mypy src/ad_dss/ --ignore-missing-imports` -> `Success: no issues found in 23 source files`
  - `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v` -> `101 passed in 84.39s`, coverage `90.30%`
  - `git push origin v1-operator-demo` -> pushed commit `be791a1` to `origin/v1-operator-demo`
  - `gh run watch 29667543303 --exit-status` -> GitHub Actions green:
    - `Lint & Format in 12s`
    - `Type Check in 17s`
    - `Smoke — Pipeline in 2m0s`
    - `Tests in 2m36s`

## Phase 3 - Real ESA Data Path

Status: partial - foundation complete, raw telemetry not downloaded

Expected files touched:

- `scripts/` download entrypoint
- `src/ad_dss/data/` loader modules
- `src/ad_dss/evaluation/` or existing evaluation module
- `tests/` fixtures and unit tests
- `docs/VALIDATION_PROTOCOL.md`
- `docs/VALIDATION.md` or a real-data results artifact

Risks:

- Raw telemetry is 11.6 GB and must remain gitignored.
- Zenodo checksum and file metadata must be pulled from record 12528696 rather than guessed.
- Rare nominal event handling must be pre-registered before producing real-data results.
- This overlaps the TF notebook; do not reimplement TF probability calibration or severity-weighted PPO work.

Verification command:

```bash
python scripts/download_esa_adb.py --mission Mission1 --data-dir data/raw
python -m ad_dss.evaluation.esa_adb_mission1 --subsystem thermal --data-dir data/raw --output data/artifacts/reports/mission1_thermal_event_metrics.csv
pytest tests/ -v
```

Actual output:

- Added `scripts/download_esa_adb.py` with Zenodo record `12528696` metadata lookup, mission selection, archive download, and checksum verification when Zenodo provides a supported checksum.
- Added `src/ad_dss/data/esa_adb.py` to load ESA metadata from the existing `ESA-M*/ESA-M*(preprocessed)` folder layout:
  - required: `channels_cleaned.csv`, `labels_cleaned.csv`, `anomaly_types_cleaned.csv`
  - optional: `events_cleaned.csv`, `telecommands_cleaned.csv`
  - telemetry detection ignores metadata files and only reports additional local CSV telemetry files.
- Added `docs/VALIDATION_PROTOCOL.md` before producing ESA metrics:
  - rare nominal events are counted separately from anomaly intervals;
  - prediction hits are event-wise interval overlaps;
  - headline ESA-ADB metric is event-wise F0.5;
  - AUC-PR is the required curve metric, not AUC-ROC;
  - every metrics row must include dataset, model version, and configuration.
- Added `src/ad_dss/evaluation/esa_adb.py` with pure event interval overlap, event-wise precision/recall/F0.5, rare-nominal accounting, and metrics-row output helpers.
- Added `src/ad_dss/evaluation/esa_adb_mission1.py` CLI. With current metadata-only local data, it exits clearly and writes no metrics file.
- Added tests for downloader selection/checksum behavior, ESA metadata loading/subsystem lookup, event overlap, event-wise F0.5, zero-prediction handling, rare-nominal accounting, and evidence-context rows.
- Verification:
  - `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp tests\test_esa_adb_data.py tests\test_esa_adb_evaluation.py tests\test_download_esa_adb.py -v` -> `12 passed in 1.55s`
  - `.venv\Scripts\python.exe scripts\download_esa_adb.py --help` -> printed CLI usage for `--mission`, `--data-dir`, and `--manifest-only`
  - `.venv\Scripts\python.exe -m ad_dss.evaluation.esa_adb_mission1 --subsystem thermal --data-dir data/raw --output data/artifacts/reports/mission1_thermal_event_metrics.csv` -> exited `2` with `ERROR: ESA Mission 1 telemetry not downloaded; metadata-only files are present. Run scripts/download_esa_adb.py before producing metrics.`
  - `if exist data\artifacts\reports\mission1_thermal_event_metrics.csv (echo exists) else (echo missing)` -> `missing`
  - `.venv\Scripts\python.exe -m ruff check src/ tests/ app/ scripts/` -> `All checks passed!`
  - `.venv\Scripts\python.exe -m black --check src/ tests/ app/ scripts/` -> `40 files would be left unchanged.`
  - `.venv\Scripts\python.exe -m mypy src/ad_dss/ --ignore-missing-imports` -> `Success: no issues found in 27 source files`
  - `.venv\Scripts\python.exe -m pytest --basetemp=.pytest-tmp --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v` -> `113 passed in 76.32s`, coverage `88.72%`

## Phase 4 - Operator-Facing Console

Status: pending

Expected files touched:

- `app/streamlit_app.py`
- decision/support modules under `src/ad_dss/`
- audit-log helper module
- scripted UI tests

Risks:

- Blocking human approval must be real stateful behavior, not copy.
- SAFE_MODE needs to be visually and semantically distinct from ALERT_ONLY.
- DEGRADED mode must be triggered by missing channels, NaN output, and excessive ensemble split without crashing.

Verification commands:

```bash
pytest tests/ -v
streamlit run app/streamlit_app.py
```

Scripted UI test command to be finalized after test framework inspection.

Actual output:

- Not yet run.

## Phase 5 - Fault Tolerance And Export Path

Status: pending

Expected files touched:

- model output validation code under `src/ad_dss/models/`
- decision fallback code under `src/ad_dss/decision/`
- export scripts under `scripts/`
- tests for NaN, inf, missing-channel, ensemble disagreement, and export parity
- portable scaler artifact documentation

Risks:

- PPO export may not be cleanly achievable without changing runtime assumptions; if so, document the gap instead of hacking around SB3.
- TensorFlow/ONNX/TFLite dependencies can make clean-venv verification brittle; record exact measured tolerance.

Verification commands:

```bash
pytest tests/ -v
python scripts/export_lstm_autoencoder.py --output-dir models/export
python scripts/verify_exported_lstm.py --model-dir models/export --fixture tests/fixtures/
```

Actual output:

- Not yet run.

## Phase 6 - Readiness Report

Status: pending

Expected files touched:

- `OPERATOR_READINESS.md`
- `docs/OPERATOR_DEMO_PLAN.md`

Risks:

- Report must distinguish measured evidence from remaining gaps.
- Gate IDs must map directly to charter items: H1, C5, C6, R4, R5, S1.

Verification commands:

```bash
pytest --cov=src/ad_dss --cov-report=term-missing --cov-fail-under=75 -v
git status --short
```

Actual output:

- Not yet run.

## Escalations

- 2026-07-18: Initial system-Python verification was red because local Python is 3.13.13 while CI is Python 3.11; `gymnasium` and `stable-baselines3` were missing; Streamlit 1.58.0 with Starlette 0.41.3 failed import. Resolved for local Phase 0 by creating `.venv`, installing `.[dev]`, and rerunning the suite green. A CI-equivalent Python 3.11 run is still preferred before claiming branch CI parity.
