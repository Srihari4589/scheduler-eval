import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduler_eval.grader import correction_compliance, grade_final, hard_violations
from scheduler_eval.schemas import (
    BlockedTime,
    Correction,
    Meeting,
    ScenarioInput,
    ScheduleAssignment,
    ScheduleOutput,
)


def make_meeting(**kwargs):
    defaults = dict(id="m1", title="Test", duration_minutes=30, attendees=[])
    defaults.update(kwargs)
    return Meeting(**defaults)


def test_valid_schedule_has_no_violations():
    meetings = [make_meeting(id="a", attendees=["Alice"]), make_meeting(id="b", attendees=["Bob"])]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),
        ScheduleAssignment(meeting_id="b", day="Mon", start_time="10:00"),
    ])
    assert hard_violations(schedule, meetings, []) == []


def test_detects_double_booking_for_shared_attendee():
    meetings = [
        make_meeting(id="a", attendees=["Alice"], duration_minutes=60),
        make_meeting(id="b", attendees=["Alice"], duration_minutes=60),
    ]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),
        ScheduleAssignment(meeting_id="b", day="Mon", start_time="09:30"),  # overlaps
    ])
    violations = hard_violations(schedule, meetings, [])
    assert any("overlap" in v for v in violations)


def test_no_violation_when_overlap_has_no_shared_attendee():
    meetings = [
        make_meeting(id="a", attendees=["Alice"], duration_minutes=60),
        make_meeting(id="b", attendees=["Bob"], duration_minutes=60),
    ]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),
        ScheduleAssignment(meeting_id="b", day="Mon", start_time="09:30"),
    ])
    assert hard_violations(schedule, meetings, []) == []


def test_detects_missing_meeting():
    meetings = [make_meeting(id="a"), make_meeting(id="b")]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),
    ])
    violations = hard_violations(schedule, meetings, [])
    assert any("missing" in v and "b" in v for v in violations)


def test_detects_outside_work_hours():
    meetings = [make_meeting(id="a", duration_minutes=30)]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="17:30"),
    ])
    violations = hard_violations(schedule, meetings, [])
    assert any("work hours" in v for v in violations)


def test_not_before_and_not_after_day():
    meetings = [
        make_meeting(id="a", not_before="13:00"),
        make_meeting(id="b", not_after_day="Tue"),
    ]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),  # too early
        ScheduleAssignment(meeting_id="b", day="Wed", start_time="09:00"),  # too late
    ])
    violations = hard_violations(schedule, meetings, [])
    assert any("not_before" in v for v in violations)
    assert any("not_after_day" in v for v in violations)


def test_blocked_time_conflict():
    meetings = [make_meeting(id="a", duration_minutes=60)]
    blocked = [BlockedTime(day="Mon", start="09:00", end="12:00", reason="focus time")]
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:30"),
    ])
    violations = hard_violations(schedule, meetings, blocked)
    assert any("blocked time" in v for v in violations)


def test_regression_score_catches_forgotten_constraint():
    """If the agent's revised schedule breaks a constraint from BEFORE the correction,
    regression_score must be 0, even if the correction itself was satisfied."""
    original_meetings = [make_meeting(id="a", not_before="13:00", duration_minutes=30)]
    new_meeting = make_meeting(id="b", duration_minutes=30, attendees=[])
    scenario = ScenarioInput(meetings=original_meetings + [new_meeting], blocked_times=[])
    correction = Correction(text="add b", adds_meeting=new_meeting)

    # Final schedule violates 'a' not_before=13:00 (put at 09:00) while adding 'b' fine.
    schedule = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),
        ScheduleAssignment(meeting_id="b", day="Mon", start_time="10:00"),
    ])
    report = grade_final(
        schedule, scenario, original_meetings=original_meetings, correction=correction
    )
    assert report["regression_score"] == 0.0
    assert report["added_meeting_present"] == 1.0


def test_moving_meeting_off_superseded_fixed_day_is_not_penalized():
    """Regression test for a real bug found by reading actual Gemini traces: if a meeting's
    fixed_day is exactly the day a later correction makes unavailable for that attendee,
    complying with the correction (moving the meeting elsewhere) must NOT be scored as a
    hard-constraint violation of the now-superseded fixed_day.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from scheduler_eval.runner import _lift_superseded_fixed_day
    from scheduler_eval.schemas import ScenarioCase, ScenarioInput

    meeting = make_meeting(id="sam-1-1", attendees=["Sam"], fixed_day="Tue")
    case = ScenarioCase(
        id="t", description="t",
        input=ScenarioInput(meetings=[meeting]),
        correction=Correction(
            text="move sam off tuesday",
            reassign_attendee_unavailable={"attendee": "Sam", "day": "Tue"},
        ),
    )
    lifted = _lift_superseded_fixed_day([meeting], case)
    assert lifted[0].fixed_day is None  # the stale rule is gone for grading purposes

    schedule_moved = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="sam-1-1", day="Wed", start_time="09:00"),
    ])
    # Grading against the LIFTED meeting list: moving to Wednesday is now fully valid.
    assert hard_violations(schedule_moved, lifted, []) == []


def test_correction_compliance_attendee_moved():
    correction = Correction(
        text="move sam off tuesday",
        reassign_attendee_unavailable={"attendee": "Sam", "day": "Tue"},
    )
    meetings = [make_meeting(id="a", attendees=["Sam"])]
    schedule_bad = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Tue", start_time="09:00"),
    ])
    schedule_good = ScheduleOutput(assignments=[
        ScheduleAssignment(meeting_id="a", day="Wed", start_time="09:00"),
    ])
    bad = correction_compliance(schedule_bad, correction, meetings)
    good = correction_compliance(schedule_good, correction, meetings)
    assert bad["attendee_moved_off_unavailable_day"] == 0.0
    assert good["attendee_moved_off_unavailable_day"] == 1.0
