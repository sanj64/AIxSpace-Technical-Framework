# Auditor guide

Use the read-only auditor role. Verify the bundle signature, run manifest, dataset/config/
artifact/SBOM/output hashes, schema versions, split boundaries, normal-only fit counts,
metrics, explanation coverage, non-nominal disposition coverage, operator identities, and
audit chain. Compare the last audit hash with the customer WORM/SIEM checkpoint to detect
tail truncation. Record exceptions; never edit evidence in place.
