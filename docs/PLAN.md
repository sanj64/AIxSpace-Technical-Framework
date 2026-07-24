# Corrective Reproducibility Plan

The active AI-DSS pipeline is being corrected for scientific reproducibility from the ESA Anomaly Dataset, Zenodo record 12528696.

## Sequence

1. Preserve historical unverified work under `archive/unverified_pipeline/`.
2. Block active training from `segments_clean`, `segments_clean (3)`, and `dataset_clean`.
3. Verify ESA archive checksums and required mission schemas.
4. Use documented preprocessing only; no hidden notebook transformations.
5. Use chronological leakage-safe train, validation, and test splits.
6. Fit scalers only on the training partition.
7. Generate model artifacts, metrics, figures, reports, and manifests from the verified pipeline only.
8. Publish limitations when complete telemetry or independent reproduction is missing.

## Current Blocker

The local checkout contains ESA metadata but not the complete telemetry values required for scientifically meaningful model training. Full retraining remains blocked until the complete verified ESA payload is installed.
