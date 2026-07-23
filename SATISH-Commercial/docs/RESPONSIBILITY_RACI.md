# Responsibility model

| Activity | Accountable | Responsible/consulted |
|---|---|---|
| Commercial release | Vendor Release Owner | all owners below |
| Model/artifact acceptance | Model Risk Owner | independent reproducer, customer analyst |
| Hazard acceptance | Safety Owner | Model Risk Owner, customer safety representative |
| Security/privacy release | Security/Privacy Owner | privacy officer, penetration tester |
| Config authorship | Customer Administrator or vendor config author | customer engineering |
| Config approval | Independent config approver | cannot be the author |
| Recommendation disposition | Named Operator | optional second reviewer |
| Evidence access/review | Auditor | read-only role |

Accepting a recommendation records a human judgement. It does not issue, execute, or
acknowledge any spacecraft command. The customer retains authority over operational
procedures and command systems, which are outside SATISH.
