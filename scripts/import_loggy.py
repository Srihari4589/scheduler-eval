"""Import scheduler_eval run artifacts into Loggy format.

Usage:
    python scripts/import_loggy.py

Reads all JSON files from artifacts/runs/ and outputs Loggy-compatible JSON
to artifacts/loggy_import/. You can then import these into Loggy via its UI
or CLI.
"""

from __future__ import annotations

import json
import hashlib
from datetime import UTC, datetime
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "runs"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "loggy_import"


def run_to_loggy(run: dict) -> dict:
    """Convert a scheduler_eval run report to Loggy format (version 1)."""
    provider = run.get("provider", "unknown")
    parts = provider.split(":")
    model = parts[1] if len(parts) > 1 else "unknown"
    framework = parts[0] if parts else "unknown"

    summary = run.get("summary", {})
    # NOTE: runner.py's report has no "metadata" sub-object - git_sha lives at the
    # top level of the run report. (Previously this always read {} here, so git_sha
    # silently showed as "unknown" in every Loggy import even when a real sha existed.)
    metadata = {
        "git_sha": run.get("git_sha"),
        "prompt_version": run.get("prompt_version"),  # not yet tracked by runner.py
    }

    metrics = {}
    metric_directions = {
        "hard_pass_rate": "higher",
        "avg_preference_score": "higher",
        "avg_regression_score": "higher",
        "avg_correction_exercised": "higher",
        "avg_added_meeting_present": "higher",
        "avg_removed_meeting_absent": "higher",
        "avg_new_blocked_time_respected": "higher",
        "avg_attendee_moved_off_unavailable_day": "higher",
    }

    for key, value in summary.items():
        if isinstance(value, (int, float)):
            metric_name = key
            if key.startswith("avg_"):
                metric_name = key[4:]
            metrics[metric_name] = {
                "value": round(value, 4),
                "direction": metric_directions.get(key, "higher"),
            }

    cases = run.get("cases", [])
    errors = run.get("errors", 0)
    case_count = run.get("num_cases", len(cases))

    if errors > 0:
        result = f"{errors} of {case_count} cases errored (rate limit or other issue)."
        next_step = "Wait for quota reset and rerun."
    elif case_count == 0:
        result = "No cases were run."
        next_step = "Check scenario file."
    else:
        hard_pass = summary.get("hard_pass_rate", 0)
        if hard_pass == 1.0:
            result = f"All {case_count} cases passed hard constraints."
            next_step = "Add harder scenarios."
        else:
            result = f"{int(hard_pass * case_count)}/{case_count} cases passed hard constraints."
            next_step = "Inspect failures."

    date_str = run.get("timestamp", datetime.now(UTC).isoformat())[:10]

    title = f"{framework}:{model}"
    if metadata.get("prompt_version"):
        title += f" {metadata['prompt_version']}"
    if metadata.get("git_sha"):
        title += f" ({metadata['git_sha'][:7]})"

    return {
        "schema_version": 1,
        "date": date_str,
        "title": title,
        "attempt": f"Run {framework}:{model} on {case_count} scenarios",
        "setup": f"provider={framework}, model={model}, cases={case_count}",
        "result": result,
        "next": next_step,
        "metadata": {
            "provider": framework,
            "model": model,
            "git_sha": metadata.get("git_sha", "unknown"),
            "prompt_version": metadata.get("prompt_version", "v1"),
            "scheduler_eval_timestamp": run.get("timestamp", ""),
        },
        "metrics": metrics,
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    run_files = sorted(ARTIFACTS_DIR.glob("*.json"))
    if not run_files:
        print("No run files found in artifacts/runs/")
        return

    for run_file in run_files:
        run = json.loads(run_file.read_text(encoding="utf-8"))
        loggy_entry = run_to_loggy(run)

        sha = hashlib.sha256(run_file.read_bytes()).hexdigest()[:12]
        out_path = OUTPUT_DIR / f"{date_str(run)}_{sha}.json"
        out_path.write_text(json.dumps(loggy_entry, indent=2), encoding="utf-8")
        print(f"  {run_file.name} -> {out_path.name}")

    print(f"\nImported {len(run_files)} runs to {OUTPUT_DIR}/")
    print("Import these files into Loggy via its UI or CLI.")


def date_str(run: dict) -> str:
    ts = run.get("timestamp", datetime.now(UTC).isoformat())
    return ts[:10].replace("-", "")


if __name__ == "__main__":
    main()
