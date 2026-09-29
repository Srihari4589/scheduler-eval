"""Measure agreement between the LLM judge and human labels.

Usage:
    python scripts/measure_agreement.py human_labels.json

Reads a JSON file mapping case_id → "good"/"bad" (exported from the review tool)
and compares against the LLM judge's labels from the latest run report.

Outputs precision, recall, F1, and raw agreement — following Hamel's guidance
to use precision/recall, not raw agreement.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "runs"


def load_human_labels(path: str | Path) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {str(k): v.lower() for k, v in data.items()}


def load_judge_labels() -> dict[str, bool]:
    files = sorted(ARTIFACTS_DIR.glob("*.json"))
    if not files:
        raise RuntimeError("No run files found. Run the benchmark with --judge first.")
    latest = json.loads(files[-1].read_text(encoding="utf-8"))
    labels = {}
    for case in latest.get("cases", []):
        if case.get("error"):
            continue
        report = case.get("report", {})
        if "judge_good" in report:
            labels[case["case_id"]] = report["judge_good"]
    return labels


def compute_metrics(human: dict[str, str], judge: dict[str, bool]) -> dict:
    tp = fp = tn = fn = 0
    for case_id, human_label in human.items():
        if case_id not in judge:
            continue
        judge_good = judge[case_id]
        human_good = human_label == "good"
        if human_good and judge_good:
            tp += 1
        elif not human_good and judge_good:
            fp += 1
        elif not human_good and not judge_good:
            tn += 1
        elif human_good and not judge_good:
            fn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    agreement = (tp + tn) / len(human) if human else 0.0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "true_negatives": tn,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "raw_agreement": agreement,
        "total_labeled": len(human),
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/measure_agreement.py human_labels.json")
        sys.exit(1)

    human = load_human_labels(sys.argv[1])
    judge = load_judge_labels()

    common = set(human.keys()) & set(judge.keys())
    if not common:
        print("No overlapping case IDs between human labels and judge labels.")
        print(f"Human labels: {list(human.keys())}")
        print(f"Judge labels: {list(judge.keys())}")
        sys.exit(1)

    metrics = compute_metrics(human, judge)

    print(f"\n=== LLM Judge vs Human Labels ===")
    print(f"Cases compared: {len(common)}")
    print(f"True positives:  {metrics['true_positives']}")
    print(f"False positives: {metrics['false_positives']}")
    print(f"True negatives:  {metrics['true_negatives']}")
    print(f"False negatives: {metrics['false_negatives']}")
    print(f"\nPrecision: {metrics['precision']:.2%}")
    print(f"Recall:    {metrics['recall']:.2%}")
    print(f"F1:        {metrics['f1']:.2%}")
    print(f"Agreement: {metrics['raw_agreement']:.2%}")

    if metrics["precision"] < 0.8 or metrics["recall"] < 0.8:
        print("\nJudge needs calibration. Iterate on the judge prompt to improve alignment.")
    else:
        print("\nJudge is well-aligned with human judgment.")


if __name__ == "__main__":
    main()
