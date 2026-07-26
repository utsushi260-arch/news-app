"""Tempo/beat analysis backed by librosa."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from .dsp import time_stretch_stereo


@dataclass
class BeatInfo:
    y: np.ndarray  # stereo audio, shape (2, n_samples)
    sr: int
    tempo: float
    beat_times: np.ndarray  # seconds, sorted

    @property
    def duration(self) -> float:
        return self.y.shape[1] / self.sr


def analyze(path: Path, speed: float = 1.0) -> BeatInfo:
    """Load, optionally time-stretch by `speed` (pitch preserved), and detect tempo/beats."""
    y, sr = librosa.load(str(path), sr=44100, mono=False)
    if y.ndim == 1:
        y = np.stack([y, y])

    if speed != 1.0:
        y = time_stretch_stereo(y, speed)

    y_mono = librosa.to_mono(y)
    tempo, beat_frames = librosa.beat.beat_track(y=y_mono, sr=sr, units="frames")
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    tempo = float(np.atleast_1d(tempo)[0])
    if tempo <= 0:
        tempo = 120.0

    return BeatInfo(y=y, sr=sr, tempo=tempo, beat_times=beat_times)
