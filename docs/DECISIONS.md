# Architecture Decisions

## ADR-001: ESA Zenodo 12528696 Is Authoritative

Active model training and evaluation must trace to the ESA Anomaly Dataset, Zenodo record 12528696. Historical CSVs without a documented build path are archive evidence only.

## ADR-002: Historical CSVs Are Rejected

`segments_clean.csv`, `segments_clean (3).csv`, and `dataset_clean.csv` are blocked as active training inputs unless they are under `archive/` or `tests/`.

## ADR-003: Fail Closed When Telemetry Is Incomplete

The repository must not publish model metrics when the local data is metadata-only. Full model retraining must fail with a clear error until complete ESA telemetry values are present.

## ADR-004: Train-Only Scaling

Scalers are fit on the training partition only, then applied to validation and test partitions. This prevents validation or test data from influencing preprocessing state.
