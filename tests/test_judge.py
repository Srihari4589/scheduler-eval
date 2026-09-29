"""Tests for the LLM judge module."""

from scheduler_eval.judge import StubbornJudge
from scheduler_eval.schemas import (
    Meeting,
    ScenarioInput,
    ScheduleOutput,
    ScheduleAssignment,
)


def _make_scenario():
    return ScenarioInput(
        meetings=[
            Meeting(id="a", title="A", duration_minutes=60, attendees=["Alice", "Bob"]),
            Meeting(id="b", title="B", duration_minutes=30, attendees=["Alice", "Sam"]),
        ],
        blocked_times=[],
    )


def _make_schedule():
    return ScheduleOutput(
        assignments=[
            ScheduleAssignment(meeting_id="a", day="Mon", start_time="09:00"),
            ScheduleAssignment(meeting_id="b", day="Mon", start_time="10:00"),
        ]
    )


def test_stubborn_judge_passes_valid_schedule():
    judge = StubbornJudge()
    result = judge.evaluate(_make_scenario(), _make_schedule(), {"hard_pass": True})
    assert result["good"] is True
    assert result["scores"]["buffer_time"] == 1.0


def test_stubborn_judge_fails_invalid_schedule():
    judge = StubbornJudge()
    result = judge.evaluate(
        _make_scenario(),
        _make_schedule(),
        {"hard_pass": False, "hard_violations": ["some violation"]},
    )
    assert result["good"] is False
    assert "violation" in result["critique"].lower()


def test_stubborn_judge_returns_all_dimensions():
    judge = StubbornJudge()
    result = judge.evaluate(_make_scenario(), _make_schedule(), {"hard_pass": True})
    expected_dims = {"buffer_time", "meeting_grouping", "energy_management", "fairness", "practicality"}
    assert set(result["scores"].keys()) == expected_dims
