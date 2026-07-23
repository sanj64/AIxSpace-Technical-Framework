# Controlled claims register

Only claims marked **PERMITTED** may appear in customer-facing material, and only with
the cited evidence shipped in the same release. Product and Legal owners approve each
use; this file alone is not approval.

| Claim | Status | Minimum evidence |
|---|---|---|
| “Advisory-only historical telemetry anomaly review” | PERMITTED | Product boundary; binary/interface scan; safety tests |
| “Runs offline in a rootless Linux container” | PERMITTED AFTER BUILD VERIFICATION | OCI configuration, network-disabled deployment test, signed image digest |
| “Uses Z-score or Isolation Forest” | PERMITTED | SBOM, model card, artifact manifest |
| “Every non-nominal recommendation has a layered explanation and human disposition workflow” | PERMITTED AFTER TEST | explanation coverage and disposition tests for the exact release |
| “Measured [metric] on [named dataset/split/config]” | PERMITTED WITH QUALIFICATION | signed reproducible manifest and independent reproduction report |
| “TRL 4 partial evaluation system” | PERMITTED | system card and scope; no higher-TRL implication |
| “Validated,” “certified,” “flight-ready,” “autonomous,” “activation,” “universal accuracy,” “confidence,” or “probability” | PROHIBITED | No current evidence permits these claims |
| NASA/ESA endorsement, approval, or certification | PROHIBITED | No such endorsement exists |

Marketing results must name the dataset, effective slice, detector artifact, configuration
pack, split boundaries, code commit, and uncertainty. “Confidence” may be used only in
the statistical phrase “confidence interval,” never as an anomaly-score interpretation.
