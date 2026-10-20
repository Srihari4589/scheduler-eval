"""Test a judge against schedules with KNOWN defects (injected by us).

    python scripts/evaluate_judge.py --judge stubborn          # negative control, recall must be ~0
    python scripts/evaluate_judge.py --judge gemini            # needs GEMINI_API_KEY
    python scripts/evaluate_judge.py --judge openai --judge-model <id>   # needs OPENAI_API_KEY

Prints precision/recall for catching bad schedules, the false-positive rate on good
ones, and recall per defect type. Add --show-grader to let the judge see the
deterministic grader's verdict (then hard defects are easy; the default hides it).
This does NOT replace human labels; see docs/WHAT_GOOD_MEANS.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scheduler_eval.judge import GeminiJudge, StubbornJudge  # noqa: E402
from scheduler_eval.openai_adapter import OpenAIJudge  # noqa: E402
from scheduler_eval.judge_eval import build_probes, evaluate_judge  # noqa: E402


def fmt(x):
    return "n/a" if x is None else f"{x:.2f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--judge", choices=["stubborn", "gemini", "openai"], default="stubborn")
    ap.add_argument("--judge-model", default=None, help="exact model id (openai) or gemini model name")
    ap.add_argument("--scenarios", default=str(ROOT / "data" / "scenarios.jsonl"))
    ap.add_argument("--show-grader", action="store_true")
    ap.add_argument("--out", default=None, help="write full results (incl. critiques) as JSON")
    args = ap.parse_args()

    if args.judge == "stubborn":
        judge = StubbornJudge()
    elif args.judge == "openai":
        judge = OpenAIJudge(model=args.judge_model)
    else:
        judge = GeminiJudge(model=args.judge_model or "gemini-2.5-pro")
    probes = build_probes(args.scenarios)
    res = evaluate_judge(judge, probes, show_grader_report=args.show_grader)

    print(f"judge: {args.judge}   grader verdict shown to judge: {args.show_grader}")
    print(f"probes: {res['n_probes']} ({res['n_bad']} bad, {res['n_good']} good)")
    print(f"precision (bad):          {fmt(res['precision_bad'])}")
    print(f"recall (bad):             {fmt(res['recall_bad'])}")
    print(f"false-positive on good:   {fmt(res['false_positive_rate_on_good'])}")
    print("share judged BAD, by kind (good should be ~0, defects should be ~1):")
    for kind, v in res["by_kind"].items():
        print(f"  {kind:14s} {v['rate_judged_bad']:.2f}  (n={v['n']})")
    if res["n_good"] < 10:
        print(f"\nNote: only {res['n_good']} good probes, so the false-positive rate is rough.")
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
        print(f"\nfull results: {args.out}")


if __name__ == "__main__":
    main()
