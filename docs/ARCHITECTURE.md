# Reproducible Pipeline Architecture

```text
ESA Zenodo 12528696
        |
        v
Archive checksum verification
        |
        v
Mission schema validation
        |
        v
Documented cleaning and feature handling
        |
        v
Chronological train / validation / test split
        |
        v
Scaler fit on training partition only
        |
        v
Window generation with leakage checks
        |
        v
Model training from initialized state
        |
        v
Evaluation, reports, figures, model card, manifest
```

The current local checkout verifies archive and metadata evidence but does not contain complete telemetry values. Full training and metric generation therefore fail closed until the full ESA payload is available.

Historical notebooks, stale reports, old trained artifacts, and unverified CSV inputs are isolated in `archive/unverified_pipeline/`.
