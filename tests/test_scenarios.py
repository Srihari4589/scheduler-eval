import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from scheduler_eval.runner import load_scenarios

SCENARIOS_PATH = Path(__file__).resolve().parents[1] / "data" / "scenarios.jsonl"


def test_loads_all_scenarios():
    cases = load_scenarios(SCENARIOS_PATH)
    assert len(cases) >= 3


def test_at_least_one_case_has_a_correction():
    cases = load_scenarios(SCENARIOS_PATH)
    assert any(c.correction is not None for c in cases)


def test_at_least_one_case_has_no_correction():
    cases = load_scenarios(SCENARIOS_PATH)
    assert any(c.correction is None for c in cases)


def test_scenario_ids_are_unique():
    ids = [c.id for c in load_scenarios(SCENARIOS_PATH)]
    assert len(ids) == len(set(ids))


def test_every_correction_has_machine_checkable_ground_truth():
    for c in load_scenarios(SCENARIOS_PATH):
        if c.correction is not None:
            k = c.correction
            assert any([k.adds_meeting, k.removes_meeting_id, k.adds_blocked_time,
                        k.reassign_attendee_unavailable]), c.id
