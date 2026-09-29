"""Runs scenarios through a Provider and grades the result.

This file wires together agent.py (calls the model) and grader.py (plain Python
scoring). No AI is used in the grading step itself.
"""

from __future__ import annotations

import json
import subprocess
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from .agent import Provider, SimulatedUser
from .grader import correction_compliance, grade_final
from .schemas import BlockedTime, Meeting, ScenarioCase, ScenarioInput

ARTIFACTS_DIR = Path(__file__).resolve().parents[2] / "artifacts" / "runs"


def load_scenarios(path: str | Path) -> list[ScenarioCase]:
    cases = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(ScenarioCase.model_validate(json.loads(line)))
    return cases


def _git_sha() -> str | None:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=Path(__file__).parent, timeout=5,
        )
        return out.stdout.strip() or None
    except Exception:
        return None


def _lift_superseded_fixed_day(meetings: list[Meeting], case: ScenarioCase) -> list[Meeting]:
    """If the correction says an attendee is unavailable on day X, any meeting that had a
    fixed_day == X for that attendee is no longer bound by that fixed_day when we grade the
    FINAL schedule. The correction explicitly supersedes it - a schedule that complies with
    the correction (moves the meeting off day X) should NOT be penalized as if it broke the
    original fixed_day rule, since that rule is exactly the thing the correction overrode.
    Every other constraint on the meeting (duration, other attendees, etc.) still applies.
    """
    c = case.correction
    if c is None or c.reassign_attendee_unavailable is None:
        return meetings
    attendee = c.reassign_attendee_unavailable["attendee"]
    bad_day = c.reassign_attendee_unavailable["day"]

    updated = []
    for m in meetings:
        if m.fixed_day == bad_day and attendee in m.attendees:
            updated.append(m.model_copy(update={"fixed_day": None}))
        else:
            updated.append(m)
    return updated


def _apply_correction_to_scenario(
    original: ScenarioInput, case: ScenarioCase
) -> tuple[ScenarioInput, list[Meeting]]:
    """Builds the scenario reflecting the correction's ground-truth changes, for grading
    the FINAL schedule. Returns (updated_scenario, original_meetings_for_regression_check).

    Both returned meeting lists have any fixed_day rule that the correction explicitly
    supersedes lifted (see _lift_superseded_fixed_day) - otherwise an agent that correctly
    complies with the correction would be wrongly flagged for breaking the stale rule.
    """
    original_meetings = _lift_superseded_fixed_day(list(original.meetings), case)
    if case.correction is None:
        return original, original_meetings

    # A meeting the correction cancels must not be expected in the regression check either,
    # otherwise an agent that correctly drops it is scored as having "forgotten" it.
    if case.correction.removes_meeting_id:
        original_meetings = [
            m for m in original_meetings if m.id != case.correction.removes_meeting_id
        ]

    meetings = _lift_superseded_fixed_day(list(original.meetings), case)
    blocked = list(original.blocked_times)
    c = case.correction

    if c.removes_meeting_id:
        meetings = [m for m in meetings if m.id != c.removes_meeting_id]
    if c.adds_meeting:
        meetings.append(c.adds_meeting)
    if c.adds_blocked_time:
        blocked.append(c.adds_blocked_time)

    updated = ScenarioInput(meetings=meetings, blocked_times=blocked, notes=original.notes)
    return updated, original_meetings


@dataclass
class CaseResult:
    case_id: str
    description: str
    turns: int
    report: dict
    error: str | None = None
    raw_schedules: list[dict] = field(default_factory=list)


def run_case(provider: Provider, case: ScenarioCase, user_mode: str = "scripted") -> CaseResult:
    try:
        # Turn 1: initial plan.
        schedule_1 = provider.generate(case.input)
        raw = [schedule_1.model_dump()]
        turns = 1

        final_schedule = schedule_1
        final_scenario_input = case.input
        original_meetings = None
        correction_used = None

        if case.correction is not None:
            simulated_user = SimulatedUser(mode=user_mode)
            correction_text = simulated_user.get_correction(case.correction.text, schedule_1)
            correction_used = case.correction

            prior_turns = [
                {"role": "assistant", "content": schedule_1.model_dump_json()},
                {"role": "user", "content": correction_text},
            ]
            schedule_2 = provider.generate(case.input, prior_turns=prior_turns)
            raw.append(schedule_2.model_dump())
            turns = 2

            final_schedule = schedule_2
            final_scenario_input, original_meetings = _apply_correction_to_scenario(
                case.input, case
            )

        report = grade_final(
            schedule=final_schedule,
            scenario_input=final_scenario_input,
            original_meetings=original_meetings,
            correction=correction_used,
        )
        if correction_used is not None:
            # Did the FIRST schedule already conflict with the correction? If not, the
            # correction never forced a change and a passing score proves little
            # (this is the false-positive we found in attendee_unavailable_midtask).
            turn1 = correction_compliance(
                schedule_1, correction_used, final_scenario_input.meetings
            )
            report["correction_exercised"] = float(any(v == 0.0 for v in turn1.values()))
        return CaseResult(
            case_id=case.id, description=case.description, turns=turns,
            report=report, raw_schedules=raw,
        )
    except Exception as exc:  # noqa: BLE001 - one bad case shouldn't kill the whole run
        return CaseResult(
            case_id=case.id, description=case.description, turns=0,
            report={}, error=f"{exc}\n{traceback.format_exc()}",
        )


def run_all(
    provider: Provider,
    scenarios_path: str | Path,
    provider_label: str,
    user_mode: str = "scripted",
) -> dict:
    cases = load_scenarios(scenarios_path)
    results = [run_case(provider, c, user_mode=user_mode) for c in cases]

    errors = sum(1 for r in results if r.error)
    ok_results = [r for r in results if not r.error]

    def avg(key: str) -> float | None:
        vals = [r.report[key] for r in ok_results if key in r.report]
        return sum(vals) / len(vals) if vals else None

    summary = {
        "hard_pass_rate": avg("hard_pass"),
        "avg_preference_score": avg("preference_score"),
        "avg_regression_score": avg("regression_score"),
    }
    # Any correction_* keys, gathered dynamically since they only apply to some cases.
    correction_keys = {k for r in ok_results for k in r.report if k not in
                        ("hard_pass", "preference_score", "regression_score",
                         "hard_violations", "regression_violations")}
    for k in correction_keys:
        summary[f"avg_{k}"] = avg(k)

    report = {
        "timestamp": datetime.now(UTC).isoformat(),
        "provider": provider_label,
        "user_mode": user_mode,
        "git_sha": _git_sha(),
        "num_cases": len(cases),
        "errors": errors,
        "summary": summary,
        "cases": [
            {
                "case_id": r.case_id,
                "description": r.description,
                "turns": r.turns,
                "error": r.error,
                "report": r.report,
                "raw_schedules": r.raw_schedules,
            }
            for r in results
        ],
    }

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS_DIR / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    report["_report_path"] = str(out_path)
    return report
