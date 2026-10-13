"""Per-dimension agreement between automated raters (grader, LLM judge) and humans.

Usage:
    python scripts/dimension_agreement.py artifacts/labels/*.jsonl
    python scripts/dimension_agreement.py artifacts/labels/*.jsonl --min-n 20

Input is the shared label format (see docs/WHAT_GOOD_MEANS.md). For each dimension
(quant, qual, implicit, overall) it compares every machine rater to the HUMAN CONSENSUS
(majority of human raters; ties are skipped and counted) and prints a confusion matrix.

The question answered is "when the machine says FAIL, is it right (precision), and how many
of the human-FAIL cases does it catch (recall)?" so `fail` is the positive class. Averaging
all dimensions into one number would hide a dimension where the machine is weak, which is
exactly what this report is for.

`overall` for a machine rater is derived: fail if any of its dimensions fail, pass if all
non-na ones pass. Rows labeled `na` are skipped. Humans currently label `overall` only, so
quant/qual/implicit rows appear here only after humans label those dimensions separately.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

DIMENSIONS = ("quant", "qual", "implicit", "overall")
MACHINE_SOURCES = ("grader", "judge")


def load_rows(paths: list[str]) -> list[dict]:
    rows = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                rows.append(json.loads(line))
    return rows


def human_consensus(rows: list[dict], dimension: str) -> tuple[dict[tuple, str], int]:
    """{(task, case_id): label} by majority vote of human raters, plus the number of ties."""
    votes: dict[tuple, list[str]] = defaultdict(list)
    for r in rows:
        if r.get("source") == "human" and r["dimension"] == dimension and r["label"] in ("pass", "fail"):
            votes[(r["task"], r["case_id"])].append(r["label"])
    consensus, ties = {}, 0
    for key, labels in votes.items():
        top = Counter(labels).most_common()
        if len(top) > 1 and top[0][1] == top[1][1]:
            ties += 1
            continue
        consensus[key] = top[0][0]
    return consensus, ties


def machine_labels(rows: list[dict], dimension: str) -> dict[str, dict[tuple, str]]:
    """{rater: {(task, case_id): label}} for machine raters on one dimension."""
    out: dict[str, dict[tuple, str]] = defaultdict(dict)
    if dimension != "overall":
        for r in rows:
            if r.get("source") in MACHINE_SOURCES and r["dimension"] == dimension and r["label"] in ("pass", "fail"):
                out[r["rater"]][(r["task"], r["case_id"])] = r["label"]
        return dict(out)
    per_case: dict[tuple, dict[tuple, list[str]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if r.get("source") in MACHINE_SOURCES and r["dimension"] != "overall" and r["label"] in ("pass", "fail"):
            per_case[r["rater"]][(r["task"], r["case_id"])].append(r["label"])
    for rater, cases in per_case.items():
        for key, labels in cases.items():
            out[rater][key] = "fail" if "fail" in labels else "pass"
    return dict(out)


def confusion(machine: dict[tuple, str], human: dict[tuple, str]) -> dict:
    """Confusion counts with `fail` as the positive class (detecting bad runs)."""
    tp = fp = tn = fn = 0
    for key in set(machine) & set(human):
        m, h = machine[key] == "fail", human[key] == "fail"
        tp += m and h
        fp += m and not h
        tn += (not m) and (not h)
        fn += (not m) and h
    n = tp + fp + tn + fn
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * precision * recall / (precision + recall)) if precision and recall else None
    return {
        "n": n, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "precision": precision, "recall": recall, "f1": f1,
        "raw_agreement": (tp + tn) / n if n else None,
        "human_fail": tp + fn,
    }


def report(rows: list[dict], min_n: int = 20) -> list[dict]:
    results = []
    for dim in DIMENSIONS:
        human, ties = human_consensus(rows, dim)
        if not human:
            continue
        for rater, labels in sorted(machine_labels(rows, dim).items()):
            c = confusion(labels, human)
            if c["n"] == 0:
                continue
            results.append({"dimension": dim, "rater": rater, "ties": ties, "small": c["n"] < min_n, **c})
    return results


def _pct(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.0%}"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("files", nargs="+")
    ap.add_argument("--min-n", type=int, default=20, help="warn when a dimension has fewer cases")
    args = ap.parse_args()

    results = report(load_rows(args.files), args.min_n)
    if not results:
        print("No machine-vs-human pairs found. Need human labels (source=human) and grader/judge")
        print("rows on the same cases. Run scripts/export_labels.py with --rater and --human first.")
        return
    print("\n=== Machine vs human consensus, per dimension (positive class = fail) ===")
    for r in results:
        print(f"\n[{r['dimension']}] {r['rater']}   n={r['n']}  human-fail={r['human_fail']}")
        print(f"            machine fail   machine pass")
        print(f"  human fail   {r['tp']:>6}         {r['fn']:>6}")
        print(f"  human pass   {r['fp']:>6}         {r['tn']:>6}")
        print(f"  precision={_pct(r['precision'])}  recall={_pct(r['recall'])}  "
              f"f1={_pct(r['f1'])}  raw agreement={_pct(r['raw_agreement'])}")
        if r["small"]:
            print(f"  WARNING: only {r['n']} cases (< {args.min_n}); treat these numbers as rough.")
        if r["human_fail"] == 0:
            print("  WARNING: humans labeled no failures here, so recall is undefined and "
                  "precision only shows false alarms.")
        if r["ties"]:
            print(f"  note: {r['ties']} case(s) skipped because human raters tied.")
    weak = [r for r in results if r["recall"] is not None and r["recall"] < 0.8]
    if weak:
        print("\nWeak spots (recall < 80%): " + ", ".join(f"{r['rater']}/{r['dimension']}" for r in weak))


if __name__ == "__main__":
    main()
