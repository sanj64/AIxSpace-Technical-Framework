# Preliminary hazard analysis

This is an engineering hazard register for v0.9 replay. Safety Owner review is pending.

| Hazard | Possible cause | Control | Detection/evidence | Residual disposition |
|---|---|---|---|---|
| Missed anomaly | distribution shift, weak signal, threshold | no actuation; human review; customer acceptance thresholds; baseline comparison | event recall, latency, OOD and drift tests | Customer/Safety Owner acceptance required |
| False alert | rare nominal event, threshold, noise | show raw evidence and limits; disposition; rare-nominal analysis | event precision, false alarms/hour, overlap report | Use-case-specific acceptance |
| Incorrect subsystem | mapping error, correlated features | signed mapping; ranked evidence; independent approval | mapping regression suite | Config approver owns correction |
| Stale or missing data | disconnect, gaps, schema loss | `DEGRADED` + `ALERT_ONLY`; score withheld | quality flags and fail-safe tests | Operator investigates source |
| NaN/inf detector output | malformed input, numerical failure | score withheld; `DEGRADED` + `ALERT_ONLY` | non-finite injection tests | Model Risk review |
| Wrong/corrupted artifact | storage or release error | artifact hash in every packet; signed manifest | hash verification and corruption test | Release blocked |
| Configuration error | bad bound/rule/weight | fixed rules; signed/expiring pack; author cannot approve | schema, semantic validation, regression evidence | Activation blocked/rollback |
| Misleading explanation | proxy mistaken for cause/probability | exact arithmetic; actual-model sensitivity label; explicit limits | 100% explanation coverage and claim scan | Model Risk approval |
| Operator overreliance | automation bias | advisory banner; mandatory rationale; comprehension study | paid-evaluation feedback | Training/UI remediation |
| Data poisoning | contaminated normal baseline | dataset hash; normal-only training; independent split/reproduction | provenance and contamination tests | Rebuild artifact |
| Audit tampering | file modification/deletion | signed hash chain; customer WORM/SIEM export | verification utility | Incident response |
| Unauthorized disposition | weak identity/key handling | OIDC-required production mode; roles; signed audit | authentication/authorization test | Release blocked |

Severity and likelihood ratings must be completed with the customer mission context;
generic ratings would create false precision.
