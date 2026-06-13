"""Tests for data/preprocessing.py."""

import numpy as np
import pandas as pd
import pytest

from ad_dss.data.preprocessing import (
    clean,
    create_windows,
    interpolate_gaps,
    normalize,
    preprocess_pipeline,
)


def _make_df(n: int = 50, cols: int = 3, nans: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    data = rng.standard_normal((n, cols))
    if nans:
        data[5, 0] = np.nan
        data[10, 1] = np.nan
    idx = pd.date_range("2025-01-01", periods=n, freq="s")
    return pd.DataFrame(data, index=idx, columns=[f"ch{i}" for i in range(cols)])


def test_clean_removes_nans() -> None:
    df = _make_df(nans=True)
    out = clean(df)
    assert not out.isna().any().any()


def test_clean_sorts_index() -> None:
    df = _make_df()
    shuffled = df.sample(frac=1, random_state=0)
    out = clean(shuffled)
    assert out.index.is_monotonic_increasing


def test_clean_drops_all_nan_col() -> None:
    df = _make_df()
    df["all_nan"] = np.nan
    out = clean(df)
    assert "all_nan" not in out.columns


def test_interpolate_gaps() -> None:
    df = _make_df(nans=True)
    out = interpolate_gaps(df)
    assert not out.isna().any().any()


def test_normalize_minmax_range() -> None:
    df = _make_df()
    normed, scaler = normalize(df, method="minmax")
    assert normed.min().min() >= -1e-9
    assert normed.max().max() <= 1 + 1e-9


def test_normalize_standard() -> None:
    df = _make_df()
    normed, scaler = normalize(df, method="standard")
    assert abs(normed.mean().mean()) < 0.1


def test_normalize_reuse_scaler() -> None:
    df_train = _make_df(n=50)
    df_test = _make_df(n=20)
    _, scaler = normalize(df_train, method="minmax")
    normed_test, _ = normalize(df_test, method="minmax", scaler=scaler, fit=False)
    assert normed_test.shape == df_test.shape


def test_create_windows_shape() -> None:
    data = np.ones((100, 3))
    windows = create_windows(data, window_size=10)
    assert windows.shape == (91, 10, 3)


def test_create_windows_too_small() -> None:
    data = np.ones((5, 2))
    with pytest.raises(ValueError):
        create_windows(data, window_size=10)


def test_preprocess_pipeline_end_to_end() -> None:
    df = _make_df(n=80, nans=True)
    windows, normed_df, scaler = preprocess_pipeline(df, window_size=10)
    assert windows.shape[1] == 10
    assert windows.shape[2] == normed_df.shape[1]
    assert not normed_df.isna().any().any()
