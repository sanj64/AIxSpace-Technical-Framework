# Security evidence status — 2026-07-21

- `pip-audit 2.9.0` identified four advisories in the initial cryptography pin. The pin
  was raised to `48.0.1`, the Python 3.11/Linux lock and SBOM were regenerated, and the
  follow-up audit reported no known vulnerabilities in the 50 locked runtime packages.
- Trivy 0.71.0 found zero Debian high/critical findings in the pinned Python 3.11.15 base.
  It found two fixed high findings in build tooling vendored by base-image setuptools/
  wheel. The final runtime Docker stage now removes pip, setuptools, and wheel after
  installation so that build tooling is not shipped.
- The local Docker daemon was unavailable, so the final combined image has **not** been
  built or rescanned locally. CI builds the image and uses the repaired Trivy Action
  v0.36.0 pinned to immutable commit `a9c7b0f06e461e9d4b4d1711f154ee024b8d7ab8` to fail on
  fixed high/critical findings.

These are time-bounded engineering scans, not a penetration test or vulnerability warranty.
The independent penetration test and final-image scan remain release gates.
