# Unverified Historical Pipeline Archive

This directory preserves historical AI-DSS inputs, notebooks, models, reports, and metrics for audit only.

These files are not active training inputs and are not active validation evidence. They were moved here because the repository did not contain a documented, reproducible path showing that they were generated from the official ESA Anomaly Dataset, Zenodo record 12528696.

Archived material includes:

- `segments_clean` CSV copies.
- `dataset_clean` CSV copies.
- The historical AI-DSS notebook.
- The historical PPO decision artifact.
- Stale validation metrics and reports generated from the archived CSVs.

Active training code must reject these files unless they are used from `archive/` or `tests/` for audit and regression purposes.
