# Local-only deployment

SATISH can run entirely on one Windows computer. In this mode, the detector,
configuration, evidence bundles, signing key, operator console, audit logs, synthetic
stream, and dashboard all remain on the local filesystem. Every service binds only to
`127.0.0.1`, so other computers cannot reach them.

## Local topology

```text
signed configuration + calibrated Z-score artifact
                         |
                         v
 deterministic synthetic telemetry (seed 42, 1 Hz)
                         |
                         v
 quality -> detector -> risk -> policy -> explanation -> audit
                         |
          +--------------+----------------+
          |                               |
          v                               v
 operator console               same-origin gateway
 127.0.0.1:8501                 127.0.0.1:3000
                                          |
                              +-----------+-----------+
                              |                       |
                              v                       v
                     renderer :3001          live API/SSE :8765
                         all services loopback only
```

The operator console loads the full local replay evidence directory. The dashboard reads
only the local live service through the gateway. No customer telemetry is required or
uploaded, and the application performs no outbound data transfer.

The gateway serves compiled CSS and JavaScript directly, avoiding the Windows renderer
asset-path failure, and proxies only the versioned local live API. Open:

- `http://127.0.0.1:3000/` for the explanatory overview.
- `http://127.0.0.1:3000/live` for the real-time synthetic monitor.

## Start, inspect, and stop

From the `SATISH-Commercial` directory in PowerShell:

```powershell
.\scripts\Start-SATISH-Local.cmd
.\scripts\Get-SATISH-LocalStatus.cmd
.\scripts\Stop-SATISH-Local.cmd
```

The start script chooses the newest complete `outputs/demo-*` evidence bundle by default.
It verifies the signed configuration, artifact, feature-schema, compiled assets, live
health endpoint, and audit signing before reporting success. To select another governed
run, provide its evidence directory, audit private key, signed configuration, and
configuration public key:

```powershell
.\scripts\Start-SATISH-Local.cmd `
  -RunDirectory "C:\approved\run\evidence" `
  -AuditPrivateKey "C:\approved\keys\audit-private.pem" `
  -ConfigPath "C:\approved\config\evaluation.signed.json" `
  -ConfigPublicKey "C:\approved\keys\release-public.pem" `
  -OperatorId "named.operator"
```

Every start creates `outputs/live/live-*`. During operation, the session contains
telemetry, risk, explanation, recommendation, and signed hash-chain records. Normal
shutdown finalizes file hashes and the session manifest atomically. An interrupted
session retains its active checkpoint for recovery and inspection.

The live reference is causal. Each sample is scored against the preceding window, and
only valid non-anomalous samples update that window. Anomalous or degraded samples freeze
it. Missing or reordered channels, non-finite values, physical-bound violations, stale
or reversed time, schema mismatches, artifact mismatches, and processing failures produce
`DEGRADED` plus `ALERT_ONLY`.

Local evaluation identity mode is intended only for a single-user loopback deployment.
Do not bind it to a LAN address. Shared or operational deployments require TLS, customer
OIDC, governed key custody, export/privacy approval, and the release gates documented in
`RELEASE_GATES.md`.

## Local versus public access

A local-only deployment stops working for viewers when the computer is off and is not
reachable from the internet. Making a computer-hosted instance public would require a
secure reverse proxy or tunnel, firewall policy, TLS, monitoring, patching, and an
always-on host. That is not enabled by these scripts.

The prior cloud showcase is a separate recoverable deployment. It should remain in
owner-only access mode; the local scripts never publish or change it.
