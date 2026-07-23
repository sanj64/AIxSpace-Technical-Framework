"""Layered, review-only Streamlit console for completed historical replays."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import streamlit as st

from satish_commercial.contracts import Disposition
from satish_commercial.pipeline import record_disposition
from satish_commercial.signing import load_private_key


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _operator_identity() -> tuple[str, bool]:
    try:
        if st.user.is_logged_in:
            return str(st.user.email), True
    except (AttributeError, KeyError):
        pass
    return os.environ.get("SATISH_OPERATOR_ID", ""), False


st.set_page_config(page_title="SATISH Advisory Console", layout="wide")
st.title("SATISH Commercial — Historical Replay")
st.warning(
    "Advisory only. This console cannot transmit spacecraft commands. "
    "Recommendations are not acknowledgement or execution. TRL 4 partial evaluation system."
)

run_text = st.text_input(
    "Completed run directory", value=os.environ.get("SATISH_RUN_DIRECTORY", "")
)
if not run_text:
    st.info("Enter a completed replay directory to review its signed evidence.")
    st.stop()

run_directory = Path(run_text).expanduser().resolve()
required = {
    "risk": run_directory / "risk-packets.jsonl",
    "explanations": run_directory / "explanation-packets.jsonl",
    "recommendations": run_directory / "recommendations.jsonl",
    "manifest": run_directory / "run-manifest.json",
    "audit": run_directory / "audit.jsonl",
}
missing = [name for name, path in required.items() if not path.is_file()]
if missing:
    st.error("Incomplete evidence set; refusing partial output: " + ", ".join(missing))
    st.stop()

risks = {item["packet_id"]: item for item in _jsonl(required["risk"])}
explanations = {item["explanation_id"]: item for item in _jsonl(required["explanations"])}
recommendations = _jsonl(required["recommendations"])
manifest = json.loads(required["manifest"].read_text(encoding="utf-8"))

non_nominal = [item for item in recommendations if item["action"] != "NOMINAL"]
pending = [item for item in non_nominal if item["disposition"] == "PENDING"]
left, middle, right = st.columns(3)
left.metric("Non-nominal", len(non_nominal))
middle.metric("Required dispositions pending", len(pending))
right.metric(
    "Explanation coverage", f"{100 * len(explanations) / max(len(recommendations), 1):.0f}%"
)

if not non_nominal:
    st.success("No non-nominal recommendation occurred in this replay.")
    st.stop()

selected_id = st.selectbox(
    "Recommendation",
    [item["recommendation_id"] for item in non_nominal],
    format_func=lambda value: next(
        f"{item['action']} · {item['disposition']} · {value}"
        for item in non_nominal
        if item["recommendation_id"] == value
    ),
)
recommendation = next(item for item in non_nominal if item["recommendation_id"] == selected_id)
risk = risks[recommendation["risk_packet_id"]]
explanation = explanations[recommendation["explanation_id"]]

if recommendation["action"] == "SAFE_MODE":
    st.error("SAFE_MODE contingency recommendation — visually elevated review required")
elif risk["system_mode"] == "DEGRADED":
    st.warning("DEGRADED — failed prerequisite limits this recommendation to ALERT_ONLY")
else:
    st.info(f"{recommendation['action']} advisory recommendation")

st.subheader("Operator card")
operator_left, operator_right = st.columns(2)
with operator_left:
    st.write(
        {
            "what_happened": (
                f"{risk['detector_identity']} marked telemetry anomalous"
                if risk["anomaly"]
                else "detector result unavailable or non-anomalous"
            ),
            "subsystem": risk["subsystem"],
            "system_mode": risk["system_mode"],
            "recommended_response": recommendation["action"],
            "required_disposition": recommendation["disposition"],
        }
    )
with operator_right:
    st.write("Why")
    st.json(explanation["detector_evidence"], expanded=True)
    st.write("Limits")
    for limitation in explanation["limitations"]:
        st.caption(f"• {limitation}")

with st.expander("Analyst evidence"):
    st.write("Ranked model evidence")
    st.dataframe(explanation["ranked_feature_contributions"], use_container_width=True)
    st.write("Approved reference baseline")
    st.json(explanation["reference_baseline"])
    st.write("Risk arithmetic")
    st.json(explanation["risk_factor_decomposition"])
    st.write("Feasible counterfactual / sensitivity")
    st.json(explanation["feasible_counterfactual"])
    st.write("Configuration and artifact identity")
    st.json(
        {
            "artifact_hash": risk["artifact_hash"],
            "config_hash": risk["config_hash"],
            "feature_schema_hash": risk["feature_schema_hash"],
            "run_id": risk["run_id"],
        }
    )

with st.expander("Audit trace"):
    st.json(explanation["deterministic_policy_trace"])
    st.json({"recommendation": recommendation, "manifest": manifest})
    st.download_button(
        "Download signed audit log",
        required["audit"].read_bytes(),
        file_name="audit.jsonl",
        mime="application/x-ndjson",
    )

identity, oidc_identity = _operator_identity()
role = os.environ.get("SATISH_ROLE", "auditor").lower()
require_oidc = os.environ.get("SATISH_REQUIRE_OIDC", "0") == "1"
if require_oidc and not oidc_identity:
    st.error("Production identity policy requires customer OIDC; disposition is disabled.")
    st.stop()
if role not in {"operator", "admin"}:
    st.info("Read-only auditor role. An operator or administrator must record disposition.")
    st.stop()
if recommendation["disposition"] != "PENDING":
    st.success(
        f"Disposition recorded by {recommendation['operator_identity']}: "
        f"{recommendation['disposition']}"
    )
    st.stop()

st.subheader("Human responsibility")
with st.form("disposition-form"):
    st.text_input("Named operator", value=identity, disabled=True)
    selected_disposition = st.radio("Disposition", ["ACCEPTED", "REJECTED", "DEFERRED"])
    reason_code = st.selectbox(
        "Reason code",
        ["OPERATOR_CONFIRMED", "EVIDENCE_INSUFFICIENT", "KNOWN_NOMINAL_EVENT", "FURTHER_REVIEW"],
    )
    rationale = st.text_area("Rationale (required)")
    second_reviewer = st.text_input("Second reviewer (when required)")
    submitted = st.form_submit_button("Record signed disposition")

if submitted:
    key_path = os.environ.get("SATISH_AUDIT_PRIVATE_KEY", "")
    if not identity:
        st.error("No authenticated or evaluation operator identity is configured.")
    elif not key_path:
        st.error("The audit signing service/key is unavailable; refusing an unsigned disposition.")
    else:
        try:
            record_disposition(
                run_directory,
                recommendation["recommendation_id"],
                Disposition(selected_disposition),
                identity,
                reason_code,
                rationale,
                load_private_key(Path(key_path)),
                second_reviewer_identity=second_reviewer or None,
                require_second_reviewer=os.environ.get("SATISH_SECOND_REVIEW", "0") == "1",
            )
            st.success("Signed human disposition recorded. Refreshing evidence view.")
            st.rerun()
        except Exception as exc:
            st.error(f"Disposition rejected: {exc}")
