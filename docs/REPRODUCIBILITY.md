# Reproducibility

## Commands

```bash
python -m ad_dss.pipeline.esa_rebuild audit
python -m ad_dss.pipeline.esa_rebuild verify
python -m ad_dss.pipeline.esa_rebuild dry-run
python -m ad_dss.pipeline.esa_rebuild clean
```

These commands write evidence under `artifacts/esa_rebuild/`.

## Full Rebuild

```bash
python -m ad_dss.pipeline.esa_rebuild full-rebuild
```

Full rebuild expects the real ESA Mission 1 archive at `data/raw/ESA-Mission1.zip` by default. You may override that with `--source-zip`, but it will not fall back to synthetic data or archived historical CSVs.

## XGBoost Research Candidate

```bash
python -m ad_dss.pipeline.esa_rebuild xgboost-candidate --channel-limit 3
```

The XGBoost path is research-gated for v0.9. It uses chronological train/validation/test partitions, train-only feature filling, validation threshold selection, and feature attribution labelled as model sensitivity evidence rather than causation. It is not an active paid-evaluation detector unless model-risk release gates approve it.

## LSTM Gate

LSTM remains excluded from active v0.9 evidence. Before it can become an active detector, it must add split-safe windows, train-only scaling, overfitting checks, reconstruction-error explanations, independent reproduction, and a model-risk approval record.

## Determinism Requirements

- Seed: 42 unless explicitly changed in the manifest.
- Split method: chronological train, validation, and test partitions.
- Scaler rule: fit on training only.
- Forbidden active inputs: `segments_clean.csv`, `segments_clean (3).csv`, and `dataset_clean.csv`.
- Required evidence: source hashes, split boundaries, scaler partition, generated output hashes, and limitations.
