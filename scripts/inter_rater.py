"""Inter-rater agreement (Cohen's kappa) from shared-format label files.

Usage:
    python scripts/inter_rater.py labels_srihari.jsonl labels_aayush.jsonl labels_moulik.jsonl
    python scripts/inter_rater.py artifacts/labels/*.jsonl --dimension overall

Only rows with label pass/fail are compared (`na` is skipped). Raters are paired on
(task, case_id, dimension). Prints raw agreement AND kappa, because raw agreement
alone looks good when most labels are the same class.
"""

from __future__ import annotations

import argparse
import itertools
import json
from collections import defaultdict
from pathlib import Path


def load_rows(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def cohens_kappa(a: list[str], b: list[str]) -> float | None:
    """Cohen's kappa for two equal-length label lists. None if undefined."""
    n = len(a)
    if n == 0:
        return None
    observed = sum(x == y for x, y in zip(a, b)) / n
    classes = set(a) | set(b)
    expected = sum((a.count(c) / n) * (b.count(c) / n) for c in classes)
    if expected == 1.0:
        return None  # everyone used one class; kappa is undefined
    return (observed - expected) / (1 - expected)


def pairwise(rows: list[dict], dimension: str, human_only: bool = True) -> list[dict]:
    by_rater: dict[str, dict[tuple, str]] = defaultdict(dict)
    for r in rows:
        if r["dimension"] != dimension or r["label"] not in ("pass", "fail"):
            continue
        if human_only and r.get("source") != "human":
            continue
        by_rater[r["rater"]][(r["task"], r["case_id"])] = r["label"]

    results = []
    for r1, r2 in itertools.combinations(sorted(by_rater), 2):
        shared = sorted(set(by_rater[r1]) & set(by_rater[r2]))
        a = [by_rater[r1][k] for k in shared]
        b = [by_rater[r2][k] for k in shared]
        agree = sum(x == y for x, y in zip(a, b)) / len(shared) if shared else None
        results.append(
            {"raters": (r1, r2), "n": len(shared), "raw_agreement": agree, "kappa": cohens_kappa(a, b)}
        )
    return results


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--dimension", default="overall")
    ap.add_argument("--include-machine", action="store_true", help="also compare grader/judge raters")
    args = ap.parse_args()

    rows = load_rows(args.files)
    results = pairwise(rows, args.dimension, human_only=not args.include_machine)
    if not results:
        print(f"No rater pairs found for dimension '{args.dimension}'. Need 2+ raters on shared cases.")
        return
    print(f"\n=== Inter-rater agreement: {args.dimension} ===")
    for r in results:
        k = "undefined" if r["kappa"] is None else f"{r['kappa']:.2f}"
        raw = "n/a" if r["raw_agreement"] is None else f"{r['raw_agreement']:.0%}"
        print(f"{r['raters'][0]} vs {r['raters'][1]}: n={r['n']}  raw={raw}  kappa={k}")
    print("\nRule of thumb: kappa < 0.4 weak, 0.4-0.6 moderate, 0.6-0.8 good, > 0.8 strong.")
    print("Low kappa means the rubric is unclear. Revise docs/WHAT_GOOD_MEANS.md, then relabel.")


if __name__ == "__main__":
    main()
