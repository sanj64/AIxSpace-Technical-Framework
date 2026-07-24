# Corrective Action Report

## Actions Completed

- Archived historical unverified CSVs, notebook, PPO artifact, stale metrics, and stale reports.
- Added active guards that reject `segments_clean`, `segments_clean (3)`, and `dataset_clean` as training inputs outside `archive/` and `tests/`.
- Added ESA archive verification, mission schema validation, hash evidence, and manifest generation.
- Added leakage-safe chronological split, train-only scaler fitting, and duplicate-window validation helpers.
- Removed active validation claims based on archived CSVs.
- Added reproducibility documentation and tests.

## Active Limitation

Full retraining is intentionally blocked in this checkout because complete ESA telemetry values are absent. No new active model metrics are published.

## Required Next Action

Install the complete ESA Anomaly Dataset payload from Zenodo record 12528696, rerun `python -m ad_dss.pipeline.esa_rebuild full-rebuild`, and publish only the regenerated artifacts and metrics produced by that workflow.
