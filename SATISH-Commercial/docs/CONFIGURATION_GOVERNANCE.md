# Governed customization

Customer administrators may change only Config Pack fields: channel/subsystem mapping,
physical bounds, detector threshold settings, risk thresholds, criticality and phase
weights, approved branding, expiry, and second-review requirement. The five deterministic
safety rules are fixed in v0.9. Arbitrary Python, expressions, plugins, network calls, and
model uploads are not accepted.

Every proposed pack must be signed by an offline release key, have different author and
approver identities, pass schema/semantic checks, and pass the customer’s approved
regression dataset. Activation records the pack hash, regression evidence hash, approver,
effective/expiry dates, and previous pack. Activation is atomic; rollback selects a still
valid previously approved pack and adds a signed audit entry. Private signing keys remain
outside the container.
