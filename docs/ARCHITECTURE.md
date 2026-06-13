# AD-DSS Architecture

## System Data Flow

```
config/settings.yaml
       │
       ▼
telemetry/handler.py      ← CSV/JSON or synthetic generator
       │  TelemetryFrame
       ▼
data/preprocessing.py     ← clean, interpolate, normalize, window
       │  np.ndarray windows
       ▼
models/anomaly_detector.py ← LSTM AE | Isolation Forest | Z-score
       │  list[AnomalyResult]
       ▼
models/risk_predictor.py  ← criticality matrix × phase → score → level
       │  list[RiskResult]
       ▼
decision/decision_logic.py ← rule engine | PPO agent → action
       │  Decision
       ▼
decision/backup_strategy.py ← config-driven fallback lookup
       │  list[BackupAction]
       ├──▶ utils/visualize.py → Figure objects
       └──▶ reports/generate_report.py → CSV + PDF
                    ▲
core/mission_engine.py orchestrates all of the above
       │
       ├── batch mode: run_batch(data_path) → dict
       └── replay mode: run_replay(data_path) → Generator[MissionEvent]
                                                      │
                                                      ▼
                                            app/streamlit_app.py
                                    (scenario select, playback, plots, log)
```

## Module Contracts

### `common/schemas.py`
```python
@dataclass
class TelemetryFrame:
    df: pd.DataFrame          # index=timestamp, cols=subsystem_channel
    subsystems: list[str]
    source: str

@dataclass
class AnomalyResult:
    timestamp: pd.Timestamp
    subsystem: str
    reconstruction_error: float
    anomaly_flag: int          # 0 or 1
    score: float               # normalized 0..1

@dataclass
class RiskResult:
    level: Literal["LOW", "MEDIUM", "CRITICAL"]
    score: float               # 0..1
    reason: str
    subsystem: str
    timestamp: pd.Timestamp

@dataclass
class Decision:
    action: Literal["IGNORE", "LOG", "NOTIFY_GROUND", "SAFE_MODE", "ABORT_PAYLOAD"]
    reason: str
    timestamp: pd.Timestamp

@dataclass
class BackupAction:
    component: str
    fallback_component: str
    activated: bool
    reason: str
    timestamp: pd.Timestamp

@dataclass
class MissionPhase:
    name: str
    start_idx: int
    end_idx: int

@dataclass
class MissionEvent:
    step: int
    timestamp: pd.Timestamp
    phase: MissionPhase
    telemetry_snapshot: dict
    anomaly_flags: list[AnomalyResult]
    risk: RiskResult | None
    decision: Decision | None
    backups: list[BackupAction]
```

### `models/anomaly_detector.py` — Interface
```python
class AnomalyDetector:
    def __init__(self, config: dict, method: str = "lstm") -> None: ...
    def train(self, df: pd.DataFrame) -> None: ...
    def score(self, df: pd.DataFrame) -> np.ndarray: ...          # per-window MSE
    def detect(self, df: pd.DataFrame, subsystem: str = "default") -> list[AnomalyResult]: ...
    def save(self, path: Path) -> None: ...
    def load(self, path: Path) -> None: ...
```

### `models/risk_predictor.py` — Interface
```python
class RiskPredictor:
    def __init__(self, config: dict) -> None: ...
    def predict(self, anomalies: list[AnomalyResult], phase: MissionPhase) -> list[RiskResult]: ...
    def train_classifier(self, X: np.ndarray, y: np.ndarray) -> None: ...
```

### `decision/decision_logic.py` — Interface
```python
class DecisionEngine:
    def __init__(self, config: dict, mode: str = "rule") -> None: ...
    def decide(self, risk: RiskResult, phase: MissionPhase) -> Decision: ...
    def train_rl(self, anomaly_scores: np.ndarray) -> None: ...
```

### `core/mission_engine.py` — Interface
```python
class MissionEngine:
    def __init__(self, config_path: Path) -> None: ...
    def run_batch(self, data_path: Path, method: str = "lstm") -> dict: ...
    def run_replay(self, data_path: Path, method: str = "lstm") -> Generator[MissionEvent, None, None]: ...

def main() -> None: ...   # CLI entrypoint
```

## Technology Stack
- **Language**: Python 3.11 (running on 3.13 venv)
- **ML / DL**: TensorFlow 2.21 / Keras; scikit-learn
- **RL**: stable-baselines3 + gymnasium
- **App**: Streamlit 1.58
- **Plotting**: matplotlib (headless Agg), plotly (Streamlit interactive)
- **Config**: PyYAML
- **Quality**: pytest, ruff, black, mypy, pre-commit
- **CI**: GitHub Actions

## TRL 5 Relevant Environment
The relevant environment is a **streaming/replay simulation** over realistic mission telemetry:
- ESA Mission 1, 2, 3 preprocessed datasets
- `segments_clean.csv` (CubeSat/LEO anomaly data)
- Injected thermal ramp failure scenario (synthetic but physically plausible)

The breadboard validation is the `mission_engine.run_replay()` loop processing time-ordered telemetry with real anomaly scoring, risk assessment, and decision-making — the same computational chain that would execute on a ground-station decision support system.
