"""BPM-synced crossfade mixing of a sequence of analyzed tracks."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .beat_analysis import BeatInfo
from .dsp import peak_safe_normalize, time_stretch_stereo

# Short and beat-synced reads as a clean cut rather than an audible "two
# songs playing at once" blend; combined with skipping quiet intros/outros
# (see beat_analysis._energetic_bounds) this is what makes the switch hard
# to pinpoint by ear. Not exposed to end users since there's no "wrong"
# tempo they could pick to make these better.
DEFAULT_CROSSFADE_SECONDS = 1.5
DEFAULT_MAX_STRETCH = 0.08


@dataclass
class MixState:
    y: np.ndarray  # stereo audio so far, shape (2, n_samples)
    tempo: float  # reference tempo the mix is currently locked to
    beat_times: np.ndarray  # beat times (seconds) within the mix so far
    outro_trim: float  # quiet-outro seconds to cut away from the current tail before the next join


def mix_tracks(
    analyzed: list[BeatInfo],
    crossfade_seconds: float = DEFAULT_CROSSFADE_SECONDS,
    max_stretch: float = DEFAULT_MAX_STRETCH,
) -> tuple[np.ndarray, int]:
    """Crossfade a list of analyzed tracks into a single stereo mix.

    Each subsequent track has its tempo nudged toward the first track's
    tempo (clamped to `max_stretch`) so the crossfade region lines up on
    the beat instead of just fading blindly.
    """
    if not analyzed:
        raise ValueError("mix対象のトラックがありません")

    sr = analyzed[0].sr
    current = MixState(
        y=analyzed[0].y,
        tempo=analyzed[0].tempo,
        beat_times=analyzed[0].beat_times,
        outro_trim=analyzed[0].outro_trim,
    )

    for nxt in analyzed[1:]:
        current = _crossfade_pair(current, nxt, crossfade_seconds, max_stretch, sr)

    # Equal-power crossfades can push the overlap region above 0dBFS even
    # when the source tracks were individually normalized, so guard against
    # clipping here regardless of whether workout mastering runs afterward.
    return peak_safe_normalize(current.y), sr


def _crossfade_pair(
    current: MixState,
    nxt: BeatInfo,
    crossfade_dur: float,
    max_stretch: float,
    sr: int,
) -> MixState:
    rate = _clamped_rate(current.tempo, nxt.tempo, max_stretch)
    if abs(rate - 1.0) > 1e-3:
        stretched_y = time_stretch_stereo(nxt.y, rate)
        stretched_beats = nxt.beat_times / rate
        intro_skip = nxt.intro_skip / rate
    else:
        stretched_y = nxt.y
        stretched_beats = nxt.beat_times
        intro_skip = nxt.intro_skip

    cur_duration = current.y.shape[1] / sr
    target_outro = max(0.0, cur_duration - crossfade_dur - current.outro_trim)
    outro_start = _nearest_beat(current.beat_times, target_outro)

    # Join on the first beat once the incoming track has properly kicked in,
    # not just its first detected beat - that's usually still inside a quiet
    # intro, which would make the switch obvious instead of hiding it.
    past_intro = stretched_beats[stretched_beats >= intro_skip]
    if len(past_intro):
        intro_offset = float(past_intro[0])
    elif len(stretched_beats):
        intro_offset = float(stretched_beats[0])
    else:
        intro_offset = intro_skip

    outro_start_sample = int(outro_start * sr)
    intro_offset_sample = int(intro_offset * sr)

    tail_current_samples = current.y.shape[1] - outro_start_sample
    remaining_next_samples = stretched_y.shape[1] - intro_offset_sample
    overlap_samples = max(1, min(tail_current_samples, remaining_next_samples, int(crossfade_dur * sr)))

    head = current.y[:, :outro_start_sample]
    overlap_a = current.y[:, outro_start_sample:outro_start_sample + overlap_samples]
    overlap_b = stretched_y[:, intro_offset_sample:intro_offset_sample + overlap_samples]
    tail_b = stretched_y[:, intro_offset_sample + overlap_samples:]

    # equal-power crossfade curve so the perceived volume stays constant through the overlap
    t = np.linspace(0, np.pi / 2, overlap_samples)
    fade_out = np.cos(t)
    fade_in = np.sin(t)
    mixed_overlap = overlap_a * fade_out + overlap_b * fade_in

    new_y = np.concatenate([head, mixed_overlap, tail_b], axis=1)

    shift = outro_start - intro_offset
    kept_beats = current.beat_times[current.beat_times < outro_start]
    shifted_next_beats = stretched_beats + shift
    new_duration = new_y.shape[1] / sr
    new_beats = np.concatenate([kept_beats, shifted_next_beats])
    new_beats = np.sort(new_beats[(new_beats >= 0) & (new_beats < new_duration)])

    return MixState(y=new_y, tempo=current.tempo, beat_times=new_beats, outro_trim=nxt.outro_trim)


def _clamped_rate(ref_tempo: float, track_tempo: float, max_stretch: float) -> float:
    if track_tempo <= 0:
        return 1.0
    raw_rate = ref_tempo / track_tempo
    lo, hi = 1.0 - max_stretch, 1.0 + max_stretch
    return float(np.clip(raw_rate, lo, hi))


def _nearest_beat(beat_times: np.ndarray, t: float) -> float:
    if len(beat_times) == 0:
        return t
    idx = int(np.argmin(np.abs(beat_times - t)))
    return float(beat_times[idx])
