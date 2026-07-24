# Reproducibility

## Commands

```bash
python -m ad_dss.pipeline.esa_rebuild audit
python -m ad_dss.pipeline.esa_rebuild verify
python -m ad_dss.pipeline.esa_rebuild dry-run
```

These commands write evidence under `artifacts/esa_rebuild/`.

## Full Rebuild

```bash
python -m ad_dss.pipeline.esa_rebuild full-rebuild
```

In this checkout, full rebuild fails closed because complete ESA telemetry values are not present. This is expected and prevents accidental publication of metrics from incomplete or unverified inputs.

## Determinism Requirements

- Seed: 42 unless explicitly changed in the manifest.
- Split method: chronological train, validation, and test partitions.
- Scaler rule: fit on training only.
- Forbidden active inputs: `segments_clean.csv`, `segments_clean (3).csv`, and `dataset_clean.csv`.
- Required evidence: source hashes, split boundaries, scaler partition, generated output hashes, and limitations.
