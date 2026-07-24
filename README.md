# AI-DSS Technical Framework

AI-DSS is a spacecraft anomaly detection and decision-support research framework. The active scientific pipeline is being corrected so model artifacts, metrics, and reports are reproducible from the ESA Anomaly Dataset, Zenodo record 12528696.

## Current Evidence Status

The repository now treats historical `segments_clean` and `dataset_clean` files as unverified archive material. They are preserved under `archive/unverified_pipeline/` and are blocked as active training inputs.

The local checkout contains ESA mission metadata files from the preprocessed ESA archives: channels, labels, telecommands, events, and anomaly types. It does not contain complete per-channel telemetry values required to retrain active anomaly models. For that reason, no active model accuracy, precision, recall, F1, ROC-AUC, PR-AUC, calibration, or feature-importance result is claimed until the complete verified ESA payload is installed and the rebuild workflow is run.

## Reproducible Workflow

Install the package in editable mode, then run:

```bash
python -m ad_dss.pipeline.esa_rebuild audit
python -m ad_dss.pipeline.esa_rebuild verify
python -m ad_dss.pipeline.esa_rebuild dry-run
```

`full-rebuild` intentionally fails closed in this checkout because the complete telemetry values are not present:

```bash
python -m ad_dss.pipeline.esa_rebuild full-rebuild
```

## Active Data Policy

Active training must start from the official ESA dataset evidence bundle. The following files are historical only and cannot be supplied to active training:

- `segments_clean.csv`
- `segments_clean (3).csv`
- `dataset_clean.csv`

## Repository Layout

- `src/ad_dss/data/` - preprocessing, ESA verification, leakage controls.
- `src/ad_dss/pipeline/` - reproducible rebuild entrypoints.
- `docs/` - provenance, corrective action, reproducibility, model, and dataset documentation.
- `archive/unverified_pipeline/` - retained historical material that is not active evidence.
- `tests/` - regression tests for reproducibility controls and existing mission logic.

## Quality Checks

```bash
python -m pytest
python -m ruff check .
python -m mypy src
```
