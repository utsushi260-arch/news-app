"""Shared low-level audio DSP helpers used by both beat analysis and mixing."""
from __future__ import annotations

import librosa
import numpy as np


def time_stretch_stereo(y: np.ndarray, rate: float) -> np.ndarray:
    """Speed up (rate > 1) or slow down (rate < 1) stereo audio, preserving pitch."""
    channels = [librosa.effects.time_stretch(y=y[ch], rate=rate) for ch in range(y.shape[0])]
    min_len = min(len(c) for c in channels)
    return np.stack([c[:min_len] for c in channels])
