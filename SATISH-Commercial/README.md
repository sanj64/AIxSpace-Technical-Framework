# SATISH Commercial

SATISH Commercial is a proprietary, advisory-only console for reviewing historical
satellite telemetry and a local synthetic live stream. The v0.9 evaluation build
accepts read-only data, applies quality checks, runs a governed detector, calculates a
deterministic risk level, explains the result, and requires a named human disposition.

The repository is deliberately separate from the two source repositories. Nothing in
this product can transmit a spacecraft command or represent acknowledgement as command
execution. It is a **TRL 4 partial evaluation system**, not flight-ready or certified
mission software.

## Safety contract

```text
read-only replay -> quality gate -> detector -> risk calculation
                 -> deterministic policy -> explanation
                 -> pending recommendation -> human disposition
                 -> signed hash-chained audit record
```

- Fixed recommendation vocabulary: `NOMINAL`, `COOLDOWN`, `SAFE_MODE`, `ALERT_ONLY`.
- Any failed prerequisite forces `DEGRADED` mode and `ALERT_ONLY`.
- Every non-nominal recommendation remains `PENDING` until an operator accepts,
  rejects, or defers it with a rationale.
- Scores are not presented as probability, confidence, or causal effect.
- Configuration is data-only, signed, independently approved, versioned, and expiring.
- Production dependencies contain no TensorFlow, Gymnasium, Stable-Baselines3, LSTM,
  PPO, or learned decision policy.

## Local evaluation

Python 3.11 is the reference runtime.

```bash
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
satish keys generate --private-key release-private.pem --public-key release-public.pem
satish config sign config/evaluation.example.yaml --private-key release-private.pem \
  --output config/evaluation.signed.json
satish replay examples/telemetry.csv --config config/evaluation.signed.json \
  --public-key release-public.pem --output outputs/run
satish audit verify outputs/run/audit.jsonl --public-key release-public.pem
```

Private signing keys must be kept outside the repository and production container.
The Streamlit UI is started with `streamlit run src/satish_commercial/app.py`.

For the current Windows workspace, the operator console, synthetic anomaly engine,
internal renderer, and styled dashboard can be started locally and bound to loopback
only:

```powershell
.\scripts\Start-SATISH-Local.cmd
.\scripts\Get-SATISH-LocalStatus.cmd
.\scripts\Stop-SATISH-Local.cmd
```

See [`docs/LOCAL_DEPLOYMENT.md`](docs/LOCAL_DEPLOYMENT.md) for the local data boundary,
custom run selection, and the difference between local-only and internet-accessible use.

The overview is available at `http://127.0.0.1:3000/` and the real-time synthetic
monitor at `http://127.0.0.1:3000/live`. The live service loads and verifies an existing
signed configuration and calibrated Z-score artifact; it never trains or calibrates
while monitoring. Its output is local evaluation evidence, not spacecraft telemetry,
flight validation, confidence, probability, or a command path.

## Release status

This repository implements the technical v0.9 evaluation boundary and supplies
evidence templates. It is not sale-ready until every externally owned gate in
[`docs/RELEASE_GATES.md`](docs/RELEASE_GATES.md) has documentary evidence and signed
approval. In particular, the repository cannot establish chain of title, issue an
export classification, provide insurance, conduct independent validation, or execute
a customer evaluation agreement.
