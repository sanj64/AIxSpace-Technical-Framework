# Model card — v0.9 permitted detectors

## Intended use

Historical, read-only anomaly review for an approved commercial satellite telemetry
dataset and signed customer configuration. Not for command, actuation, government or
defence missions, or unreviewed channels.

## Causal Z-score

Uses only earlier observations in its rolling window. The explanation identifies the
responsible channel, raw value, reference mean/standard deviation, signed z-score,
threshold, margin, window, and exact threshold boundary. Zero-variance channels produce
zero standardized deviation rather than numerical infinity.

## Isolation Forest

Fits only normal training rows. Its threshold is selected from a separate normal
calibration partition. Explanation rescoring replaces one feature at a time with its
approved training median in the actual fitted model. These values are **model
sensitivities, not causal effects**.

## Shared limits

Scores are not probability, confidence, certainty, severity, or causal attribution.
Performance can change by spacecraft, subsystem, mission phase, channel class, anomaly
type, sampling rate, and configuration. Public claims must use exact measured evidence.
LSTM/PPO and learned policy are excluded.
