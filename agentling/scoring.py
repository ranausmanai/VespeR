from __future__ import annotations

import re


SELF_CRITIQUE_RE = re.compile(r"self[-_ ]?critique\s*score\s*[:=]\s*(\d+(?:\.\d+)?)", re.IGNORECASE)


def _keywords(instruction: str) -> list[str]:
    words = [w.strip(".,:;()[]{}\"'`).!?/").lower() for w in instruction.split()]
    words = [w for w in words if len(w) >= 5]
    seen: set[str] = set()
    out: list[str] = []
    for word in words:
        if word not in seen:
            seen.add(word)
            out.append(word)
        if len(out) >= 15:
            break
    return out


def completeness_score(instruction: str, output: str) -> float:
    keys = _keywords(instruction)
    if not keys:
        return 7.0
    lower = output.lower()
    hits = sum(1 for key in keys if key in lower)
    return min(10.0, (hits / len(keys)) * 10)


def logical_consistency_score(output: str) -> float:
    lower = output.lower()
    penalties = 0
    if "todo" in lower and "complete" in lower:
        penalties += 2
    if "cannot" in lower and "implemented" in lower:
        penalties += 2
    if "unknown" in lower and "guaranteed" in lower:
        penalties += 2
    return max(1.0, 10.0 - penalties)


def self_critique_score(output: str) -> float:
    match = SELF_CRITIQUE_RE.search(output)
    if not match:
        return 5.0
    raw = float(match.group(1))
    return max(0.0, min(10.0, raw))


def total_score(instruction: str, output: str, validation_passed: bool) -> float:
    c = completeness_score(instruction, output)
    l = logical_consistency_score(output)
    s = self_critique_score(output)
    weighted = (0.45 * c) + (0.35 * l) + (0.2 * s)
    if not validation_passed:
        weighted *= 0.7
    return round(weighted, 2)
