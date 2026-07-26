"""Optional "workout" mastering pass: punchier beat/bass for gym use.

Applies a bass low-shelf boost followed by a gentle compressor (to make the
beat/kick hit harder and feel louder) and a final peak-safe normalize so the
result never clips.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import lfilter


def apply_workout_master(
    y: np.ndarray,
    sr: int,
    bass_gain_db: float = 6.0,
    bass_cutoff_hz: float = 120.0,
    ratio: float = 3.0,
    makeup_db: float = 4.0,
) -> np.ndarray:
    boosted = _low_shelf(y, sr, cutoff_hz=bass_cutoff_hz, gain_db=bass_gain_db)
    compressed = _compress(boosted, sr, ratio=ratio, makeup_db=makeup_db)
    return _peak_safe_normalize(compressed)


def _low_shelf(y: np.ndarray, sr: int, cutoff_hz: float, gain_db: float) -> np.ndarray:
    """RBJ Audio EQ Cookbook low-shelf biquad; boosts everything below cutoff_hz."""
    a_gain = 10 ** (gain_db / 40)
    w0 = 2 * np.pi * cutoff_hz / sr
    alpha = np.sin(w0) / 2 * np.sqrt((a_gain + 1 / a_gain) + 2)
    cos_w0 = np.cos(w0)
    sqrt_a = np.sqrt(a_gain)

    b0 = a_gain * ((a_gain + 1) - (a_gain - 1) * cos_w0 + 2 * sqrt_a * alpha)
    b1 = 2 * a_gain * ((a_gain - 1) - (a_gain + 1) * cos_w0)
    b2 = a_gain * ((a_gain + 1) - (a_gain - 1) * cos_w0 - 2 * sqrt_a * alpha)
    a0 = (a_gain + 1) + (a_gain - 1) * cos_w0 + 2 * sqrt_a * alpha
    a1 = -2 * ((a_gain - 1) + (a_gain + 1) * cos_w0)
    a2 = (a_gain + 1) + (a_gain - 1) * cos_w0 - 2 * sqrt_a * alpha

    b = np.array([b0, b1, b2]) / a0
    a = np.array([a0, a1, a2]) / a0
    return lfilter(b, a, y, axis=-1)


def _compress(
    y: np.ndarray,
    sr: int,
    threshold_db: float = -18.0,
    ratio: float = 3.0,
    attack_ms: float = 5.0,
    release_ms: float = 80.0,
    makeup_db: float = 4.0,
    hop: int = 64,
) -> np.ndarray:
    """Feed-forward peak compressor with a downsampled envelope follower (fast enough for full tracks)."""
    level = np.max(np.abs(y), axis=0)
    level_ds = level[::hop]
    sr_ds = sr / hop
    attack_coef = np.exp(-1.0 / (sr_ds * attack_ms / 1000))
    release_coef = np.exp(-1.0 / (sr_ds * release_ms / 1000))

    envelope_ds = np.empty_like(level_ds)
    env = 0.0
    for i, lv in enumerate(level_ds):
        coef = attack_coef if lv > env else release_coef
        env = coef * env + (1 - coef) * lv
        envelope_ds[i] = env

    envelope = np.interp(np.arange(len(level)), np.arange(len(level_ds)) * hop, envelope_ds)

    env_db = 20 * np.log10(np.maximum(envelope, 1e-8))
    over_db = env_db - threshold_db
    reduced_db = np.where(over_db > 0, over_db - over_db / ratio, 0.0)
    gain = 10 ** ((-reduced_db) / 20)
    makeup = 10 ** (makeup_db / 20)

    return y * gain[np.newaxis, :] * makeup


def _peak_safe_normalize(y: np.ndarray, target_peak: float = 0.97) -> np.ndarray:
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > target_peak:
        y = y * (target_peak / peak)
    return y
