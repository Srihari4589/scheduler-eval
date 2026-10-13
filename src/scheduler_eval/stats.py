"""Small statistics helpers: bootstrap confidence intervals and per-dimension gating.

Plain Python, no AI, no numpy. Seeded so the same inputs always give the same interval.
"""

from __future__ import annotations

import random

# A "dimension" is one separately-scored thing a run can fail at. These are the keys in a
# case report that are 0..1 scores where 1.0 means pass. preference_score is a soft score,
# so it is reported but never gates a case.
HARD_DIMENSIONS = ("hard_pass", "regression_score")
NON_DIMENSION_KEYS = {
    "hard_violations", "regression_violations", "preference_score", "correction_exercised",
    "judge_good", "judge_critique", "judge_scores",
}
PASS_THRESHOLD = 1.0


def bootstrap_ci(
    values: list[float], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float, float] | None:
    """Percentile bootstrap CI for the mean. Returns (low, mean, high), or None if empty.

    With a single value (or all-equal values) the interval collapses to that value; that is
    honest about what we know, but it is NOT evidence of low variance - check n.
    """
    if not values:
        return None
    rng = random.Random(seed)
    n = len(values)
    means = sorted(sum(rng.choices(values, k=n)) / n for _ in range(n_boot))
    lo = means[int((alpha / 2) * n_boot)]
    hi = means[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return lo, sum(values) / n, hi


def dimension_scores(report: dict) -> dict[str, float]:
    """Every pass/fail dimension present in one case report (hard rules, regression,
    and each correction_* compliance check)."""
    return {
        k: float(v)
        for k, v in report.items()
        if k not in NON_DIMENSION_KEYS and isinstance(v, (int, float)) and not isinstance(v, bool)
    }


def case_gate(report: dict) -> dict:
    """Strict per-case verdict: passes only if EVERY dimension is at 1.0.

    Returns the failing dimensions by name, so one bad dimension cannot hide inside an
    average. A correction that was never exercised is flagged, not silently counted.
    """
    dims = dimension_scores(report)
    failed = sorted(k for k, v in dims.items() if v < PASS_THRESHOLD)
    return {
        "dimensions": dims,
        "failed_dimensions": failed,
        "strict_pass": not failed,
        "weakest_dimension": min(dims, key=dims.get) if dims else None,
        "correction_not_exercised": report.get("correction_exercised") == 0.0,
    }


def per_dimension_summary(case_reports: list[dict]) -> dict:
    """Across cases: for each dimension, pass rate and the cases that failed it, plus the
    overall strict pass rate (a case passes only if all its dimensions pass)."""
    gates = [case_gate(r) for r in case_reports]
    names = sorted({d for g in gates for d in g["dimensions"]})
    out: dict = {"dimensions": {}, "n_cases": len(case_reports)}
    for name in names:
        vals = [g["dimensions"][name] for g in gates if name in g["dimensions"]]
        out["dimensions"][name] = {
            "n": len(vals),
            "pass_rate": sum(1 for v in vals if v >= PASS_THRESHOLD) / len(vals),
            "min": min(vals),
        }
    out["strict_pass_rate"] = (
        sum(1 for g in gates if g["strict_pass"]) / len(gates) if gates else None
    )
    out["not_exercised_cases"] = sum(1 for g in gates if g["correction_not_exercised"])
    if out["dimensions"]:
        worst = min(out["dimensions"], key=lambda k: out["dimensions"][k]["pass_rate"])
        out["weakest_dimension"] = worst
    else:
        out["weakest_dimension"] = None
    return out
