"""OpenAI adapter tests with a fake client. No network, no key."""
import json
from types import SimpleNamespace

import pytest

from scheduler_eval.openai_adapter import OpenAIJudge, OpenAIProvider, resolve_model
from scheduler_eval.schemas import ScenarioInput, ScheduleOutput


class FakeErr(Exception):
    def __init__(self, status):
        self.status_code = status


class FakeClient:
    """Returns queued replies; an int in the queue raises an error with that status."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, **kw):
        self.calls.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, int):
            raise FakeErr(r)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=r))])


def _scenario():
    return ScenarioInput(meetings=[{"id": "a", "title": "A", "duration_minutes": 30,
                                    "attendees": ["X"]}], blocked_times=[], notes="")


SCHEDULE = json.dumps({"assignments": [{"meeting_id": "a", "day": "Mon", "start_time": "09:00"}],
                       "notes": "ok"})


def test_model_is_never_guessed(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="No model id"):
        resolve_model(None)
    monkeypatch.setenv("OPENAI_MODEL", "from-env")
    assert resolve_model(None) == "from-env"
    assert resolve_model("explicit") == "explicit"


def test_provider_parses_schedule_and_sends_model():
    c = FakeClient([SCHEDULE])
    out = OpenAIProvider(model="m1", client=c).generate(_scenario())
    assert isinstance(out, ScheduleOutput) and out.assignments[0].day == "Mon"
    assert c.calls[0]["model"] == "m1"
    assert c.calls[0]["response_format"] == {"type": "json_object"}


def test_prior_turns_are_included():
    c = FakeClient([SCHEDULE])
    OpenAIProvider(model="m", client=c).generate(
        _scenario(), prior_turns=[{"role": "user", "content": "move Sam"}])
    assert "move Sam" in c.calls[0]["messages"][1]["content"]


def test_retries_rate_limit_then_succeeds(monkeypatch):
    import scheduler_eval.openai_adapter as oa
    monkeypatch.setattr(oa.time, "sleep", lambda s: None)
    c = FakeClient([429, 503, SCHEDULE])
    OpenAIProvider(model="m", client=c).generate(_scenario())
    assert len(c.calls) == 3


def test_non_retryable_error_is_raised_immediately():
    c = FakeClient([401, SCHEDULE])
    with pytest.raises(FakeErr):
        OpenAIProvider(model="m", client=c).generate(_scenario())
    assert len(c.calls) == 1


def test_judge_overrides_good_when_grader_found_violations():
    reply = json.dumps({"good": True, "critique": "fine", "scores": {"practicality": 1.0}})
    c = FakeClient([reply])
    sched = ScheduleOutput.model_validate_json(SCHEDULE)
    out = OpenAIJudge(model="m", client=c).evaluate(
        _scenario(), sched, {"hard_pass": False, "hard_violations": ["x overlaps y"]})
    assert out["good"] is False and "x overlaps y" in out["critique"]
