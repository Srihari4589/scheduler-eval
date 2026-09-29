"""End-to-end checks on the harness itself (no AI model involved).

1. PerfectProvider: returns hand-verified correct schedules. Must score perfectly everywhere -
   if it doesn't, the bug is in the harness, not in an agent.
2. StubbornProvider: ignores every correction (returns its first schedule again). Must FAIL
   every scenario that has a correction - if it doesn't, some scenario can be passed by
   accident and would give a false positive.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduler_eval.grader import hard_violations
from scheduler_eval.runner import load_scenarios, run_case
from scheduler_eval.schemas import ScenarioInput, ScheduleAssignment, ScheduleOutput

SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "data" / "scenarios.jsonl"


def sched(*rows):
    return ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id=m, day=d, start_time=t) for m, d, t in rows
    ])


# scenario id -> (turn-1 schedule, final schedule after the correction).
# For cases without a correction both are the same.
PERFECT = {
    "baseline_week": (lambda s: (s, s))(sched(
        ("design-review", "Mon", "09:00"), ("sam-1-1", "Tue", "09:00"),
        ("all-hands", "Fri", "09:00"), ("vendor-call", "Mon", "13:00"))),
    "add_meeting_midtask": (
        sched(("design-review", "Mon", "09:00"), ("sam-1-1", "Tue", "09:00"),
              ("all-hands", "Fri", "09:00"), ("vendor-call", "Mon", "13:00")),
        sched(("design-review", "Mon", "09:00"), ("sam-1-1", "Tue", "09:00"),
              ("all-hands", "Fri", "09:00"), ("vendor-call", "Mon", "13:00"),
              ("budget-review", "Tue", "10:00"))),
    # Turn 1 MUST put Sam's meetings on Tuesday (fixed_day). Turn 2 moves them off, which is
    # valid only because the correction supersedes that fixed_day.
    "attendee_unavailable_midtask": (
        sched(("design-review", "Mon", "09:00"), ("sam-1-1", "Tue", "09:00"),
              ("sam-sync", "Tue", "10:00"), ("vendor-call", "Mon", "13:00")),
        sched(("design-review", "Mon", "09:00"), ("sam-1-1", "Wed", "09:00"),
              ("sam-sync", "Wed", "10:00"), ("vendor-call", "Mon", "13:00"))),
    "remove_meeting_midtask": (
        sched(("design-review", "Mon", "09:00"), ("offsite-prep", "Mon", "10:00"),
              ("sam-1-1", "Tue", "09:00"), ("planning", "Thu", "09:00"),
              ("vendor-call", "Mon", "13:00")),
        sched(("design-review", "Mon", "09:00"), ("offsite-prep", "Mon", "10:00"),
              ("sam-1-1", "Tue", "09:00"), ("vendor-call", "Mon", "13:00"))),
    "blocked_time_midtask": (
        sched(("client-sync", "Wed", "09:00"), ("team-retro", "Wed", "09:45"),
              ("sam-1-1", "Mon", "09:00"), ("vendor-call", "Mon", "13:00")),
        sched(("client-sync", "Wed", "10:30"), ("team-retro", "Wed", "11:15"),
              ("sam-1-1", "Mon", "09:00"), ("vendor-call", "Mon", "13:00"))),
    "dense_week_add_big_meeting": (
        sched(("design-review", "Mon", "09:00"), ("hiring-sync", "Mon", "10:00"),
              ("sam-1-1", "Mon", "10:45"), ("vendor-call", "Mon", "14:00"),
              ("qa-triage", "Tue", "09:00"), ("roadmap", "Thu", "09:00"),
              ("all-hands", "Fri", "09:00")),
        sched(("design-review", "Mon", "09:00"), ("hiring-sync", "Mon", "10:00"),
              ("sam-1-1", "Mon", "10:45"), ("vendor-call", "Mon", "14:00"),
              ("qa-triage", "Tue", "09:00"), ("roadmap", "Thu", "09:00"),
              ("all-hands", "Fri", "09:00"), ("board-prep", "Tue", "10:00"))),
}


def _key(scenario_input: ScenarioInput) -> str:
    """Identify a scenario from what the provider is actually shown (the meeting ids)."""
    ids = {m.id for m in scenario_input.meetings}
    for case in load_scenarios(SCENARIOS_PATH):
        if {m.id for m in case.input.meetings} == ids and case.input.notes == scenario_input.notes:
            return case.id
    raise KeyError(f"unknown scenario: {ids}")


class PerfectProvider:
    def generate(self, scenario_input: ScenarioInput, prior_turns=None) -> ScheduleOutput:
        turn1, final = PERFECT[_key(scenario_input)]
        return turn1 if prior_turns is None else final


class StubbornProvider:
    """Gives the same first-turn schedule again after the correction (ignores it)."""

    def generate(self, scenario_input: ScenarioInput, prior_turns=None) -> ScheduleOutput:
        return PERFECT[_key(scenario_input)][0]


def test_every_scenario_has_a_perfect_schedule_entry():
    assert {c.id for c in load_scenarios(SCENARIOS_PATH)} == set(PERFECT)


def test_turn1_schedules_are_valid_for_the_original_task():
    """The first schedule must itself satisfy the ORIGINAL rules (incl. any fixed_day)."""
    for case in load_scenarios(SCENARIOS_PATH):
        turn1, _ = PERFECT[case.id]
        assert hard_violations(turn1, case.input.meetings, case.input.blocked_times) == [], case.id


def test_perfect_provider_scores_perfectly_on_every_scenario():
    for case in load_scenarios(SCENARIOS_PATH):
        result = run_case(PerfectProvider(), case)
        assert result.error is None, result.error
        assert result.report["hard_pass"] == 1.0, (case.id, result.report["hard_violations"])
        if "regression_score" in result.report:
            assert result.report["regression_score"] == 1.0, (
                case.id, result.report.get("regression_violations"))
        for key, value in result.report.items():
            if key.startswith(("added_", "removed_", "new_blocked_", "attendee_moved_")):
                assert value == 1.0, (case.id, key)


def test_every_correction_actually_changes_something_in_turn1():
    """Guards against the false positive we found: a correction that the first schedule
    already satisfied never forces the agent to do anything."""
    for case in load_scenarios(SCENARIOS_PATH):
        if case.correction is None:
            continue
        result = run_case(PerfectProvider(), case)
        assert result.report["correction_exercised"] == 1.0, case.id


def test_ignoring_the_correction_fails_every_scenario_that_has_one():
    """Negative control: an agent that ignores the correction must never get a pass."""
    for case in load_scenarios(SCENARIOS_PATH):
        if case.correction is None:
            continue
        result = run_case(StubbornProvider(), case)
        assert result.error is None, result.error
        assert result.report["hard_pass"] == 0.0, (case.id, "ignored correction but passed")


def test_stubborn_agent_on_sam_tuesday_is_caught_specifically():
    case = next(c for c in load_scenarios(SCENARIOS_PATH)
                if c.id == "attendee_unavailable_midtask")
    report = run_case(StubbornProvider(), case).report
    assert report["attendee_moved_off_unavailable_day"] == 0.0
    assert any("unavailable" in v for v in report["hard_violations"])
