# Administrator guide

1. Verify the signed bundle and image digest before import.
2. Deploy rootless with a read-only root filesystem, internal-only network, read-only
   telemetry/config mounts, and a dedicated evidence volume.
3. Configure TLS and customer OIDC; map only `admin`, `operator`, and `auditor`. Production
   must set `SATISH_REQUIRE_OIDC=1`. Evaluation identity variables are not production auth.
4. Keep signing keys outside the image. Grant the disposition service access only to the
   audit key; configuration/release keys remain offline.
5. Verify and regress every Config Pack, then activate atomically. Monitor expiry and retain
   a still-valid rollback target.
6. Export audit checkpoints to customer WORM/SIEM storage and test restore/verification.
7. Block outbound routing and confirm the container cannot reach public networks.

Do not mount a ground-station or spacecraft command interface into this deployment.
