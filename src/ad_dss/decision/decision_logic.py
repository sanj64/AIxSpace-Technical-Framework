"""Decision engine: risk → action via rule engine or PPO RL agent."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import Decision, MissionPhase, RiskResult

logger = get_logger(__name__)

_ACTION_MAP = {0: "IGNORE", 1: "LOG", 2: "NOTIFY_GROUND", 3: "SAFE_MODE"}
_LEVEL_ORDER = {"LOW": 0, "MEDIUM": 1, "CRITICAL": 2}


class AnomalyEnv:
    """Gymnasium environment for the PPO decision agent.

    Observation: [normalized_anomaly_score]  (float32, 0..1)
    Actions: {0: IGNORE, 1: LOG, 2: NOTIFY_GROUND, 3: SAFE_MODE}
    Reward: +1 for correct action, -1 for incorrect.
    """

    def __init__(self, scores: np.ndarray, threshold: float = 0.5) -> None:
        try:
            import gymnasium as gym  # noqa: F401
            from gymnasium import spaces

            class _Env(gym.Env):
                metadata: dict = {"render_modes": []}

                def __init__(self_, scores: np.ndarray, threshold: float) -> None:
                    super().__init__()
                    self_.scores = scores.astype(np.float32)
                    self_.index = 0
                    self_.threshold = float(threshold)
                    self_.action_space = spaces.Discrete(4)
                    self_.observation_space = spaces.Box(
                        low=0.0, high=1.0, shape=(1,), dtype=np.float32
                    )

                def reset(self_, *, seed=None, options=None):  # type: ignore[override]
                    super().reset(seed=seed)
                    self_.index = 0
                    return np.array([self_.scores[0]], dtype=np.float32), {}

                def step(self_, action):  # type: ignore[override]
                    score = float(self_.scores[self_.index])
                    is_anomaly = score > self_.threshold
                    reward = (
                        1.0
                        if (is_anomaly and action >= 1) or (not is_anomaly and action == 0)
                        else -1.0
                    )
                    self_.index += 1
                    done = self_.index >= len(self_.scores)
                    obs = np.array(
                        [self_.scores[min(self_.index, len(self_.scores) - 1)]], dtype=np.float32
                    )
                    return obs, reward, done, False, {}

                def render(self_) -> None:
                    pass

            self._env = _Env(scores, threshold)
            self._gym_available = True
        except ImportError:
            self._gym_available = False
            self._env = None
            logger.warning("gymnasium not available; RL training disabled")

    @property
    def env(self):  # type: ignore[return]
        return self._env


class DecisionEngine:
    """Decides what action to take given a RiskResult.

    Mode 'rule': deterministic rule table (always available).
    Mode 'rl': PPO policy trained on anomaly scores (requires gymnasium + SB3).
    """

    def __init__(self, config: dict, mode: str = "rule") -> None:
        d_cfg = config.get("decision", config)
        self.mode = mode or d_cfg.get("mode", "rule")
        self.rl_timesteps: int = int(d_cfg.get("rl_timesteps", 2000))
        self.rl_model_path = Path(
            d_cfg.get("rl_model_path", "archive/unverified_pipeline/ppo_decision_agent")
        )
        self._rl_model: object = None

    # ── Public API ───────────────────────────────────────────────────────────

    def decide(self, risk: RiskResult, phase: MissionPhase) -> Decision:
        """Return the recommended action for a given risk result."""
        if self.mode == "rl" and self._rl_model is not None:
            return self.decide_rl(risk.score)
        return self._rule_decision(risk, phase)

    def train_rl(self, anomaly_scores: np.ndarray, seed: int = 42) -> None:
        """Train PPO on historical anomaly scores."""
        try:
            from stable_baselines3 import PPO

            max_s = anomaly_scores.max() if anomaly_scores.max() > 0 else 1.0
            norm_scores = np.clip(anomaly_scores / max_s, 0.0, 1.0).astype(np.float32)
            threshold = float(np.percentile(norm_scores, 90))

            aenv = AnomalyEnv(norm_scores, threshold=threshold)
            if not aenv._gym_available:
                logger.warning("Skipping RL training: gymnasium not available")
                return

            self._rl_model = PPO("MlpPolicy", aenv.env, verbose=0, seed=seed)  # type: ignore[assignment]
            self._rl_model.learn(total_timesteps=self.rl_timesteps)  # type: ignore[union-attr]
            self.rl_model_path.parent.mkdir(parents=True, exist_ok=True)
            self._rl_model.save(str(self.rl_model_path))  # type: ignore[union-attr]
            logger.info("PPO trained and saved to %s", self.rl_model_path)
        except ImportError:
            logger.warning("stable-baselines3 not available; RL training skipped")

    def load_rl(self) -> None:
        """Load a pre-trained PPO model."""
        try:
            from stable_baselines3 import PPO

            self._rl_model = PPO.load(str(self.rl_model_path))  # type: ignore[assignment]
            logger.info("PPO model loaded from %s", self.rl_model_path)
        except Exception as exc:
            logger.warning("Could not load RL model: %s", exc)

    def decide_rl(self, score: float) -> Decision:
        """Use the trained PPO policy to decide on a normalised anomaly score."""
        if self._rl_model is None:
            logger.warning("RL model not loaded; falling back to threshold rule")
            ts = pd.Timestamp.utcnow()
            action_str = "NOTIFY_GROUND" if score > 0.5 else "LOG"
            return Decision(
                action=action_str, reason="RL fallback: score-threshold rule", timestamp=ts  # type: ignore[arg-type]
            )

        obs = np.array([[float(score)]], dtype=np.float32)
        action, _ = self._rl_model.predict(obs, deterministic=True)  # type: ignore[attr-defined]
        action_int = int(np.asarray(action).flat[0])
        action_str = _ACTION_MAP.get(action_int, "LOG")
        ts = pd.Timestamp.utcnow()
        return Decision(action=action_str, reason=f"RL policy action={action_int}", timestamp=ts)  # type: ignore[arg-type]

    # ── Rule engine ──────────────────────────────────────────────────────────

    def _rule_decision(self, risk: RiskResult, phase: MissionPhase) -> Decision:
        ts = risk.timestamp
        level = risk.level
        sub = risk.subsystem

        if level == "CRITICAL":
            return Decision(
                action="SAFE_MODE",
                reason=f"CRITICAL risk in {sub} during {phase.name}: entering safe mode",
                timestamp=ts,
            )
        if level == "MEDIUM":
            # Thermal or EPS in early phases → abort payload ops
            if sub in ("Thermal", "EPS") and phase.name in (
                "Launch",
                "Deployment",
                "Commissioning",
            ):
                return Decision(
                    action="ABORT_PAYLOAD",
                    reason=f"MEDIUM {sub} risk in {phase.name}: abort payload operations",
                    timestamp=ts,
                )
            return Decision(
                action="NOTIFY_GROUND",
                reason=f"MEDIUM risk in {sub} during {phase.name}: notifying ground",
                timestamp=ts,
            )
        # LOW
        return Decision(
            action="LOG",
            reason=f"LOW risk in {sub} during {phase.name}: logging for review",
            timestamp=ts,
        )
