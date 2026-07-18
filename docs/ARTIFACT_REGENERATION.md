# Artifact Regeneration

Generated telemetry, model, and report outputs are not tracked in Git. They are runtime artifacts and are ignored under `data/`, `models/`, and `reports/`.

## Validation Artifacts

Regenerate the synthetic thermal validation outputs with:

```bash
.venv\Scripts\python.exe tests/validate_trl5.py
```

Expected outputs:

- `data/artifacts/validation_kpis.csv`
- `data/artifacts/comparison_metrics_thermal.csv`
- `data/artifacts/failure_scenario_thermal.csv`

## Mission Replay Reports

After placing or downloading a telemetry CSV under `data/raw/`, regenerate report CSV/PDF outputs with:

```bash
.venv\Scripts\python.exe -m ad_dss.core.mission_engine --data data/raw/segments_clean.csv --method zscore
```

Expected output directory:

- `data/artifacts/reports/`

## ESA Data

The ESA mission telemetry archives are not tracked. Phase 3 will add a scripted Zenodo downloader for record `12528696` with mission selection and checksum verification. Until then, ESA data files under `data/raw/ESA-M*/` are local-only working copies and must not be used as committed validation evidence.
