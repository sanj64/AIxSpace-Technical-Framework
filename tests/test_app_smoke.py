"""Headless smoke tests for the Streamlit app (import + logic only)."""

import numpy as np
import pandas as pd
import pytest


def test_app_imports() -> None:
    """App module and key functions import without error."""
    from app.streamlit_app import (
        build_app,
        _load_config,
        _render_sidebar,
        _render_telemetry_panel,
        _render_risk_panel,
        _render_decision_log,
    )


def test_load_config_returns_dict() -> None:
    from app.streamlit_app import _load_config
    cfg = _load_config()
    assert isinstance(cfg, dict)
    assert "seed" in cfg


def test_resolve_data_path_known_scenario() -> None:
    from app.streamlit_app import _resolve_data_path, SCENARIOS
    # CubeSat scenario should resolve to existing CSV
    path = _resolve_data_path("CubeSat/LEO (segments_clean)")
    from pathlib import Path
    assert Path(path).exists()


def test_scenario_keys_defined() -> None:
    from app.streamlit_app import SCENARIOS
    assert len(SCENARIOS) >= 3
    assert "CubeSat/LEO (segments_clean)" in SCENARIOS


def test_level_colors_defined() -> None:
    from app.streamlit_app import LEVEL_COLORS
    assert "LOW" in LEVEL_COLORS
    assert "MEDIUM" in LEVEL_COLORS
    assert "CRITICAL" in LEVEL_COLORS
