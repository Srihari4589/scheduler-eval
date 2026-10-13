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


def cluster_bootstrap_ci(
    clusters: dict[str, list[float]], n_boot: int = 2000, alpha: float = 0.05, seed: int = 0
) -> tuple[float, float, float] | None:
    """Two-stage percentile bootstrap CI for a mean, treating each scenario as a cluster.

    Stage 1 resamples scenarios with replacement; stage 2 resamples the repeats inside each
    drawn scenario. So the interval reflects BOTH run-to-run noise and the fact that we only
    tried a handful of scenarios. Returns (low, mean, high), where mean gives each scenario
    equal weight, or None if there is no data.

    Caveat: with ~6 scenarios the interval is wide on purpose, and it says nothing about
    whether those scenarios represent all schedules a user might ask for.
    """
    clusters = {k: v for k, v in clusters.items() if v}
    if not clusters:
        return None
    rng = random.Random(seed)
    keys = list(clusters)
    k = len(keys)
    stats = []
    for _ in range(n_boot):
        total = 0.0
        for key in rng.choices(keys, k=k):
            vals = clusters[key]
            total += sum(rng.choices(vals, k=len(vals))) / len(vals)
        stats.append(total / k)
    stats.sort()
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    point = sum(sum(v) / len(v) for v in clusters.values()) / k
    return lo, point, hi


def case_metric_table(runs: list[list[dict]]) -> dict[str, dict[str, list[float]]]:
    """Regroup repeated runs as {metric: {scenario_id: [value per repeat]}}.

    `runs` is one list of case dicts ({"case_id", "error", "report"}) per repeat. Errored
    cases are skipped, so a scenario can have fewer values than there were repeats.
    Metrics: every pass/fail dimension, preference_score, and strict_pass (all dimensions).
    """
    table: dict[str, dict[str, list[float]]] = {}
    for cases in runs:
        for c in cases:
            if c.get("error") or not c.get("report"):
                continue
            report = c["report"]
            values = dict(dimension_scores(report))
            if isinstance(report.get("preference_score"), (int, float)):
                values["preference_score"] = float(report["preference_score"])
            values["strict_pass"] = 1.0 if case_gate(report)["strict_pass"] else 0.0
            for name, v in values.items():
                table.setdefault(name, {}).setdefault(c["case_id"], []).append(v)
    return table


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
