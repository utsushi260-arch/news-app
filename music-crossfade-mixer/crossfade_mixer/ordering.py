"""Decide the track order automatically so adjacent tempos are as close as possible.

The user supplies tracks in whatever order they happened to type/upload them;
this picks the sequence (a path through all tracks) that minimizes tempo
jumps between consecutive tracks, so the crossfades feel like a continuous
set rather than a random shuffle.
"""
from __future__ import annotations

from itertools import permutations

from .beat_analysis import BeatInfo

# Above this many tracks, brute-forcing every permutation (N!) gets too slow.
BRUTE_FORCE_LIMIT = 8


def order_for_smooth_mix(analyzed: list[BeatInfo]) -> list[int]:
    """Return an index ordering of `analyzed` that minimizes tempo jumps between consecutive tracks."""
    n = len(analyzed)
    if n <= 2:
        return list(range(n))

    tempos = [a.tempo for a in analyzed]
    if n <= BRUTE_FORCE_LIMIT:
        return _brute_force_order(tempos)
    return _greedy_order(tempos)


def _tempo_distance(t1: float, t2: float) -> float:
    # Half-time/double-time tempos (e.g. 90 vs 180 BPM) mix well together,
    # so treat them as close rather than penalizing the raw BPM gap.
    return min(abs(t1 - t2), abs(t1 - t2 * 2), abs(t1 - t2 / 2))


def _path_cost(order: list[int], tempos: list[float]) -> float:
    return sum(
        _tempo_distance(tempos[order[i]], tempos[order[i + 1]])
        for i in range(len(order) - 1)
    )


def _brute_force_order(tempos: list[float]) -> list[int]:
    n = len(tempos)
    best_order = list(range(n))
    best_cost = float("inf")
    for perm in permutations(range(n)):
        cost = _path_cost(perm, tempos)
        if cost < best_cost:
            best_cost = cost
            best_order = list(perm)
    return best_order


def _greedy_order(tempos: list[float]) -> list[int]:
    n = len(tempos)
    best_order = list(range(n))
    best_cost = float("inf")
    for start in range(n):
        visited = [start]
        remaining = set(range(n)) - {start}
        while remaining:
            last = visited[-1]
            nxt = min(remaining, key=lambda i: _tempo_distance(tempos[last], tempos[i]))
            visited.append(nxt)
            remaining.remove(nxt)
        cost = _path_cost(visited, tempos)
        if cost < best_cost:
            best_cost = cost
            best_order = visited
    return best_order
