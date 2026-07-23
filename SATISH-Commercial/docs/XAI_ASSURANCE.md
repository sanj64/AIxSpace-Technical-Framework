# Explainability assurance

The design applies the four NISTIR 8312 principles and the NIST AI RMF as governance
references, without claiming NIST certification.

| Principle | Implementation | Verification |
|---|---|---|
| Explanation | Every recommendation links a versioned Explanation Packet | schema and 100% coverage tests |
| Meaningful | operator card, analyst evidence, and complete audit layers | paid-evaluation comprehension/usefulness study |
| Explanation accuracy | Z-score exposes exact arithmetic; Isolation Forest rescores the fitted artifact; policy shows evaluated rules | reproducibility and exact-value tests |
| Knowledge limits | scores labelled non-probabilistic/non-causal; approved reference range and limitations shown; failed prerequisites force `DEGRADED` | claim scan and failure-injection tests |

Risk explanations disclose persistence, criticality, phase weight, thresholds, arithmetic,
and the valid factor change needed to lower a level. Decision explanations disclose rule
set/version, evaluated conditions, override, output, alternatives, and rejection reasons.
No feature sensitivity is represented as cause, operational remedy, certainty, confidence,
or probability.

References: https://www.nist.gov/itl/ai-risk-management-framework and
https://www.nist.gov/publications/four-principles-explainable-artificial-intelligence
