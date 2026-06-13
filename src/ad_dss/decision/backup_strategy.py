"""Backup strategy: config-driven fallback lookup tables activated on CRITICAL/MEDIUM decisions."""

from __future__ import annotations

import pandas as pd

from ad_dss.common.logging_config import get_logger
from ad_dss.common.schemas import BackupAction, Decision, RiskResult

logger = get_logger(__name__)


class BackupStrategyManager:
    """Activates pre-defined backup components/procedures based on risk level and decision action."""

    def __init__(self, config: dict) -> None:
        self._strategies: dict = config.get("backup_strategies", {})

    # ── Public API ───────────────────────────────────────────────────────────

    def evaluate(
        self,
        decision: Decision,
        risk: RiskResult,
    ) -> list[BackupAction]:
        """Return list of backup actions warranted by the current decision + risk."""
        actions: list[BackupAction] = []
        strategy = self._strategies.get(risk.subsystem)
        if not strategy:
            logger.debug("No backup strategy defined for subsystem %s", risk.subsystem)
            return actions

        trigger_levels: list[str] = strategy.get("trigger_levels", ["CRITICAL"])
        if risk.level not in trigger_levels:
            return actions

        ts = risk.timestamp
        component = strategy.get("component", "unknown")
        fallback = strategy.get("fallback", "none")
        reason = strategy.get("reason", f"Backup for {risk.subsystem} at {risk.level}")

        action = BackupAction(
            component=component,
            fallback_component=fallback,
            activated=True,
            reason=reason,
            timestamp=ts,
        )
        actions.append(action)
        logger.info(
            "Backup activated: %s → %s (%s level, action=%s)",
            component,
            fallback,
            risk.level,
            decision.action,
        )
        return actions

    def evaluate_all(
        self,
        decisions: list[tuple[Decision, RiskResult]],
    ) -> list[BackupAction]:
        """Evaluate backup strategies for a batch of (decision, risk) pairs."""
        all_actions: list[BackupAction] = []
        for dec, risk in decisions:
            all_actions.extend(self.evaluate(dec, risk))
        return all_actions
