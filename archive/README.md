# Archive

This directory keeps superseded SATISH prototype tracks for historical reference only.

The active AD-DSS implementation is `src/ad_dss`, with the Streamlit operator console in `app/streamlit_app.py`. Files under `archive/` must not be imported by runtime code, used as validation evidence, or presented as current architecture.

Archived tracks:

- `AI-FP/`: legacy failure-predictor stub superseded by `src/ad_dss/models/`.
- `AD-RRA/`: legacy risk-allocation stub superseded by `src/ad_dss/models/risk_predictor.py` and `src/ad_dss/decision/`.
- `AI-DSS/`: legacy notebook/PDF material superseded by the package implementation and app.
- `Quantum/`: earlier placeholder material, not part of the active operator-demo implementation.
- `Thermal/`: earlier thermal prototype material, superseded by packaged detector tests and validation artifacts.

Large CSV/ZIP snapshots from the legacy `AI-FP` directory are intentionally not tracked. Regenerate or download data through the documented data path instead of restoring those files to Git.
