"""Recorder-side passive TCP RTT; never a latency measurement for other players."""
from __future__ import annotations
import math

def clean(samples, duration, limit=20000):
    if not isinstance(samples, list):
        return []
    result = []
    for row in samples[:limit]:
        if (isinstance(row, list) and len(row) == 2 and
                all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in row) and
                0 <= row[0] <= duration and 0 <= row[1] <= 60000):
            result.append([float(row[0]), float(row[1])])
    return sorted(result, key=lambda row: row[0])

def summarize(samples):
    if not samples:
        return None
    values = [row[1] for row in samples]
    return {"avg": round(sum(values)/len(values), 2), "min": min(values), "max": max(values),
            "samples": len(values), "current": samples[-1][1]}
