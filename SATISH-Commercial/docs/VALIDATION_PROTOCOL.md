# Validation and independent reproduction protocol

1. Use synthetic data only for labelled engineering tests.
2. Acquire ESA Mission 1 and Mission 2 independently; verify recorded hashes and license.
3. Apply shipped subsystem mappings and preserve rare nominal events.
4. Sort chronologically, then freeze 60% training, 20% calibration, 20% untouched test.
5. Fit only rows explicitly labelled normal. Calibrate on a separate normal subset.
6. Run rule-only, persistence, and simple statistical baselines with the same test slice.
7. Report event F0.5, event precision/recall, AUC-PR, false alarms/hour, onset latency,
   rare-nominal overlaps, sample/event counts, and uncertainty intervals.
8. Stratify by subsystem, mission phase, anomaly type, and channel class. Do not substitute
   human-demographic fairness language for telemetry coverage analysis.
9. Inject missing/stale channels, NaN/inf, artifact corruption, column reordering, time
   gaps, drift, OOD values, interrupted cleaning, invalid config, and partial output sets.
10. Verify deterministic decisions, actual artifact/config/data binding, audit chain,
    signed config rejection, and first-test-row replay alignment.
11. An independent engineer reproduces from a clean environment and signs the report.

NASA-STD-8739.8 lifecycle assurance and IV&V concepts are a credibility reference only.
The project does not claim NASA approval or certification. Customer-specific acceptance
thresholds belong in the order form; no universal accuracy warranty is allowed.
