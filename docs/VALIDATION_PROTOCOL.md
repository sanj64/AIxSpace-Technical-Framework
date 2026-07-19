# SATISH AD-DSS Validation Protocol

Assessment claims must name the dataset, model version, and configuration used to produce every reported number. Synthetic runs are labelled synthetic every time, and train, calibration, and test data must not mix.

## ESA-ADB Event-Wise Scoring

ESA-ADB anomalies are labelled as time intervals. A predicted interval counts as an anomaly true positive only when it overlaps a ground-truth anomaly interval. Unmatched predicted intervals count as false positives, and unmatched anomaly intervals count as false negatives.

The headline ESA-ADB event metric is corrected event-wise F0.5, not point-wise F1. Precision is weighted over recall because false alarms erode operator trust. AUC-PR is the curve metric for ESA-ADB because anomaly density is low; AUC-ROC must not be used as a headline metric.

## Rare Nominal Events

Rare nominal events are not anomalies. They must be counted separately before results are produced:

- predictions overlapping anomaly intervals count through anomaly precision, recall, and event-wise F0.5;
- predictions overlapping rare nominal intervals are reported as rare-nominal overlaps;
- rare-nominal overlaps remain visible in the output so detector precision is not inflated by treating commanded transitions as anomalies.

## Evidence Output

Every ESA metrics row must include:

- dataset and mission identifier;
- model version and configuration name;
- event true positives, false positives, and false negatives;
- precision, recall, and event-wise F0.5;
- rare-nominal event count and rare-nominal overlap count.

If telemetry is absent, commands must fail clearly and produce no metrics file.
