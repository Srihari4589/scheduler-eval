"""Plain-Python grading of a ScheduleOutput. No AI model is involved anywhere in this file.

Everything here is arithmetic and comparisons: turning "09:30" into minutes, checking
whether two time ranges overlap, and counting how many rules were satisfied.
"""

from __future__ import annotations

from .schemas import (
    BlockedTime,
    Correction,
    Meeting,
    ScenarioInput,
    ScheduleOutput,
    WORK_DAYS,
    WORK_END,
    WORK_START,
)

DAY_ORDER = {d: i for i, d in enumerate(WORK_DAYS)}


def _to_minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def _range(day: str, start: str, duration_minutes: int) -> tuple[int, int, int]:
    """Returns (day_index, start_minutes, end_minutes)."""
    start_m = _to_minutes(start)
    return DAY_ORDER.get(day, -1), start_m, start_m + duration_minutes


def _overlaps(a_start: int, a_end: int, b_start: int, b_end: int) -> bool:
    return a_start < b_end and b_start < a_end


def _meeting_lookup(meetings: list[Meeting]) -> dict[str, Meeting]:
    return {m.id: m for m in meetings}


def hard_violations(
    schedule: ScheduleOutput, meetings: list[Meeting], blocked_times: list[BlockedTime]
) -> list[str]:
    """Returns a list of human-readable violation strings. Empty list = fully valid schedule."""
    violations: list[str] = []
    by_id = _meeting_lookup(meetings)
    assigned_ids = [a.meeting_id for a in schedule.assignments]

    # 1. Every meeting scheduled exactly once.
    expected_ids = set(by_id.keys())
    actual_ids = set(assigned_ids)
    for missing in expected_ids - actual_ids:
        violations.append(f"missing: '{missing}' was never scheduled")
    for extra in actual_ids - expected_ids:
        violations.append(f"unknown: '{extra}' is not a real meeting")
    for mid in actual_ids:
        if assigned_ids.count(mid) > 1:
            violations.append(f"duplicate: '{mid}' scheduled more than once")

    placements = []  # (meeting, day, start_min, end_min)
    for a in schedule.assignments:
        m = by_id.get(a.meeting_id)
        if m is None:
            continue
        day_idx, start_m, end_m = _range(a.day, a.start_time, m.duration_minutes)

        # 2. Valid weekday.
        if day_idx == -1:
            violations.append(f"'{m.id}' scheduled on invalid day '{a.day}'")
            continue

        # 3. Inside work hours.
        if start_m < _to_minutes(WORK_START) or end_m > _to_minutes(WORK_END):
            violations.append(
                f"'{m.id}' at {a.day} {a.start_time} falls outside work hours"
            )

        # 4. not_before
        if m.not_before and start_m < _to_minutes(m.not_before):
            violations.append(f"'{m.id}' starts before its not_before={m.not_before}")

        # 5. not_after_day
        if m.not_after_day and day_idx > DAY_ORDER[m.not_after_day]:
            violations.append(f"'{m.id}' scheduled after its not_after_day={m.not_after_day}")

        # 6. fixed_day
        if m.fixed_day and a.day != m.fixed_day:
            violations.append(f"'{m.id}' must be on {m.fixed_day}, got {a.day}")

        # 7. blocked times
        for bt in blocked_times:
            if DAY_ORDER.get(bt.day) == day_idx and _overlaps(
                start_m, end_m, _to_minutes(bt.start), _to_minutes(bt.end)
            ):
                violations.append(f"'{m.id}' overlaps blocked time on {bt.day} ({bt.reason})")

        placements.append((m, day_idx, start_m, end_m))

    # 8. No attendee double-booked.
    for i in range(len(placements)):
        m1, d1, s1, e1 = placements[i]
        for j in range(i + 1, len(placements)):
            m2, d2, s2, e2 = placements[j]
            if d1 == d2 and _overlaps(s1, e1, s2, e2):
                shared = set(m1.attendees) & set(m2.attendees)
                if shared:
                    violations.append(
                        f"'{m1.id}' and '{m2.id}' overlap for shared attendee(s) {sorted(shared)}"
                    )

    return violations


