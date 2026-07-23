# Security whitepaper — evaluation architecture

## Boundary

The reference deployment is a rootless OCI container with a read-only root filesystem,
no runtime network, read-only telemetry/config mounts, and a separate writable evidence
volume. It has no command client. Customer OIDC and TLS are required for production and
must be tested in the customer environment; the environment-variable identity fallback
is explicitly limited to controlled evaluation.

## Integrity

- Ed25519 signatures protect approved configuration and every audit record.
- SHA-256 binds dataset, ordered feature schema, fitted artifact, configuration, SBOM,
  generated evidence, and source commit.
- Audit records are append-only and hash-chained; verification detects modification,
  insertion, deletion before the tail, and reordering. Customer WORM/SIEM export detects
  tail truncation when the remote checkpoint is retained.
- Incomplete output sets and non-empty output targets are rejected.

## Development controls

The CI template runs tests/coverage, Ruff, mypy, Bandit, dependency audit, secret scan,
SBOM generation, OCI build, and artifact checksums. The selling company must configure
protected branches, two-person review for safety/security/config changes, signed commits
and tags, release signing, provenance attestations, vulnerability intake, and retention.

## Release policy

No known exploitable critical vulnerability is permitted. Any accepted high-severity
finding needs an owner, documented rationale, compensating control, and expiry. An
independent penetration test must close critical/high findings before general sale.
