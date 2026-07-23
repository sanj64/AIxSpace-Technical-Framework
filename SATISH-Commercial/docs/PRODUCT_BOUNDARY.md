# Product boundary

## Included in v0.9 paid evaluation

- Offline, on-premises historical telemetry replay.
- Read-only CSV ingestion; chronological sorting and causal quality processing.
- Z-score or Isolation Forest anomaly detection.
- Transparent risk arithmetic and fixed deterministic advisory rules.
- Layered operator, analyst, and audit explanations.
- Mandatory named disposition of each non-nominal recommendation.
- Signed customer configuration and signed hash-chained audit output.

## Explicitly excluded

- Spacecraft, ground-station, payload, or actuator command creation or transmission.
- Live telemetry adapters (reserved for a gated v1.0 change).
- LSTM, PPO, reinforcement learning, learned decision policies, TensorFlow, Gymnasium,
  Stable-Baselines3, and optional probability/risk classifiers.
- Arbitrary Python, customer plugins, executable configuration, or remote code loading.
- Government, defence, CUI, controlled-mission, and export-controlled deployments.
- ESA telemetry files in the distribution.
- Claims of activation, autonomy, flight readiness, validation, certification, universal
  accuracy, NASA/ESA approval, or operational command acknowledgement.

Every distribution is built only from this repository. The two source repositories
remain provenance evidence and are not distribution inputs.

## Roles that must sign the boundary

Product Owner, Legal Owner, and Model Risk Owner must sign documentary evidence in the
release record. A repository commit is not a legal or organizational approval.
