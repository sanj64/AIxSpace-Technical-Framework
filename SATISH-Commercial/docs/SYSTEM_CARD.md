# System card

SATISH v0.9 is a TRL 4 partial historical-replay evaluation system. Its pipeline is:

`read-only telemetry → quality gate → permitted detector → risk arithmetic → fixed policy → explanation → pending advisory recommendation → human disposition → signed audit`

Knowledge limits are made visible through data-quality flags, `DEGRADED` mode, missing
scores, reference ranges, dataset/config/artifact hashes, and explicit explanation
limitations. Any quality or detector prerequisite failure removes advisory autonomy and
produces `ALERT_ONLY`.

The system does not contain a live adapter, command schema, actuator client, flight
software interface, or learned decision policy. Production identity requires customer
OIDC; environment identity is evaluation-only. TLS termination and customer SIEM/WORM
export are deployment responsibilities verified at acceptance.
