"""Shared low-level audio DSP helpers used by both beat analysis and mixing."""
from __future__ import annotations

import librosa
import numpy as np


def time_stretch_stereo(y: np.ndarray, rate: float) -> np.ndarray:
    """Speed up (rate > 1) or slow down (rate < 1) stereo audio, preserving pitch."""
    channels = [librosa.effects.time_stretch(y=y[ch], rate=rate) for ch in range(y.shape[0])]
    min_len = min(len(c) for c in channels)
    return np.stack([c[:min_len] for c in channels])


def peak_safe_normalize(y: np.ndarray, target_peak: float = 0.97) -> np.ndarray:
    """Scale down if needed so the peak never exceeds target_peak (no-op if already under).

    Equal-power crossfades can push the overlap region's peak above 0dBFS
    even when both source tracks were individually normalized, since the
    fade curves are power-preserving rather than amplitude-preserving.
    """
    peak = float(np.max(np.abs(y))) if y.size else 0.0
    if peak > target_peak:
        y = y * (target_peak / peak)
    return y
