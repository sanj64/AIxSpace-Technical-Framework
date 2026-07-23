# Offline release bundle contents

A release builder must fail unless the bundle contains: rootless OCI image archive and
digest; checksums; SPDX/CycloneDX SBOM; third-party license texts/notices; executed EULA
and order form; support policy; admin/operator/auditor guides; model/system/data cards;
security whitepaper and threat model; signed validation and independent-reproduction
reports; signed Config Pack template; backup/restore/decommission procedure; public
verification key; audit/bundle verification utilities; vulnerability disposition; and
signed release record. Dataset files and private keys are prohibited.

The generic repository does not manufacture executed contracts or independent evidence.
Those files are inserted only by the accountable release process after approval.

After assembling an approved directory, run `create_checksums.py`, sign the manifest with
`sign_bundle.py` using the offline release key, and give the customer `verify_bundle.py`
plus the corresponding public key. Signing keys, datasets, and temporary build material
are never copied into the bundle.
