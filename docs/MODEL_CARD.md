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

XGBoost was trained on Mission 1 with `python -m ad_dss.pipeline.esa_rebuild xgboost-candidate`. It is labelled `RESEARCH_GATED_NOT_ACTIVE_V0_9`, trained 58 of 76 attempted channels, and did not beat the Z-score baseline on aggregate precision, F1, or F0.5. Feature importances are non-causal model sensitivity evidence and cannot be shown as confidence, certainty, probability, or flight validation.

Isolation Forest was trained on Mission 1 with `python -m ad_dss.pipeline.esa_rebuild isolation-forest-candidate`. It is labelled `RESEARCH_GATED_NOT_ACTIVE_V0_9`, trained all 76 attempted channels, and did not beat the Z-score baseline on aggregate precision, recall, F1, or F0.5. Feature sensitivities are non-causal model evidence and cannot be shown as confidence, certainty, probability, or flight validation. Joblib binaries remain local and are referenced by hash in committed manifests.

LSTM autoencoders were trained on Mission 1 with `python -m ad_dss.pipeline.esa_rebuild lstm-candidate`. They are labelled `RESEARCH_GATED_NOT_ACTIVE_V0_9`, trained all 76 attempted channels, and did not beat the Z-score baseline on aggregate precision, F1, or F0.5. Reconstruction errors are model reconstruction evidence only. Keras binaries remain local and are referenced by hash in committed manifests.

| Candidate | Status | Channels trained | Test windows/samples | Precision | Recall | F1 | F0.5 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| XGBoost | Research-gated, not active v0.9 | 58 / 76 | 14042473 samples | 0.0130 | 0.1643 | 0.0241 | 0.0159 |
| Isolation Forest | Research-gated, not active v0.9 | 76 / 76 | 18542473 samples | 0.0151 | 0.0080 | 0.0105 | 0.0128 |
| LSTM autoencoder | Research-gated, not active v0.9 | 76 / 76 | 760000 windows | 0.0277 | 0.3262 | 0.0510 | 0.0339 |

Candidate evidence files:

- `artifacts/esa_rebuild/xgboost_candidate_manifest.json`
- `artifacts/esa_rebuild/mission1_xgboost_metrics.json`
- `artifacts/esa_rebuild/mission1_xgboost_channel_metrics.csv`
- `artifacts/esa_rebuild/mission1_xgboost_feature_attributions.csv`
- `artifacts/esa_rebuild/isolation_forest_candidate_manifest.json`
- `artifacts/esa_rebuild/mission1_isolation_forest_metrics.json`
- `artifacts/esa_rebuild/mission1_isolation_forest_channel_metrics.csv`
- `artifacts/esa_rebuild/mission1_isolation_forest_feature_sensitivity.csv`
- `artifacts/esa_rebuild/lstm_candidate_manifest.json`
- `artifacts/esa_rebuild/mission1_lstm_metrics.json`
- `artifacts/esa_rebuild/mission1_lstm_channel_metrics.csv`
- `artifacts/esa_rebuild/mission1_lstm_training_history.csv`
- `artifacts/esa_rebuild/mission1_lstm_explanation_limitations.json`

Mission 2 and Mission 3 remain unavailable for full raw telemetry training until their full raw telemetry archives are moved into `data/raw/`.
