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
python -m ad_dss.pipeline.esa_rebuild xgboost-candidate
```

The XGBoost path is research-gated for v0.9. It uses chronological train/validation/test partitions, train-only feature filling, validation threshold selection, and feature attribution labelled as model sensitivity evidence rather than causation. The Mission 1 full run trained 58 of 76 attempted channels and remains inactive because it did not beat the Z-score baseline on aggregate precision, F1, or F0.5. It is not an active paid-evaluation detector unless model-risk release gates approve it.

## Isolation Forest Research Candidate

```bash
python -m ad_dss.pipeline.esa_rebuild isolation-forest-candidate
```

The Isolation Forest path is research-gated for v0.9. It trains per-channel models on finite, non-labelled chronological training samples, calibrates thresholds on normal calibration scores, and evaluates once on untouched test samples. Feature sensitivities are model evidence rather than causation. Joblib binaries remain local/ignored; manifests record their hashes.

The Mission 1 full run trained all 76 attempted channels and remains inactive because it did not beat the Z-score baseline on aggregate precision, recall, F1, or F0.5.

## LSTM Gate

LSTM remains excluded from active v0.9 evidence. Before it can become an active detector, it must pass overfitting checks, independent reproduction, acceptance-threshold review, explanation review, and a model-risk approval record.

The research-gated LSTM candidate command is:

```bash
python -m ad_dss.pipeline.esa_rebuild lstm-candidate --epochs 2 --batch-size 128 --window-size 32
```

It trains Mission 1 channel autoencoders from random initialization, generates windows independently inside each chronological partition, fits scaling only on finite non-labelled training samples, calibrates on normal calibration windows, and evaluates once on untouched test windows. Keras model binaries remain local/ignored; manifests record their hashes.

The Mission 1 full run trained all 76 attempted channels and remains inactive because it did not beat the Z-score baseline on aggregate precision, F1, or F0.5.

## Determinism Requirements

- Seed: 42 unless explicitly changed in the manifest.
- Split method: chronological train, validation, and test partitions.
- Scaler rule: fit on training only.
- Forbidden active inputs: `segments_clean.csv`, `segments_clean (3).csv`, and `dataset_clean.csv`.
- Required evidence: source hashes, split boundaries, scaler partition, generated output hashes, and limitations.
