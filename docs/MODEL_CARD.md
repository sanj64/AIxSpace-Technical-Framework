# Model Card

## Active Model Status

A real-data ESA Mission 1 channelwise Z-score baseline is published in `artifacts/esa_rebuild/mission1_zscore_model.json`.

Historical model artifacts remain archived because they were not reproducibly regenerated from the verified ESA dataset in the corrected pipeline.

## Training Data

Source: `data/raw/ESA-Mission1.zip`, SHA-256 `8c81edb1e81af9084f38a3cc06fa06dbea73b504c99ce1b0fb92bda996b801a7`.

The trainer fits each channel independently using finite, non-labelled samples in the chronological training partition. It calibrates thresholds on finite, non-labelled validation samples and evaluates the untouched chronological test partition.

## Baseline Metrics

| Metric | Value |
| --- | ---: |
| Channels trained | 76 |
| Test samples | 148971440 |
| Label-positive test samples | 1966322 |
| Precision | 0.0412 |
| Recall | 0.2461 |
| F1 | 0.0706 |
| F0.5 | 0.0494 |

Event-level evidence: 146 of 558 test-overlapping labelled intervals were detected.

## Evidence Files

- `artifacts/esa_rebuild/full_rebuild_manifest.json`
- `artifacts/esa_rebuild/mission1_metrics.json`
- `artifacts/esa_rebuild/mission1_channel_metrics.csv`
- `artifacts/esa_rebuild/mission1_event_metrics.csv`
- `artifacts/esa_rebuild/mission1_training_progress.csv`

## Current Limitations

This is a simple univariate per-channel Z-score baseline. The aggregate precision and recall are low, and many labelled intervals are not detected. These results should be used as a reproducible baseline for further model development, not as production performance evidence.

## Research-Gated Candidates

XGBoost may be trained with `python -m ad_dss.pipeline.esa_rebuild xgboost-candidate`, but any generated XGBoost artifact is labelled `RESEARCH_GATED_NOT_ACTIVE_V0_9`. Feature importances are non-causal model sensitivity evidence and cannot be shown as confidence, certainty, probability, or flight validation.

LSTM remains a backlog/research item and is not active v0.9 evidence.
