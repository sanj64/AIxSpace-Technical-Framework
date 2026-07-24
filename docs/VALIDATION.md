# Validation Status

Historical validation reports based on `segments_clean` and `dataset_clean` have been archived and are no longer active evidence.

The active repository does not claim operational validation, flight readiness, certification, or universal model accuracy. The current verified state is:

- ESA Mission 1 archive integrity and schema checks are implemented.
- Historical CSV training inputs are rejected by active training paths.
- A channelwise Z-score baseline has been trained from `ESA-Mission1.zip`.
- The baseline is fit on finite, non-labelled samples in the chronological training partition.
- Thresholds are calibrated on finite, non-labelled validation samples.
- Metrics are evaluated on untouched chronological test samples.

## Metrics

Current sample-level test metrics for the real ESA Mission 1 baseline:

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

These are baseline research results, not production accuracy claims.

## Acceptance Rule

Any future validation report must include the ESA source hash evidence, exact split boundaries, scaler fit partition, code commit, model configuration, output hashes, and remaining limitations.
