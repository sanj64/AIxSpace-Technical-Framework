# Evaluation operations

## Install and verify

Verify bundle checksums before loading the OCI archive. Configure the container with no
network, read-only telemetry/config volumes, a dedicated evidence volume, a customer
approved public configuration key, and an audit signing service/key. Production identity
must use OIDC and TLS; do not expose the evaluation identity mode to a shared network.

## Backup and restore

Back up configuration packs, manifests, packet files, audit logs, public keys, OIDC role
mapping, and release records to customer-controlled immutable storage. Verify both file
checksums and audit chains after restore. Private keys follow the customer/vendor key
custody and recovery policy and are never part of a support bundle.

## Support bundle

Default to manifests, software/version information, redacted quality flags, and selected
audit identifiers. Exclude raw telemetry, personal identifiers, private keys, access
tokens, and customer secrets unless separately approved and encrypted. Record purpose,
recipient, export classification, retention, and deletion date.

## Updates and decommissioning

Accept only signed, checksum-verified releases. Preserve the prior image/config for atomic
rollback. On decommission, export required audit/evidence, obtain customer retention
direction, cryptographically erase vendor-held support copies where applicable, revoke
credentials/keys, and record completion. No mission data is collected by default.
