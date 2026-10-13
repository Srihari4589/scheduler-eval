"""Checks the judge-evaluation harness itself, with no AI involved."""

from pathlib import Path

from scheduler_eval.grader import hard_violations
from scheduler_eval.judge import StubbornJudge
from scheduler_eval.judge_eval import build_probes, evaluate_judge

SCENARIOS = Path(__file__).resolve().parents[1] / "data" / "scenarios.jsonl"


class OracleJudge:
    """Knows the answer (by re-running the grader + a spacing check). Validates the
    metric math: it must score ~perfectly, otherwise the harness is wrong."""

    def evaluate(self, scenario_input, schedule, grader_report):
        vs = hard_violations(schedule, scenario_input.meetings, scenario_input.blocked_times)
        by_id = {m.id: m for m in scenario_input.meetings}
        from scheduler_eval.grader import _to_minutes
        per_day: dict[str, list[tuple[int, int]]] = {}
        for a in schedule.assignments:
            s = _to_minutes(a.start_time)
            per_day.setdefault(a.day, []).append((s, s + by_id[a.meeting_id].duration_minutes))
        cramped = any(
            nxt[0] - cur[1] < 15
            for rows in per_day.values()
            for cur, nxt in zip(sorted(rows), sorted(rows)[1:])
        )
        return {"good": not vs and not cramped, "critique": "", "scores": {}}


def test_probes_cover_hard_and_soft_defects_and_good():
    kinds = {p.kind for p in build_probes(SCENARIOS)}
    assert "good" in kinds
    assert {"drop_meeting", "double_book", "outside_hours"} <= kinds
    assert {"back_to_back", "late_dump"} & kinds


def test_probe_labels_agree_with_the_grader():
    for p in build_probes(SCENARIOS):
        vs = hard_violations(p.schedule, p.scenario.meetings, p.scenario.blocked_times)
        if p.kind == "good" or p.kind in ("back_to_back", "late_dump"):
            assert vs == [], (p.case_id, p.kind, vs)
        else:
            assert vs, (p.case_id, p.kind, "defect did not break a hard rule")


def test_stubborn_judge_is_a_negative_control_with_zero_recall():
    res = evaluate_judge(StubbornJudge(), build_probes(SCENARIOS))
    assert res["recall_bad"] == 0.0
    assert res["false_positive_rate_on_good"] == 0.0


def test_oracle_judge_scores_perfectly():
    res = evaluate_judge(OracleJudge(), build_probes(SCENARIOS))
    assert res["recall_bad"] == 1.0
    assert res["precision_bad"] == 1.0
    assert res["false_positive_rate_on_good"] == 0.0


def test_judge_is_not_shown_grader_verdict_by_default():
    seen = []

    class Spy:
        def evaluate(self, scenario_input, schedule, grader_report):
            seen.append(grader_report)
            return {"good": True, "critique": "", "scores": {}}

    evaluate_judge(Spy(), build_probes(SCENARIOS))
    assert all(r == {"hard_pass": True, "hard_violations": []} for r in seen)
