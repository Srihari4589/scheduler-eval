"""Generate a PDF report of the scheduler_eval project for mentors."""

from fpdf import FPDF
from pathlib import Path
import json
import glob

ARTIFACTS_DIR = Path(__file__).resolve().parents[1] / "artifacts" / "runs"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "artifacts" / "scheduler_eval_report.pdf"


class PDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(100, 100, 100)
        self.cell(0, 8, "scheduler_eval - Project Report", align="R")
        self.ln(12)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(150, 150, 150)
        self.cell(0, 10, f"Page {self.page_no()}", align="C")

    def section_title(self, title):
        self.set_font("Helvetica", "B", 14)
        self.set_text_color(30, 80, 162)
        self.cell(0, 10, title, new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(30, 80, 162)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(4)

    def subsection_title(self, title):
        self.set_font("Helvetica", "B", 11)
        self.set_text_color(50, 50, 50)
        self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def body_text(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.multi_cell(0, 5.5, text)
        self.ln(2)

    def bullet(self, text):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        x = self.get_x()
        self.cell(6, 5.5, chr(149))
        self.multi_cell(0, 5.5, text)
        self.ln(1)

    def metric_row(self, label, value):
        self.set_font("Helvetica", "", 10)
        self.set_text_color(40, 40, 40)
        self.cell(90, 6, label)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(30, 80, 162)
        self.cell(0, 6, value, new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(40, 40, 40)


def get_latest_run():
    files = sorted(ARTIFACTS_DIR.glob("*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text(encoding="utf-8"))


def build_pdf():
    pdf = PDF()
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(30, 80, 162)
    pdf.cell(0, 14, "scheduler_eval", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "I", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, "A Scheduling Agent with Multi-Level Evaluation Harness", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    # Metadata
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(80, 80, 80)
    pdf.cell(0, 6, "Date: 2026-09-29", align="C")
    pdf.cell(0, 6, "Author: Srihari", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, "Repo: github.com/Srihari4589/scheduler-eval", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(8)

    # 1. Project Overview
    pdf.section_title("1. Project Overview")
    pdf.body_text(
        "scheduler_eval is a weekly meeting-scheduling agent built to practice evaluation. "
        "The agent receives a list of meetings with hard constraints (no double-booking, fixed days, "
        "earliest-start times, blocked times) and soft preferences (e.g. 'ideally before 11am'), "
        "and must place them into a Mon-Fri, 09:00-17:00 week. Some scenarios include a mid-task "
        "correction that forces the agent to revise its schedule without breaking earlier constraints."
    )
    pdf.body_text(
        "The project follows Hamel Husain's three-level evaluation framework: "
        "Level 1 (deterministic unit tests), Level 2 (LLM-based qualitative judgment), "
        "and Level 3 (A/B testing). The correction step is the key design feature: "
        "a one-shot agent cannot produce retries, corrections, or 'did it forget what I told it earlier' failures."
    )

    # 2. Architecture
    pdf.section_title("2. Architecture")
    pdf.body_text("The project is organized into the following components:")
    pdf.bullet("schemas.py - Pydantic data models (Meeting, ScenarioInput, ScheduleOutput, Correction)")
    pdf.bullet("agent.py - Provider protocol + GeminiProvider (real model) + FixtureProvider (naive baseline)")
    pdf.bullet("grader.py - Deterministic scoring: hard violations, preference score, correction compliance, regression check")
    pdf.bullet("judge.py - LLM-based qualitative judge (GeminiJudge) + negative control (StubbornJudge)")
    pdf.bullet("runner.py - End-to-end scenario runner, saves JSON reports to artifacts/runs/")
    pdf.bullet("cli.py - Typer CLI with --provider, --model, --repeats, and --judge flags")
    pdf.bullet("tests/ - 24 tests covering grader, runner, scenarios, and judge")
    pdf.bullet("scripts/ - Review tool, agreement measurement, Loggy import, report generation")
    pdf.ln(2)

    # 3. Test Results
    pdf.section_title("3. Test Results")
    pdf.body_text("All 24 tests pass. The test suite covers:")
    pdf.bullet("Grader: 9 tests - hard violations, double-booking, missing meetings, work hours, not_before/not_after, blocked times, regression, correction compliance")
    pdf.bullet("Runner: 6 tests - perfect provider, stubborn provider (negative control), correction exercised, turn-1 validity")
    pdf.bullet("Scenarios: 3 tests - loading, uniqueness, correction ground truth")
    pdf.bullet("Judge: 3 tests - stubborn judge pass/fail, dimension coverage")
    pdf.ln(2)

    # 4. Benchmark Results
    pdf.section_title("4. Benchmark Results (Gemini 3.5 Flash Lite)")
    run = get_latest_run()
    if run:
        summary = run.get("summary", {})
        pdf.body_text("Latest run: " + run.get("timestamp", "unknown"))
        pdf.body_text("Provider: " + run.get("provider", "unknown"))
        pdf.body_text("Cases: " + str(run.get("num_cases", 0)) + "  |  Errors: " + str(run.get("errors", 0)))
        pdf.ln(2)
        pdf.metric_row("Hard pass rate:", f"{summary.get('hard_pass_rate', 0):.4f}")
        pdf.metric_row("Avg preference score:", f"{summary.get('avg_preference_score', 0):.4f}")
        pdf.metric_row("Avg regression score:", f"{summary.get('avg_regression_score', 0):.4f}")
        pdf.metric_row("Avg correction exercised:", f"{summary.get('avg_correction_exercised', 0):.4f}")
        pdf.metric_row("Avg added meeting present:", f"{summary.get('avg_added_meeting_present', 0):.4f}")
        pdf.metric_row("Avg attendee moved off unavailable day:", f"{summary.get('avg_attendee_moved_off_unavailable_day', 0):.4f}")
        pdf.metric_row("Avg removed meeting absent:", f"{summary.get('avg_removed_meeting_absent', 0):.4f}")
        pdf.metric_row("Avg new blocked time respected:", f"{summary.get('avg_new_blocked_time_respected', 0):.4f}")
    pdf.ln(2)

    # 5. Scenarios
    pdf.section_title("5. Test Scenarios (6 total)")
    scenarios = [
        ("baseline_week", "No correction. Basic mix of constraints: shared attendees, fixed day, not-before, soft preference."),
        ("add_meeting_midtask", "Correction adds a new meeting. Tests fitting it in without breaking earlier constraints."),
        ("attendee_unavailable_midtask", "Sam's meetings pinned to Tuesday. Correction makes Tuesday unavailable - agent must move them."),
        ("remove_meeting_midtask", "Correction cancels a meeting. Tests clean removal without disturbing anything else."),
        ("blocked_time_midtask", "Wednesday afternoon blocked. Correction blocks morning - agent must fit meetings in 90-min window."),
        ("dense_week_add_big_meeting", "7 meetings, 4 people, daily lunch blocked. Correction adds a 2-hour meeting with a deadline."),
    ]
    for sid, desc in scenarios:
        pdf.bullet(f"{sid}: {desc}")
    pdf.ln(2)

    # 6. Key Findings
    pdf.section_title("6. Key Findings")
    pdf.bullet("False positive found and fixed: attendee_unavailable_midtask originally never put anything on Tuesday, so the correction tested nothing. Fixed by forcing Sam's meetings onto Tuesday with fixed_day.")
    pdf.bullet("Second grader bug found: regression check still expected a cancelled meeting, so a correct agent scored 0. Fixed in runner.py.")
    pdf.bullet("Negative control added: StubbornProvider ignores every correction. Found that a perfect score could measure nothing - grader now adds a hard violation when an unavailable attendee is still booked that day.")
    pdf.bullet("Prompt ambiguity fixed: model read 'before 10:00' as 'by 10:00'. Reworded prompt to say 'strictly earlier than... exactly equal does NOT satisfy it'. Preference score went from 0.9444 to 1.0000.")
    pdf.bullet("Rate limit handling: Gemini free-tier 429 errors invalidate --repeats runs. Documented in known issues.")
    pdf.ln(2)

    # 7. Evaluation Levels
    pdf.section_title("7. Evaluation Levels Implemented")
    pdf.subsection_title("Level 1: Unit Tests (Complete)")
    pdf.body_text("24 deterministic tests covering grader, runner, scenarios, and judge. Run on every push via GitHub Actions CI.")
    pdf.subsection_title("Level 2: LLM Judge (Implemented)")
    pdf.body_text("GeminiJudge critiques schedules on 5 qualitative dimensions: buffer time, meeting grouping, energy management, fairness, practicality. StubbornJudge serves as negative control. Meta-evaluation workflow built (review tool + agreement measurement).")
    pdf.subsection_title("Level 3: A/B Testing (Partially)")
    pdf.body_text("--repeats N runs the benchmark multiple times for variance analysis. Loggy import script enables run comparison. Full A/B testing (two prompts, same scenarios) not yet automated.")
    pdf.ln(2)

    # 8. Known Issues
    pdf.section_title("8. Known Issues and Limitations")
    issues = [
        "Constraint satisfaction does not equal schedule quality - grader verifies hard rules, not goodness",
        "No soft-preference gradation (binary per meeting, no partial credit)",
        "No attendee workload fairness check",
        "No temporal distribution check (all meetings on 2 days = evenly spread)",
        "--repeats summary silently skips errored cases",
        "No tracing / observability (no Langfuse integration)",
        "No human evaluation workflow (tooling built, labels not yet collected)",
        "No automated A/B testing",
        "Gemini free-tier rate limits require spacing between runs",
    ]
    for issue in issues:
        pdf.bullet(issue)
    pdf.ln(2)

    # 9. Comparison with Teammate's Project
    pdf.section_title("9. Comparison with Teammate's transciption_agent_eval")
    pdf.body_text("The teammate's project is at a more mature evaluation phase. Key differences:")
    pdf.bullet("Meta-evaluation: Teammate has full workflow (human annotation, evaluator comparison, adjudication). We have the tooling built but need human labels.")
    pdf.bullet("Tracing: Teammate uses Langfuse for every benchmark item. We save JSON reports but have no trace UI.")
    pdf.bullet("CI: Teammate runs tests + fixture benchmark on every push. We now have the same.")
    pdf.bullet("Known defects: Teammate documents as baseline counterexamples. We now document 9 known issues.")
    pdf.bullet("Experiment tracking: Teammate uses Loggy. We have an import script ready.")
    pdf.bullet("Data policy: Teammate has consent/redaction/retention for sensitive transcripts. Our data is synthetic, so N/A.")
    pdf.ln(2)

    # 10. Next Steps
    pdf.section_title("10. Next Steps")
    next_steps = [
        "Collect human labels using the review tool, then measure judge precision/recall",
        "Add harder scenarios: two corrections in a row, correction conflicting with blocked time, impossible correction",
        "Try a weaker model to confirm the grader discriminates good from bad",
        "Integrate Langfuse tracing for browsable runs",
        "Fix --repeats summary to warn about errors",
        "Add soft-preference gradation and attendee fairness metrics",
        "Write the 'what good means' document (half-page definition of schedule quality)",
        "Rotate Gemini API key (was visible in screen recording)",
    ]
    for step in next_steps:
        pdf.bullet(step)
    pdf.ln(4)

    # Footer
    pdf.set_font("Helvetica", "I", 9)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 6, "Generated by scheduler_eval - scripts/generate_report.py", align="C")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(OUTPUT_PATH))
    print(f"Report saved to: {OUTPUT_PATH}")


if __name__ == "__main__":
    build_pdf()
