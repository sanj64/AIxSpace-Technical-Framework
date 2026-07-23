# Threat model

| Threat | Trust boundary | Principal control |
|---|---|---|
| Malicious telemetry/parser input | telemetry mount | size/type/schema limits, causal quality gate, parser fuzzing target |
| Poisoned training labels/data | dataset acquisition | dataset hash/provenance, normal-only filter, independent reproduction |
| Configuration substitution | config mount | Ed25519 verification, hash in every packet, expiry/approval checks |
| Artifact substitution/corruption | evidence volume | serialize-then-hash/load, hash in packets and manifest |
| Unauthorized operator action | browser/identity | OIDC-required mode, role check, named signed disposition |
| Audit editing or reordering | evidence volume | signed hash chain and customer WORM/SIEM checkpoint |
| Secret/key theft | signing boundary | no private key in image/repository; external secret/key service; rotation |
| Dependency compromise | build network | lock, SBOM, audit, reviewed updates, signed provenance |
| Data exfiltration | container network/support | no runtime network; redacted support bundle; least data |
| Container escape | host/runtime | rootless user, read-only filesystem, no capabilities, no-new-privileges |

Open items requiring customer deployment evidence: TLS configuration, OIDC claims/role
mapping, log export, host hardening, volume permissions, denial-of-service limits, and
backup/restore.
