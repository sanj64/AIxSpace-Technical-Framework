# Release gates and sale-ready definition

Copy the appropriate stage template to a controlled release record. The command
`satish release check release/release-record.yaml` fails unless every gate is
`APPROVED`, names accountable approvers, and points to existing evidence files. Never
change a status merely to make CI pass.

## v0.9 paid evaluation

- Product boundary, provenance ledger, and claims register signed.
- Counsel-approved chain of title, dual-license basis, EULA/order form, privacy terms,
  export/sanctions clauses, warranty/indemnity/acceptance terms, and public claims.
- Customer/delivery-specific Canada and US classification/screening recorded.
- Historical replay only; signed customer pack; no live adapter or actuation.
- P0/P1 defects closed; hazard/model-risk review signed; 100% non-nominal explanation.
- Reproducible evidence, SBOM, signed bundle, vulnerability review, guides, and support
  policy supplied under a fixed-duration evaluation agreement.

## v1.0 production advisory

Everything above plus signed paid-evaluation acceptance, a separately reviewed read-only
live adapter passing schema/latency/disconnect/replay-parity/fail-safe tests, production
OIDC/TLS, full disposition coverage, independent reproduction, independent penetration
test remediation, and all owner signoffs.

## External gates this repository cannot complete

- Company chain of title, contributor/contractor assignments, trademark, patent/FTO,
  trade-secret review, and counsel opinion on prior Apache-2.0 distribution/dual license.
- Canadian/US export classifications, Controlled Goods determination, sanctions and
  denied-party screening, and any permit.
- Executed contracts, privacy officer appointment, insurance coverage opinion.
- Independent reproduction and penetration-test reports.
- Signed commercial operator evaluation acceptance.

Until every relevant gate has valid evidence, SATISH remains a TRL 4 partial evaluation
system and is not ready for open-market sale.
