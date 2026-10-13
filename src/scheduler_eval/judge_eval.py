"""Tests the JUDGE against schedules whose quality we know, because we built the defect.

Why: an LLM judge is itself a model that can be wrong. Human labels are the real ground
truth, but they are slow. This gives a fast first check: take a schedule that is
well-spaced and valid ("good"), inject one known defect ("bad"), and ask the judge to
tell them apart. Report precision and recall for catching bad schedules, and the false
positive rate on good ones.

Honest limits:
- The defects are synthetic and fairly blatant. A judge that passes this has not been
  shown to match humans on subtle cases; that still needs real 2-rater labels.
- "good" means well-spaced and rule-valid by construction, not a human's verdict.
- A deterministic ground truth like this cannot tell us whether the judge agrees with
  people, only whether it can catch defects we planted.

No AI is used here except in the judge being tested.
"""

from __future__ import annotations

from dataclasses import dataclass

from .grader import _to_minutes, hard_violations
from .judge import Judge
from .runner import _apply_correction_to_scenario, load_scenarios
from .schemas import (
    WORK_DAYS,
    Meeting,
    ScenarioInput,
    ScheduleAssignment,
    ScheduleOutput,
)

GAP = 30  # minutes of buffer a "good" schedule leaves between meetings on a day


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _structural(schedule: ScheduleOutput, meetings, blocked) -> list[str]:
    """Hard violations other than 'missing' (used while a schedule is partly built)."""
    return [v for v in hard_violations(schedule, meetings, blocked) if not v.startswith("missing")]


def build_good_schedule(scenario: ScenarioInput) -> ScheduleOutput | None:
    """Greedy: spread meetings over the week, mornings first, >= GAP minutes between
    meetings on the same day. Returns None if the greedy search can't place everything."""
    placed: list[ScheduleAssignment] = []
    durations = {m.id: m.duration_minutes for m in scenario.meetings}
    # Hardest-constrained first.
    order = sorted(
        scenario.meetings,
        key=lambda m: (m.fixed_day is None, m.not_before is None, -m.duration_minutes),
    )
    for m in order:
        days = [m.fixed_day] if m.fixed_day else list(WORK_DAYS)
        days.sort(key=lambda d: sum(1 for a in placed if a.day == d))
        ok = False
        for day in days:
            for start in range(9 * 60, 17 * 60, 15):
                end = start + m.duration_minutes
                if any(
                    a.day == day
                    and start < _to_minutes(a.start_time) + durations[a.meeting_id] + GAP
                    and _to_minutes(a.start_time) < end + GAP
                    for a in placed
                ):
                    continue
                cand = ScheduleAssignment(meeting_id=m.id, day=day, start_time=_hhmm(start))
                trial = ScheduleOutput(assignments=[*placed, cand])
                if not _structural(trial, scenario.meetings, scenario.blocked_times):
                    placed.append(cand)
                    ok = True
                    break
            if ok:
                break
        if not ok:
            return None
    return ScheduleOutput(assignments=placed)


# ---- injected defects. Each returns a new schedule, or None if not applicable. ----

def inject_drop_meeting(s, sc):
    return ScheduleOutput(assignments=s.assignments[:-1]) if len(s.assignments) > 1 else None


def inject_double_book(s, sc):
    by_id = {m.id: m for m in sc.meetings}
    for a in s.assignments:
        for b in s.assignments:
            if a is b:
                continue
            if set(by_id[a.meeting_id].attendees) & set(by_id[b.meeting_id].attendees):
                new = [
                    x if x is not b else ScheduleAssignment(
                        meeting_id=b.meeting_id, day=a.day, start_time=a.start_time)
                    for x in s.assignments
                ]
                return ScheduleOutput(assignments=new)
    return None


def inject_outside_hours(s, sc):
    first = s.assignments[0]
    new = [ScheduleAssignment(meeting_id=first.meeting_id, day=first.day, start_time="16:50"),
           *s.assignments[1:]]
    return ScheduleOutput(assignments=new)


def inject_blocked_time(s, sc):
    if not sc.blocked_times:
        return None
    bt = sc.blocked_times[0]
    movable = [a for a in s.assignments
               if not next(m for m in sc.meetings if m.id == a.meeting_id).fixed_day]
    if not movable:
        return None
    a = movable[0]
    new = [x if x is not a else ScheduleAssignment(
        meeting_id=a.meeting_id, day=bt.day, start_time=bt.start) for x in s.assignments]
    return ScheduleOutput(assignments=new)


