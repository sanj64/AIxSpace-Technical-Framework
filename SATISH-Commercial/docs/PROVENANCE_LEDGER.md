# Provenance ledger

This ledger records the source review that informed the new commercial implementation.
No source file has been copied verbatim into this repository as of this ledger version.
Any future import requires a row with source path, repository, commit, author, license,
reviewer, modifications, and retained notices before merge.

| Commercial file or area | Source evidence reviewed | Source commit | Author recorded by Git | License status | Treatment |
|---|---|---|---|---|---|
| Product shell and safety contract | `AIxSpace-Technical-Framework` architecture and tests | `fb765682a8b509b67ba7e88b8ba758f24c4a5ccc` | Benjamin Brumm | Apache-2.0 repository | Clean commercial implementation; no verbatim import |
| ESA ingestion/evaluation concepts | `SATISH v1 Polished` partition-first pipeline | `be941f51b92b8bbd96678c56014089611dde3903` | Benjamin Brumm | **No repository license located; rights unresolved** | Concepts reviewed only; no source redistribution |
| Event-wise metrics | Polished evaluation behavior and review findings | `be941f51b92b8bbd96678c56014089611dde3903` | Benjamin Brumm | Rights unresolved | Independently implemented in `evaluation.py`; counsel review required |
| All other commercial files | New work in this repository | current commercial commit | Current contributors | Company ownership is a target state, not established fact | Contributor assignment required |

Source repositories must be retained unchanged with their Git history. The framework
working tree contained an untracked `notebooks/` directory at review time; this was not
imported. The polished repository was clean at review time.

## Required future-import fields

`destination_path`, `source_repository`, `source_path`, `source_commit`, `source_author`,
`source_license`, `copyright_notice`, `import_reviewer`, `modifications`,
`commercial_license_basis`, `legal_approval_reference`.
