"""Rolling-baseline anomaly detection on per-bucket counts (no labels needed).

Each bucket is compared with the mean/std of the buckets before it (EWMA-style, causal:
a bucket never sees its own future), so the detector works identically in replay and live.
"""
import math
from collections import defaultdict


def rate_anomalies(times_by_key: dict[str, list[float]], bucket_s: int, min_history: int, z_threshold: float,
                   start_t: float | None = None, end_t: float | None = None):
    """Yield (key, bucket_start, count, z) for buckets whose count deviates from the causal baseline."""
    for key, times in times_by_key.items():
        if not times:
            continue
        lo = start_t if start_t is not None else min(times)
        hi = end_t if end_t is not None else max(times)
        n_buckets = max(1, math.ceil((hi - lo) / bucket_s))   # last bucket ends at `hi`, never after
        counts = [0] * n_buckets
        for t in times:
            i = int((t - lo) // bucket_s)
            if 0 <= i < n_buckets:
                counts[i] += 1
        history: list[int] = []
        for i, c in enumerate(counts):
            if len(history) >= min_history:
                mean = sum(history) / len(history)
                var = sum((h - mean) ** 2 for h in history) / len(history)
                std = max(math.sqrt(var), 1.0)   # floor avoids huge z on near-constant baselines
                z = (c - mean) / std
                if abs(z) >= z_threshold:
                    yield key, lo + i * bucket_s, c, z
            history.append(c)


def group_times(pairs) -> dict[str, list[float]]:
    out: dict[str, list[float]] = defaultdict(list)
    for key, t in pairs:
        out[key].append(t)
    return out