def preference_score(schedule: ScheduleOutput, meetings: list[Meeting]) -> float:
    """Soft-preference satisfaction: fraction of meetings with a 'prefer_before' that met it."""
    by_id = _meeting_lookup(meetings)
    relevant = [m for m in meetings if m.prefer_before]
    if not relevant:
        return 1.0
    satisfied = 0
    for a in schedule.assignments:
        m = by_id.get(a.meeting_id)
        if m and m.prefer_before and _to_minutes(a.start_time) < _to_minutes(m.prefer_before):
            satisfied += 1
    return satisfied / len(relevant)


def correction_compliance(
    schedule: ScheduleOutput, correction: Correction, meetings_after: list[Meeting]
) -> dict[str, float]:
    """Checks whether the final schedule reflects the mid-task correction.
    Returns a dict of 0/1 sub-scores for whichever parts of the correction apply.
    """
    result: dict[str, float] = {}
    assigned_ids = {a.meeting_id for a in schedule.assignments}

    if correction.adds_meeting is not None:
        result["added_meeting_present"] = float(correction.adds_meeting.id in assigned_ids)

    if correction.removes_meeting_id is not None:
        result["removed_meeting_absent"] = float(
            correction.removes_meeting_id not in assigned_ids
        )

    if correction.adds_blocked_time is not None:
        bt = correction.adds_blocked_time
        by_id = _meeting_lookup(meetings_after)
        conflict = False
        for a in schedule.assignments:
            m = by_id.get(a.meeting_id)
            if not m:
                continue
            day_idx, start_m, end_m = _range(a.day, a.start_time, m.duration_minutes)
            if DAY_ORDER.get(bt.day) == day_idx and _overlaps(
                start_m, end_m, _to_minutes(bt.start), _to_minutes(bt.end)
            ):
                conflict = True
        result["new_blocked_time_respected"] = float(not conflict)

    if correction.reassign_attendee_unavailable is not None:
        info = correction.reassign_attendee_unavailable
        attendee, bad_day = info["attendee"], info["day"]
        by_id = _meeting_lookup(meetings_after)
        conflict = False
        for a in schedule.assignments:
            m = by_id.get(a.meeting_id)
            if m and attendee in m.attendees and a.day == bad_day:
                conflict = True
        result["attendee_moved_off_unavailable_day"] = float(not conflict)

    return result


def grade_final(
    schedule: ScheduleOutput,
    scenario_input: ScenarioInput,
    original_meetings: list[Meeting] | None = None,
    correction: Correction | None = None,
) -> dict:
    """Full grading report for one final schedule.

    - hard_violations / hard_pass: the non-negotiable rules
    - preference_score: soft-preference satisfaction
    - regression_score (only if original_meetings given): fraction of the ORIGINAL
      meetings' hard constraints still satisfied after a correction was applied -
      catches the agent "forgetting" earlier constraints while fixing a new one
    - correction_* (only if a correction was given): did it actually comply
    """
    violations = hard_violations(schedule, scenario_input.meetings, scenario_input.blocked_times)

    # If the correction made an attendee unavailable on a day, leaving them booked that day
    # is a hard failure of the FINAL schedule. (The stale fixed_day rule was lifted for
    # grading, so without this check an agent that ignores the correction would still pass.)
    if correction is not None and correction.reassign_attendee_unavailable is not None:
        who = correction.reassign_attendee_unavailable["attendee"]
        bad_day = correction.reassign_attendee_unavailable["day"]
        by_id = _meeting_lookup(scenario_input.meetings)
        for a in schedule.assignments:
            m = by_id.get(a.meeting_id)
            if m and who in m.attendees and a.day == bad_day:
                violations.append(
                    f"'{m.id}' is still on {bad_day} but the correction made {who} "
                    f"unavailable that day"
                )

    report: dict = {
        "hard_violations": violations,
        "hard_pass": float(len(violations) == 0),
        "preference_score": preference_score(schedule, scenario_input.meetings),
    }

    if original_meetings is not None:
        # Re-check only the meetings that existed before the correction, using only
        # their own per-meeting rules (not the full attendee-conflict pass, since new
        # meetings from the correction may legitimately interact with them).
        original_ids = {m.id for m in original_meetings}
        sub_assignments = [a for a in schedule.assignments if a.meeting_id in original_ids]
        sub_schedule = ScheduleOutput(assignments=sub_assignments)
        regression_violations = hard_violations(
            sub_schedule, original_meetings, scenario_input.blocked_times
        )
        report["regression_violations"] = regression_violations
        report["regression_score"] = float(len(regression_violations) == 0)

    if correction is not None:
        report.update(correction_compliance(schedule, correction, scenario_input.meetings))

    return report
