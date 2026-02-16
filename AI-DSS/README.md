# 🚀 AI-DSS: Intelligent Decision Support System for Satellite Telemetry

## 📌 Overview
The AI-DSS (Artificial Intelligence – Decision Support System) module is designed to assist satellite operators in real-time monitoring, anomaly assessment, and corrective action recommendation.  

This system integrates outputs from anomaly detection and failure prediction modules to provide intelligent, ranked, and explainable operational decisions.

The DSS acts as the final intelligence layer in the telemetry monitoring pipeline.

---

## 🎯 Objective
To build an AI-driven decision support framework that:

- Monitors real-time satellite telemetry
- Classifies anomaly severity
- Ranks system risks
- Recommends corrective actions
- Assists operators in faster, data-driven decision-making

---

## 🏗️ System Architecture

Telemetry Data  
        ↓  
Preprocessing & Feature Engineering  
        ↓  
Anomaly Detection Module (LSTM / ML Model)  
        ↓  
Failure Prediction Module  
        ↓  
⚡ AI-DSS (Decision Engine)  
        ↓  
Action Recommendation + Risk Ranking  

---

## 🧠 Core Features

### 1️⃣ State-Based Action Recommendation
The DSS analyzes:
- System health indicators
- Predicted anomaly class
- Severity score
- Historical telemetry trends

Based on these inputs, it recommends:
- Continue monitoring
- Trigger subsystem reset
- Switch to backup system
- Enter safe mode
- Raise critical alert

---

### 2️⃣ Anomaly Classification & Ranking
The system:
- Categorizes anomalies (Low / Medium / High / Critical)
- Computes risk score
- Ranks issues based on urgency
- Prioritizes operator attention

Risk score is computed using:
- Deviation magnitude
- Failure probability
- Historical failure correlation

---

### 3️⃣ Integration with Other Modules
The DSS integrates with:

- ✅ Anomaly Detection Module (LSTM-based)
- ✅ Failure Prediction Module
- ✅ Trend Analysis Engine
- ✅ Alert System

It acts as a centralized intelligence layer that converts raw predictions into actionable decisions.

---

## 🛠️ Technologies Used

- Python
- NumPy
- Pandas
- Scikit-learn
- TensorFlow / PyTorch (for LSTM integration)
- Matplotlib (for monitoring visualization)

---

## 📊 Decision Logic (Implemented in Code)

The DSS logic includes:

- Threshold-based anomaly scoring
- Probability-based failure risk estimation
- Rule-based + ML-assisted decision mapping
- Priority ranking algorithm
- Alert triggering mechanism

Example Decision Flow:

IF anomaly_score < threshold_low  
    → Normal Operation  

IF threshold_low ≤ anomaly_score < threshold_high  
    → Monitor Closely  

IF anomaly_score ≥ threshold_high AND failure_prob > 0.7  
    → Trigger Safe Mode  

---

## 📈 Outputs

The DSS produces:

- Recommended Action
- Risk Score
- Severity Level
- Alert Status
- Ranked Issue List

All outputs are generated in structured format (CSV / Table) for dashboard integration.

---

## 🔍 Example Use Case

Input:
- Telemetry voltage spike
- Temperature deviation
- LSTM anomaly probability = 0.82
- Failure prediction probability = 0.76

Output:
- Severity: High
- Risk Score: 0.79
- Recommended Action: Switch to Backup Power Unit
- Alert: Critical

---

## 🚀 Future Enhancements

- Reinforcement Learning-based adaptive decisions (PPO / DQN)
- Explainable AI (SHAP-based decision explanation)
- Real-time dashboard integration
- Edge deployment for onboard processing
- Automated mission risk simulation

---

## 📌 Conclusion

The AI-DSS module transforms raw satellite telemetry insights into intelligent, ranked, and actionable decisions.  
It improves operational safety, reduces manual response delay, and enhances mission reliability through AI-driven automation.

---

👨‍💻 Developed as part of an AI-powered Satellite Monitoring & Autonomous Decision System.
