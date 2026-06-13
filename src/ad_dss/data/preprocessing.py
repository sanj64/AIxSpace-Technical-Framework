"""Data preprocessing: clean, interpolate, normalize, window."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler, StandardScaler

from ad_dss.common.logging_config import get_logger

logger = get_logger(__name__)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    """Fill gaps (ffill then bfill), sort by index, drop all-NaN columns."""
    df = df.copy()
    df = df.select_dtypes(include="number")  # keep numeric only
    df = df.ffill().bfill()
    df = df.sort_index()
    all_nan = df.columns[df.isna().all()]
    if len(all_nan):
        logger.warning("Dropping all-NaN columns: %s", list(all_nan))
        df = df.drop(columns=all_nan)
    logger.info("clean(): shape after cleaning = %s", df.shape)
    return df


def interpolate_gaps(df: pd.DataFrame, method: str = "linear") -> pd.DataFrame:
    """Interpolate remaining NaN values along the time axis."""
    return df.interpolate(method=method, axis=0).ffill().bfill()  # type: ignore[arg-type]


def normalize(
    df: pd.DataFrame,
    method: str = "minmax",
    scaler: Any = None,
    fit: bool = True,
) -> tuple[pd.DataFrame, Any]:
    """Normalize DataFrame columns. Returns (normalized_df, fitted_scaler).

    Pass `scaler` and `fit=False` to apply a pre-fitted scaler (e.g., on test data).
    """
    if scaler is None:
        scaler = MinMaxScaler() if method == "minmax" else StandardScaler()

    values = df.values
    if fit:
        scaled = scaler.fit_transform(values)
    else:
        scaled = scaler.transform(values)

    result = pd.DataFrame(scaled, index=df.index, columns=df.columns)
    return result, scaler


def create_windows(data: np.ndarray, window_size: int) -> np.ndarray:
    """Create overlapping sliding windows from 2-D array (samples × features).

    Returns array of shape (n_windows, window_size, n_features).
    """
    if data.ndim == 1:
        data = data.reshape(-1, 1)
    n_samples, n_features = data.shape
    n_windows = n_samples - window_size + 1
    if n_windows <= 0:
        raise ValueError(f"Not enough samples ({n_samples}) for window_size={window_size}")
    windows = np.lib.stride_tricks.sliding_window_view(data, (window_size, n_features))
    return windows.reshape(-1, window_size, n_features)


def preprocess_pipeline(
    df: pd.DataFrame,
    window_size: int = 30,
    normalization: str = "minmax",
) -> tuple[np.ndarray, pd.DataFrame, Any]:
    """Run the full preprocessing pipeline: clean → normalize → window.

    Returns (windows, cleaned_normalized_df, scaler).
    """
    cleaned = clean(df)
    normalized, scaler = normalize(cleaned, method=normalization)
    windows = create_windows(normalized.values, window_size)
    logger.info(
        "preprocess_pipeline(): windows=%s, scaler=%s",
        windows.shape,
        type(scaler).__name__,
    )
    return windows, normalized, scaler
