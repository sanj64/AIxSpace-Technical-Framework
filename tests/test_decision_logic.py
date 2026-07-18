"""Tests for decision/decision_logic.py."""

import sys
from types import SimpleNamespace

import pandas as pd
import pytest
import yaml

from ad_dss.common.schemas import Decision, MissionPhase, RiskResult
from ad_dss.decision.decision_logic import DecisionEngine


@pytest.fixture()
def config() -> dict:
    with open("config/settings.yaml") as f:
        return yaml.safe_load(f)


def _risk(level: str, subsystem: str = "EPS") -> RiskResult:
    return RiskResult(
        level=level,
        score=0.8 if level == "CRITICAL" else 0.4,
        reason="test",
        subsystem=subsystem,
        timestamp=pd.Timestamp("2025-01-01"),
    )


def _phase(name: str = "Operations") -> MissionPhase:
    return MissionPhase(name=name, start_idx=0, end_idx=100)


class _FakePPO:
    def __init__(self, policy: str, env: object, verbose: int = 0, seed: int = 42) -> None:
        self.policy = policy
        self.env = env
        self.verbose = verbose
        self.seed = seed
        self.learn_timesteps: int | None = None
        self.saved_path: str | None = None

    def learn(self, total_timesteps: int) -> "_FakePPO":
        self.learn_timesteps = total_timesteps
        return self

    def save(self, path: str) -> None:
        self.saved_path = path

    def predict(self, obs: object, deterministic: bool = True) -> tuple[list[int], None]:
        return [2], None


@pytest.fixture()
def fake_ppo(monkeypatch: pytest.MonkeyPatch) -> type[_FakePPO]:
    monkeypatch.setitem(sys.modules, "stable_baselines3", SimpleNamespace(PPO=_FakePPO))
    return _FakePPO


def test_critical_triggers_safe_mode(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("CRITICAL"), _phase())
    assert decision.action == "SAFE_MODE"


def test_medium_eps_launch_aborts_payload(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("MEDIUM", "EPS"), _phase("Launch"))
    assert decision.action == "ABORT_PAYLOAD"


def test_medium_thermal_deployment_aborts(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("MEDIUM", "Thermal"), _phase("Deployment"))
    assert decision.action == "ABORT_PAYLOAD"


def test_medium_in_ops_notifies_ground(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("MEDIUM", "COM"), _phase("Operations"))
    assert decision.action == "NOTIFY_GROUND"


def test_low_risk_logs(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("LOW"), _phase())
    assert decision.action == "LOG"


def test_decide_returns_decision_schema(config: dict) -> None:
    engine = DecisionEngine(config, mode="rule")
    decision = engine.decide(_risk("LOW"), _phase())
    assert isinstance(decision, Decision)
    assert decision.action in ("IGNORE", "LOG", "NOTIFY_GROUND", "SAFE_MODE", "ABORT_PAYLOAD")
    assert isinstance(decision.reason, str)
    assert isinstance(decision.timestamp, pd.Timestamp)


def test_rl_fallback_without_model(config: dict) -> None:
    engine = DecisionEngine(config, mode="rl")
    # No RL model loaded — should fall back gracefully
    decision = engine.decide_rl(0.9)
    assert isinstance(decision, Decision)
    assert decision.action in ("IGNORE", "LOG", "NOTIFY_GROUND", "SAFE_MODE", "ABORT_PAYLOAD")


def test_rl_fallback_low_score(config: dict) -> None:
    engine = DecisionEngine(config, mode="rl")
    decision = engine.decide_rl(0.1)
    assert decision.action == "LOG"
    assert "fallback" in decision.reason.lower()


def test_anomaly_env_init_and_reset() -> None:
    """AnomalyEnv wraps a gymnasium Env that resets correctly."""
    import numpy as np

    from ad_dss.decision.decision_logic import AnomalyEnv

    scores = np.linspace(0.0, 1.0, 50, dtype=np.float32)
    aenv = AnomalyEnv(scores, threshold=0.5)
    assert aenv._gym_available, "gymnasium must be available in test environment"
    env = aenv.env
    obs, info = env.reset()
    assert obs.shape == (1,)
    assert float(obs[0]) == pytest.approx(scores[0], abs=1e-5)


def test_anomaly_env_step() -> None:
    """AnomalyEnv.step returns correct reward for anomalous score + action."""
    import numpy as np

    from ad_dss.decision.decision_logic import AnomalyEnv

    scores = np.ones(10, dtype=np.float32)  # all scores = 1.0 (anomalous)
    aenv = AnomalyEnv(scores, threshold=0.5)
    env = aenv.env
    env.reset()
    obs, reward, done, truncated, info = env.step(1)  # LOG = correct for anomaly
    assert reward == pytest.approx(1.0)
    obs2, reward2, done2, _, _ = env.step(0)  # IGNORE = wrong for anomaly
    assert reward2 == pytest.approx(-1.0)


def test_train_rl_creates_model(config: dict, fake_ppo: type[_FakePPO]) -> None:
    """train_rl runs without error and sets _rl_model."""
    import numpy as np

    engine = DecisionEngine(config, mode="rl")
    # Override timesteps to tiny value for test speed
    engine.rl_timesteps = 50
    scores = np.random.default_rng(42).uniform(0.0, 1.0, 100).astype(np.float32)
    engine.train_rl(scores, seed=42)
    assert engine._rl_model is not None
    assert isinstance(engine._rl_model, fake_ppo)
    assert engine._rl_model.learn_timesteps == 50


def test_decide_rl_with_trained_model(config: dict, fake_ppo: type[_FakePPO]) -> None:
    """decide_rl uses PPO model when one is loaded."""
    import numpy as np

    engine = DecisionEngine(config, mode="rl")
    engine.rl_timesteps = 50
    scores = np.random.default_rng(7).uniform(0.0, 1.0, 100).astype(np.float32)
    engine.train_rl(scores, seed=7)
    assert engine._rl_model is not None
    assert isinstance(engine._rl_model, fake_ppo)

    decision = engine.decide_rl(0.8)
    assert isinstance(decision, Decision)
    assert decision.action == "NOTIFY_GROUND"


def test_decide_with_rl_model_active(config: dict, fake_ppo: type[_FakePPO]) -> None:
    """decide() routes through RL policy when mode='rl' and model is loaded."""
    import numpy as np

    engine = DecisionEngine(config, mode="rl")
    engine.rl_timesteps = 50
    scores = np.random.default_rng(3).uniform(0.0, 1.0, 100).astype(np.float32)
    engine.train_rl(scores, seed=3)
    assert isinstance(engine._rl_model, fake_ppo)

    risk = _risk("CRITICAL")
    phase = _phase("Operations")
    decision = engine.decide(risk, phase)
    assert isinstance(decision, Decision)


def test_load_rl_missing_file(config: dict) -> None:
    """load_rl with a nonexistent path logs a warning and doesn't crash."""
    from pathlib import Path

    engine = DecisionEngine(config, mode="rl")
    engine.rl_model_path = Path("nonexistent_model_path_xyz")
    engine.load_rl()  # must not raise
    assert engine._rl_model is None
