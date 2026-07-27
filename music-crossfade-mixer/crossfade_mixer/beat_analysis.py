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
    intro_skip: float = 0.0  # seconds of quiet build-up at the start it's safe to cut into
    outro_trim: float = 0.0  # seconds of quiet fade-out at the end it's safe to cut off

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

    intro_skip, outro_trim = _energetic_bounds(y_mono, sr)

    return BeatInfo(y=y, sr=sr, tempo=tempo, beat_times=beat_times, intro_skip=intro_skip, outro_trim=outro_trim)


# How long a stretch of the track needs to stay loud before we trust it as
# "the track has properly kicked in" rather than a stray transient.
_SUSTAIN_SECONDS = 2.0
# Never skip/trim more than this much, even for a very long intro/outro -
# a wrong guess should degrade gracefully, not eat half the song.
_MAX_TRIM_SECONDS = 45.0


def _energetic_bounds(y_mono: np.ndarray, sr: int) -> tuple[float, float]:
    """Estimate how much quiet build-up/fade-out sits at the head/tail of a track.

    Used to let mix transitions cut straight into the "full" part of a track
    (skipping a quiet intro) or cut away before a quiet outro, instead of
    always joining at the literal first/last sample.
    """
    hop = 512
    rms = librosa.feature.rms(y=y_mono, frame_length=2048, hop_length=hop)[0]
    if len(rms) == 0:
        return 0.0, 0.0

    frame_times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
    duration = float(frame_times[-1]) if len(frame_times) else 0.0
    if duration <= 0:
        return 0.0, 0.0

    threshold = np.percentile(rms, 85) * 0.5
    sustain_frames = max(1, int(round(_SUSTAIN_SECONDS * sr / hop)))
    max_trim = min(_MAX_TRIM_SECONDS, duration * 0.3)

    intro_skip = 0.0
    run = 0
    for i, v in enumerate(rms):
        run = run + 1 if v >= threshold else 0
        if run >= sustain_frames:
            intro_skip = float(min(max_trim, frame_times[i - sustain_frames + 1]))
            break

    outro_trim = 0.0
    run = 0
    for i in range(len(rms) - 1, -1, -1):
        run = run + 1 if rms[i] >= threshold else 0
        if run >= sustain_frames:
            boundary = min(i + sustain_frames - 1, len(frame_times) - 1)
            outro_trim = float(max(0.0, min(max_trim, duration - frame_times[boundary])))
            break

    return intro_skip, outro_trim
