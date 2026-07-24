# Corrective Action Report

## Actions Completed

- Archived historical unverified CSVs, notebook, PPO artifact, stale metrics, and stale reports.
- Added active guards that reject `segments_clean`, `segments_clean (3)`, and `dataset_clean` as training inputs outside `archive/` and `tests/`.
- Added ESA archive verification, mission schema validation, hash evidence, and manifest generation.
- Added leakage-safe chronological split, train-only scaler fitting, and duplicate-window validation helpers.
- Trained a real ESA Mission 1 channelwise Z-score baseline from `ESA-Mission1.zip`.
- Removed active validation claims based on archived CSVs.
- Added reproducibility documentation and tests.

## Active Limitation

The current active model is a simple baseline. Aggregate test precision is 0.0412, recall is 0.2461, and F1 is 0.0706, so it is not production-ready.

## Required Next Action

Use the baseline as the reproducibility floor, then develop and independently validate stronger models against the same manifest-controlled ESA pipeline.
