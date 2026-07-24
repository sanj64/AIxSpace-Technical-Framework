# Dataset Card

## Dataset

ESA Anomaly Dataset, Zenodo record 12528696.

## Local Contents

This checkout contains ESA preprocessed archives and extracted metadata:

- Mission channel metadata.
- Label intervals.
- Telecommands where available.
- Event and anomaly type metadata where available.

## Not Present

The checkout does not contain complete per-channel telemetry values required for active anomaly model training.

## Use Policy

Historical `segments_clean` and `dataset_clean` CSVs are retained under `archive/unverified_pipeline/` for audit. They must not be used as active model training inputs.

## Attribution

Public reporting should attribute the ESA Anomaly Dataset and Zenodo record 12528696 and must not imply ESA endorsement.
