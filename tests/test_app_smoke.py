"""Headless smoke tests for the Streamlit app (import + logic only)."""


def test_app_imports() -> None:
    """App module and key functions import without error."""


def test_load_config_returns_dict() -> None:
    from app.streamlit_app import _load_config

    cfg = _load_config()
    assert isinstance(cfg, dict)
    assert "seed" in cfg


def test_resolve_data_path_known_scenario() -> None:
    from app.streamlit_app import _resolve_data_path

    path = _resolve_data_path("ESA Mission 1")
    from pathlib import Path

    assert Path(path).exists()


def test_scenario_keys_defined() -> None:
    from app.streamlit_app import SCENARIOS

    assert len(SCENARIOS) >= 3
    assert "ESA Mission 1" in SCENARIOS


def test_level_colors_defined() -> None:
    from app.streamlit_app import LEVEL_COLORS

    assert "LOW" in LEVEL_COLORS
    assert "MEDIUM" in LEVEL_COLORS
    assert "CRITICAL" in LEVEL_COLORS
