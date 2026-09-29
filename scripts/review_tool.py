"""Generate an HTML review tool for human labeling of scheduler_eval runs.

Usage:
    python scripts/review_tool.py

Creates artifacts/review.html — a standalone HTML file that shows each case's
schedule side-by-side with the grader report. A human labels each as good/bad,
and the labels can be exported as JSON for meta-evaluation.
"""

from __future__ import annotations

import json
import html
from datetime import UTC, datetime
from pathlib import Path

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "runs"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "review.html"


def load_latest_runs(n: int = 5) -> list[dict]:
    files = sorted(ARTIFACTS_DIR.glob("*.json"))[-n:]
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


def schedule_to_html(schedule: dict) -> str:
    rows = []
    for a in sorted(schedule.get("assignments", []), key=lambda x: (x["day"], x["start_time"])):
        rows.append(f"<tr><td>{html.escape(a['meeting_id'])}</td><td>{a['day']}</td><td>{a['start_time']}</td></tr>")
    if not rows:
        return "<p><em>No assignments</em></p>"
    return f"""<table class="schedule">
        <tr><th>Meeting</th><th>Day</th><th>Start</th></tr>
        {''.join(rows)}
    </table>"""


def grader_report_to_html(report: dict) -> str:
    parts = []
    if report.get("hard_violations"):
        parts.append("<div class='violations'><strong>Hard violations:</strong><ul>")
        for v in report["hard_violations"]:
            parts.append(f"<li>{html.escape(v)}</li>")
        parts.append("</ul></div>")
    else:
        parts.append("<div class='pass'>No hard violations</div>")

    if "preference_score" in report:
        parts.append(f"<p>Preference score: {report['preference_score']:.2f}</p>")
    if "regression_score" in report:
        parts.append(f"<p>Regression score: {report['regression_score']:.2f}</p>")

    for key, val in report.items():
        if key.startswith(("added_", "removed_", "new_blocked_", "attendee_moved_")):
            parts.append(f"<p>{key}: {val:.0f}</p>")

    if "judge_good" in report:
        verdict = "GOOD" if report["judge_good"] else "BAD"
        parts.append(f"<p><strong>LLM Judge:</strong> {verdict}</p>")
        if report.get("judge_critique"):
            parts.append(f"<p class='critique'>{html.escape(report['judge_critique'])}</p>")

    return "\n".join(parts)


def build_review_html(runs: list[dict]) -> str:
    cases_html = []
    case_id = 0
    for run in runs:
        provider = run.get("provider", "unknown")
        timestamp = run.get("timestamp", "")
        for case in run.get("cases", []):
            if case.get("error"):
                continue
            case_id += 1
            cid = case["case_id"]
            desc = case.get("description", "")
            report = case.get("report", {})
            raw = case.get("raw_schedules", [])
            final_schedule = raw[-1] if raw else {}

            cases_html.append(f"""
            <div class="case" id="case-{case_id}">
                <h3>Case {case_id}: {html.escape(cid)}</h3>
                <p class="desc">{html.escape(desc)}</p>
                <p class="meta">Provider: {html.escape(provider)} | Run: {html.escape(timestamp)}</p>
                <div class="columns">
                    <div>{schedule_to_html(final_schedule)}</div>
                    <div>{grader_report_to_html(report)}</div>
                </div>
                <div class="label-buttons">
                    <button onclick="label({case_id}, 'good')">Good</button>
                    <button onclick="label({case_id}, 'bad')">Bad</button>
                    <span id="label-{case_id}"></span>
                </div>
            </div>
            """)

    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>scheduler_eval — Human Review</title>
    <style>
        body {{ font-family: system-ui, sans-serif; max-width: 1000px; margin: 0 auto; padding: 20px; }}
        .case {{ border: 1px solid #ccc; border-radius: 8px; padding: 16px; margin-bottom: 20px; }}
        .case h3 {{ margin-top: 0; }}
        .desc {{ color: #555; font-style: italic; }}
        .meta {{ color: #888; font-size: 0.85em; }}
        .columns {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
        table.schedule {{ border-collapse: collapse; width: 100%; }}
        table.schedule th, table.schedule td {{ border: 1px solid #ddd; padding: 4px 8px; text-align: left; }}
        .violations {{ background: #fee; padding: 8px; border-radius: 4px; }}
        .pass {{ background: #efe; padding: 8px; border-radius: 4px; }}
        .critique {{ color: #555; font-style: italic; }}
        .label-buttons {{ margin-top: 12px; }}
        .label-buttons button {{ padding: 6px 16px; margin-right: 8px; cursor: pointer; }}
        .label-buttons button.good {{ background: #4caf50; color: white; border: none; border-radius: 4px; }}
        .label-buttons button.bad {{ background: #f44336; color: white; border: none; border-radius: 4px; }}
        #export {{ margin-top: 20px; padding: 10px 20px; background: #2196f3; color: white; border: none; border-radius: 4px; cursor: pointer; }}
    </style>
</head>
<body>
    <h1>scheduler_eval — Human Review</h1>
    <p>Label each case as Good or Bad based on whether you'd accept this schedule from a competent human assistant.</p>
    <p>Consider: buffer time, meeting grouping, energy management, fairness, practicality — not just hard constraint satisfaction.</p>
    <button id="export" onclick="exportLabels()">Export Labels (JSON)</button>
    <div id="cases">
        {''.join(cases_html)}
    </div>
    <script>
        const labels = {{}};
        function label(caseId, verdict) {{
            labels[caseId] = verdict;
            document.getElementById('label-' + caseId).textContent = '→ ' + verdict.toUpperCase();
        }}
        function exportLabels() {{
            const data = JSON.stringify(labels, null, 2);
            const blob = new Blob([data], {{type: 'application/json'}});
            const a = document.createElement('a');
            a.href = URL.createObjectURL(blob);
            a.download = 'human_labels.json';
            a.click();
        }}
    </script>
</body>
</html>"""


def main():
    runs = load_latest_runs(5)
    if not runs:
        print("No run files found. Run the benchmark first.")
        return

    html_content = build_review_html(runs)
    OUTPUT_PATH.write_text(html_content, encoding="utf-8")
    print(f"Review tool: {OUTPUT_PATH}")
    print(f"Open it in a browser, label each case, then export labels as JSON.")


if __name__ == "__main__":
    main()
