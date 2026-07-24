# Data Provenance Report

## Authoritative Source

The authoritative dataset for active AI-DSS training and evaluation is the ESA Anomaly Dataset, Zenodo record 12528696.

## Repository Evidence

The repository contains three ESA preprocessed archives in `AI-FP/` and extracted mission metadata under `data/raw/ESA-M1`, `data/raw/ESA-M2`, and `data/raw/ESA-M3`.

Observed metadata row counts:

| File | Rows | Columns |
| --- | ---: | --- |
| `data/raw/ESA-M1/ESA-M1(preprocessed)/channels_cleaned.csv` | 76 | Channel, Subsystem, Physical Unit, Group, Target |
| `data/raw/ESA-M1/ESA-M1(preprocessed)/labels_cleaned.csv` | 3589 | ID, Channel, StartTime, EndTime, Duration |
| `data/raw/ESA-M2/ESA-M2(preprocessed)/channels_cleaned.csv` | 76 | Channel, Subsystem, Physical Unit, Group, Target |
| `data/raw/ESA-M2/ESA-M2(preprocessed)/labels_cleaned.csv` | 3589 | ID, Channel, StartTime, EndTime, Duration |
| `data/raw/ESA-M3/ESA- M3(preprocessed)/channels_cleaned.csv` | 76 | Channel, Subsystem, Physical Unit, Group, Target |
| `data/raw/ESA-M3/ESA- M3(preprocessed)/labels_cleaned.csv` | 3589 | ID, Channel, StartTime, EndTime, Duration |

## Historical CSV Conclusion

`segments_clean` has 303493 rows and 10 columns: channel, timestamp, value, label, sampling, anomaly, segment, train, label_numeric, and value_normalized.

`dataset_clean` has 2123 rows and 23 columns: segment, anomaly, train, channel, sampling, duration, len, mean, var, std, kurtosis, skew, and derived feature columns.

The active copies under `data/raw/` matched the historical copies under `AI-FP/` by structure and are archived for audit. The repository did not contain a documented, executable build path proving that these CSVs were produced exclusively from ESA Zenodo record 12528696 with leakage-safe preprocessing.

Conclusion: provenance is unverified. These files are not active training inputs.

## Remaining Gap

The local checkout does not contain complete per-channel ESA telemetry values. It contains mission metadata sufficient for schema and provenance checks, but not enough for scientifically meaningful model retraining.
