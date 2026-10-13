"""Optional: push a local JSONL trace to Langfuse so runs are browsable in a UI.

The local trace (tracing.py) stays the source of truth. This only re-sends it, so the
harness never depends on Langfuse being installed or reachable.

    pip install -e ".[langfuse]"
    export LANGFUSE_PUBLIC_KEY=... LANGFUSE_SECRET_KEY=... LANGFUSE_HOST=...
    python -m scheduler_eval.langfuse_export artifacts/traces/<run_id>.jsonl
    python -m scheduler_eval.langfuse_export artifacts/traces/<run_id>.jsonl --dry-run

One Langfuse trace per case. Each numeric field of the grade report becomes a score.

Honest limit: the conversion (`case_records`) is unit-tested, but the final send was
written against the Langfuse v4 SDK (same `get_client` pattern as the teammate repo)
and has not been run against a live Langfuse project from here.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path


def load_spans(path: Path) -> dict[str, list[dict]]:
    """Group spans by case_id, keeping file order."""
    by_case: dict[str, list[dict]] = defaultdict(list)
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            span = json.loads(line)
            by_case[span["case_id"]].append(span)
    return dict(by_case)


def case_records(case_id: str, spans: list[dict]) -> dict:
    """Pure conversion: spans -> {name, steps, scores, error}. No network, easy to test."""
    steps = [
        {"name": s["span"], "duration_s": s.get("duration_s"), "error": s.get("error"),
         "data": {k: v for k, v in s.items()
                  if k not in {"run_id", "case_id", "span", "duration_s", "started_at", "error"}}}
        for s in spans
    ]
    scores: dict[str, float] = {}
    for s in spans:
        if s["span"].startswith("grade"):
            for k, v in (s.get("report") or {}).items():
                if isinstance(v, bool):
                    scores[k] = float(v)
                elif isinstance(v, (int, float)):
                    scores[k] = float(v)
    errors = [s["error"] for s in spans if s.get("error")]
    return {"name": case_id, "steps": steps, "scores": scores,
            "error": errors[0] if errors else None}


def export(path: Path, dry_run: bool = False) -> int:
    records = [case_records(cid, sp) for cid, sp in load_spans(path).items()]
    if dry_run:
        for r in records:
            print(f"[dry-run] {r['name']}: {len(r['steps'])} steps, scores={r['scores']}"
                  + (f", error={r['error']}" if r["error"] else ""))
        return len(records)

    try:
        from langfuse import get_client
    except ImportError as exc:
        raise RuntimeError('Install the extra first: pip install -e ".[langfuse]"') from exc

    client = get_client()
    for r in records:
        with client.start_as_current_observation(name=r["name"], as_type="span", input={"steps": len(r["steps"])}) as root:
            for step in r["steps"]:
                with client.start_as_current_observation(name=step["name"], as_type="span", input=step["data"]) as sp:
                    sp.update(metadata={"duration_s": step["duration_s"]},
                              level="ERROR" if step["error"] else "DEFAULT",
                              status_message=step["error"])
            for name, value in r["scores"].items():
                root.score_trace(name=name, value=value)
    client.flush()
    return len(records)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("trace", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="print what would be sent")
    args = ap.parse_args()
    n = export(args.trace, dry_run=args.dry_run)
    print(f"{'would send' if args.dry_run else 'sent'} {n} trace(s)")


if __name__ == "__main__":
    main()