def _pack(s, sc, latest: bool):
    """Valid but poor: movable meetings all on one day, zero gaps (or pushed late)."""
    by_id = {m.id: m for m in sc.meetings}
    fixed = [a for a in s.assignments if by_id[a.meeting_id].fixed_day]
    movable = [by_id[a.meeting_id] for a in s.assignments if not by_id[a.meeting_id].fixed_day]
    if len(movable) < 2:
        return None
    for day in WORK_DAYS:
        placed = list(fixed)
        ok = True
        cursor = 17 * 60 if latest else 9 * 60
        for m in movable:
            for _ in range(8 * 60):
                start = cursor - m.duration_minutes if latest else cursor
                cand = ScheduleAssignment(meeting_id=m.id, day=day, start_time=_hhmm(start))
                trial = ScheduleOutput(assignments=[*placed, cand])
                if not _structural(trial, sc.meetings, sc.blocked_times):
                    placed.append(cand)
                    cursor = start if latest else start + m.duration_minutes
                    break
                cursor += -1 if latest else 1
                if cursor <= 9 * 60 or cursor >= 17 * 60:
                    ok = False
                    break
            else:
                ok = False
            if not ok:
                break
        if ok:
            return ScheduleOutput(assignments=placed)
    return None


def inject_back_to_back(s, sc):
    return _pack(s, sc, latest=False)


def inject_late_dump(s, sc):
    return _pack(s, sc, latest=True)


HARD_DEFECTS = {
    "drop_meeting": inject_drop_meeting,
    "double_book": inject_double_book,
    "outside_hours": inject_outside_hours,
    "blocked_time": inject_blocked_time,
}
SOFT_DEFECTS = {"back_to_back": inject_back_to_back, "late_dump": inject_late_dump}


@dataclass
class Probe:
    case_id: str
    kind: str          # "good" | defect name
    is_bad: bool
    scenario: ScenarioInput
    schedule: ScheduleOutput


def build_probes(scenarios_path) -> list[Probe]:
    """Good schedules plus one injected defect each, verified against the grader:
    hard defects must FAIL the hard rules, soft defects and good schedules must PASS them."""
    probes: list[Probe] = []
    for case in load_scenarios(scenarios_path):
        final_input, _ = _apply_correction_to_scenario(case.input, case)
        good = build_good_schedule(final_input)
        if good is None:
            continue
        if hard_violations(good, final_input.meetings, final_input.blocked_times):
            continue
        probes.append(Probe(case.id, "good", False, final_input, good))
        for table, must_be_valid in ((HARD_DEFECTS, False), (SOFT_DEFECTS, True)):
            for name, fn in table.items():
                bad = fn(good, final_input)
                if bad is None:
                    continue
                valid = not hard_violations(bad, final_input.meetings, final_input.blocked_times)
                if valid != must_be_valid:
                    continue  # defect didn't behave as intended; drop rather than mislabel
                probes.append(Probe(case.id, name, True, final_input, bad))
    return probes


def evaluate_judge(judge: Judge, probes: list[Probe], show_grader_report: bool = False) -> dict:
    """Ask the judge about every probe. Positive class = 'bad schedule'.

    By default the judge is NOT shown the grader's verdict, so it must notice defects
    itself (the real judge overrides to 'bad' whenever the grader reports a violation,
    which would otherwise make hard defects free).
    """
    tp = fp = tn = fn = 0
    by_kind: dict[str, dict[str, int]] = {}
    rows = []
    for p in probes:
        if show_grader_report:
            vs = hard_violations(p.schedule, p.scenario.meetings, p.scenario.blocked_times)
            report = {"hard_pass": not vs, "hard_violations": vs}
        else:
            report = {"hard_pass": True, "hard_violations": []}
        verdict = judge.evaluate(p.scenario, p.schedule, report)
        said_bad = not verdict["good"]
        if p.is_bad and said_bad:
            tp += 1
        elif p.is_bad:
            fn += 1
        elif said_bad:
            fp += 1
        else:
            tn += 1
        k = by_kind.setdefault(p.kind, {"n": 0, "judged_bad": 0})
        k["n"] += 1
        k["judged_bad"] += int(said_bad)
        rows.append({"case_id": p.case_id, "kind": p.kind, "is_bad": p.is_bad,
                     "judge_said_bad": said_bad, "critique": verdict.get("critique", "")})

    def ratio(a, b):
        return a / b if b else None

    return {
        "n_probes": len(probes),
        "n_bad": tp + fn,
        "n_good": tn + fp,
        "precision_bad": ratio(tp, tp + fp),
        "recall_bad": ratio(tp, tp + fn),
        "false_positive_rate_on_good": ratio(fp, fp + tn),
        "by_kind": {
            name: {**v, "rate_judged_bad": v["judged_bad"] / v["n"]}
            for name, v in sorted(by_kind.items())
        },
        "rows": rows,
    }
