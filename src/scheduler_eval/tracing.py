"""Lightweight local tracing: one JSONL file per run, one line per step.

A trace answers "what exactly happened in this run?" without re-running it: what the
agent was asked, what it returned, how long each step took, and what the grader said.
No external service needed. Each line is one span, so the file loads into anything
(pandas, jq, Langfuse/Loggy import scripts) without a custom parser.
"""

from __future__ import annotations

import json
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

TRACES_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "traces"


@dataclass
class Trace:
    case_id: str
    spans: list[dict] = field(default_factory=list)

    @contextmanager
    def span(self, name: str, **attrs):
        """Time a step. Attributes can be added to the yielded dict while it runs."""
        record: dict = {"case_id": self.case_id, "span": name, **attrs}
        start = time.perf_counter()
        record["started_at"] = datetime.now(UTC).isoformat()
        try:
            yield record
        except Exception as exc:  # noqa: BLE001 - record then re-raise
            record["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            record["duration_s"] = round(time.perf_counter() - start, 4)
            self.spans.append(record)


def write_traces(traces: list[Trace], run_id: str, directory: Path | None = None) -> Path:
    """Write every span of every case to <directory>/<run_id>.jsonl and return the path."""
    directory = directory or TRACES_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{run_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        for t in traces:
            for s in t.spans:
                f.write(json.dumps({"run_id": run_id, **s}) + "\n")
    return path
