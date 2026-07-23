# Data bill of materials template

Every evidence run records one row per source dataset in `RunManifestV1.dataset_ids`.
Before release, export these entries with: source title/owner, DOI or customer record,
acquisition date, original and effective SHA-256, license/contract authority, attribution,
no-endorsement text, transformation code/commit, effective rows/channels/events, labels,
rare nominal events, subsystem mapping, exclusions, retention, access/export class, and
deletion owner/date. Synthetic inputs are labelled `synthetic engineering test` and may
not be presented as benchmark evidence.
