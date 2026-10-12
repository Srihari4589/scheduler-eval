"""Export labels in the team's shared JSONL format (see docs/WHAT_GOOD_MEANS.md).

Usage:
    python scripts/export_labels.py --rater srihari --human human_labels.json
    python scripts/export_labels.py                       # grader/judge rows only

Reads the latest run in artifacts/runs/ and writes artifacts/labels/<run_id>.<rater>.jsonl
with one row per (case, rater, dimension):

* grader rows: quant (hard_pass) and implicit (correction applied and no regression)
* judge rows:  qual (only if the run was made with --judge)
* human rows:  overall good/bad from the review tool, if --human is given
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = ROOT / "artifacts" / "runs"
LABELS_DIR = ROOT / "artifacts" / "labels"

COMPLIANCE_PREFIXES = ("added_", "removed_", "new_blocked_", "attendee_moved_")


def _label(ok: bool) -> str:
    return "pass" if ok else "fail"


def implicit_label(report: dict) -> tuple[str, str]:
    """Return (label, note) for the implicit dimension of one case report."""
    if "regression_score" not in report:
        return "na", "no correction in this scenario"
    if report.get("correction_exercised", 1.0) == 0.0:
        return "na", "turn-1 schedule never conflicted with the correction"
    compliance = [v for k, v in report.items() if k.startswith(COMPLIANCE_PREFIXES)]
    applied = all(v >= 1.0 for v in compliance)
    no_regression = report["regression_score"] >= 1.0
    notes = []
    if not applied:
        notes.append("correction not applied")
    if not no_regression:
        notes.append("broke earlier constraints")
    return _label(applied and no_regression), "; ".join(notes)


def build_rows(run: dict, run_id: str, rater: str | None, human: dict[str, str] | None) -> list[dict]:
    rows: list[dict] = []

    def add(case_id, who, dimension, label, note, source):
        rows.append(
            {
                "task": "scheduler",
                "run_id": run_id,
                "case_id": case_id,
                "rater": who,
                "dimension": dimension,
                "label": label,
                "note": note,
                "source": source,
            }
        )

    for case in run.get("cases", []):
        if case.get("error"):
            continue
        cid = case["case_id"]
        report = case.get("report", {})
        violations = report.get("hard_violations", [])
        add(cid, "grader", "quant", _label(report.get("hard_pass", 0.0) >= 1.0),
            "; ".join(violations[:3]), "grader")
        label, note = implicit_label(report)
        add(cid, "grader", "implicit", label, note, "grader")
        if "judge_good" in report:
            add(cid, "llm_judge", "qual", _label(report["judge_good"]), "", "judge")

    if human:
        if not rater:
            raise SystemExit("--human requires --rater")
        known = {c["case_id"] for c in run.get("cases", [])}
        for cid, verdict in human.items():
            if cid not in known:
                continue
            add(cid, rater, "overall", _label(verdict.lower() == "good"), "", "human")
    return rows


def latest_run() -> tuple[dict, str]:
    files = sorted(RUNS_DIR.glob("*.json"))
    if not files:
        raise SystemExit("No run files in artifacts/runs/. Run `scheduler-eval` first.")
    return json.loads(files[-1].read_text(encoding="utf-8")), files[-1].stem


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--rater", help="your name, used as the rater id for human rows")
    ap.add_argument("--human", help="human_labels.json exported from the review tool")
    args = ap.parse_args()

    run, run_id = latest_run()
    human = None
    if args.human:
        human = {str(k): v for k, v in json.loads(Path(args.human).read_text(encoding="utf-8")).items()}
    rows = build_rows(run, run_id, args.rater, human)

    LABELS_DIR.mkdir(parents=True, exist_ok=True)
    out = LABELS_DIR / f"{run_id}.{args.rater or 'auto'}.jsonl"
    out.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    print(f"Wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
