# AI-DSS Technical Framework

AI-DSS is a spacecraft anomaly detection and decision-support research framework. The active scientific pipeline is being corrected so model artifacts, metrics, and reports are reproducible from the ESA Anomaly Dataset, Zenodo record 12528696.

## Current Evidence Status

The repository now treats historical `segments_clean` and `dataset_clean` files as unverified archive material. They are preserved under `archive/unverified_pipeline/` and are blocked as active training inputs.

The active baseline has now been trained from the real `ESA-Mission1.zip` archive. It is a channelwise Z-score baseline, not a production model. Current aggregate test metrics are precision `0.0412`, recall `0.2461`, F1 `0.0706`, and F0.5 `0.0494` across `148971440` test samples. Event-level evidence detected `146` of `558` test-overlapping labelled intervals.

## Reproducible Workflow

Install the package in editable mode, then run:

```bash
python -m ad_dss.pipeline.esa_rebuild audit
python -m ad_dss.pipeline.esa_rebuild verify
python -m ad_dss.pipeline.esa_rebuild dry-run
python -m ad_dss.pipeline.esa_rebuild full-rebuild
```

`full-rebuild` expects the real ESA Mission 1 archive at `data/raw/ESA-Mission1.zip` by default. You may override that with `--source-zip`, but it does not fall back to synthetic data or archived historical CSVs.

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
