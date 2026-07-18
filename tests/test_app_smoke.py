"""Headless smoke tests for the Streamlit app (import + logic only)."""


def test_app_imports() -> None:
    """App module and key functions import without error."""


def test_load_config_returns_dict() -> None:
    from app.streamlit_app import _load_config

    cfg = _load_config()
    assert isinstance(cfg, dict)
    assert "seed" in cfg


def test_resolve_data_path_known_scenario() -> None:
    from pathlib import Path

    from app.streamlit_app import _resolve_data_path

    # Data files are gitignored runtime artifacts; verify stable path mapping only.
    path = _resolve_data_path("CubeSat/LEO (segments_clean)")
    assert Path(path).as_posix() == "data/raw/segments_clean.csv"


def test_scenario_keys_defined() -> None:
    from app.streamlit_app import SCENARIOS

    assert len(SCENARIOS) >= 3
    assert "CubeSat/LEO (segments_clean)" in SCENARIOS


def test_level_colors_defined() -> None:
    from app.streamlit_app import LEVEL_COLORS

    assert "LOW" in LEVEL_COLORS
    assert "MEDIUM" in LEVEL_COLORS
    assert "CRITICAL" in LEVEL_COLORS
