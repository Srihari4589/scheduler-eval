"""OpenAI-compatible provider and judge (for example the mentor-provided GPT6 Luna model).

Configuration comes from environment variables, so no secret is ever written to a file:

    export OPENAI_API_KEY=...                  # required
    export OPENAI_MODEL=<exact model id>       # or pass --model on the command line
    export OPENAI_BASE_URL=https://.../v1      # optional, only for a non-default endpoint

    pip install -e ".[openai]"
    scheduler-eval --provider openai --model <exact model id> --repeats 1

The exact model id is deliberately not hard-coded: pass it in.
"""

from __future__ import annotations

import json
import os
import time

from .agent import load_prompt
from .judge import JUDGE_PROMPT
from .schemas import ScenarioInput, ScheduleOutput

RETRY_STATUS = (429, 500, 502, 503, 504)


def _make_client(api_key: str | None = None, base_url: str | None = None):
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise ImportError('Install the OpenAI SDK first: pip install -e ".[openai]"') from exc
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Set OPENAI_API_KEY (or pass api_key=) to use the OpenAI adapter.")
    return OpenAI(api_key=key, base_url=base_url or os.environ.get("OPENAI_BASE_URL") or None)


def resolve_model(model: str | None) -> str:
    name = model or os.environ.get("OPENAI_MODEL")
    if not name:
        raise RuntimeError(
            "No model id given. Pass --model <exact id> or set OPENAI_MODEL. "
            "The id is not guessed on purpose."
        )
    return name


def _chat_json(client, model: str, system: str, user: str, retries: int = 4, sleep=time.sleep) -> dict:
    """One JSON-mode chat call with backoff on rate limits and server errors."""
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format={"type": "json_object"},
            )
            return json.loads(resp.choices[0].message.content)
        except json.JSONDecodeError:
            raise
        except Exception as exc:  # the SDK raises typed errors; status_code is the stable part
            last = exc
            status = getattr(exc, "status_code", None)
            if status not in RETRY_STATUS or attempt == retries:
                raise
            sleep(2 ** attempt)
    raise last  # pragma: no cover


class OpenAIProvider:
    """Scheduling agent backed by an OpenAI-compatible chat model."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, client=None):
        self.model_name = resolve_model(model)
        self._client = client or _make_client(api_key, base_url)
        self.system_prompt = load_prompt()

    def generate(self, scenario_input: ScenarioInput,
                 prior_turns: list[dict] | None = None) -> ScheduleOutput:
        schema_hint = json.dumps(ScheduleOutput.model_json_schema(), indent=2)
        parts = [
            "Respond with ONLY a JSON object matching this schema, no other text:\n" + schema_hint,
            "Current scheduling task (JSON):\n" + scenario_input.model_dump_json(indent=2),
        ]
        if prior_turns:
            parts.append("Conversation so far:\n" + "\n".join(
                f"[{t['role']}]: {t['content']}" for t in prior_turns))
        data = _chat_json(self._client, self.model_name, self.system_prompt, "\n\n".join(parts))
        return ScheduleOutput.model_validate(data)


class OpenAIJudge:
    """Qualitative judge backed by an OpenAI-compatible chat model."""

    def __init__(self, model: str | None = None, api_key: str | None = None,
                 base_url: str | None = None, client=None):
        self.model_name = resolve_model(model)
        self._client = client or _make_client(api_key, base_url)

    def evaluate(self, scenario_input: ScenarioInput, schedule: ScheduleOutput,
                 grader_report: dict) -> dict:
        user = "\n\n".join([
            "--- Original scheduling task ---\n" + scenario_input.model_dump_json(indent=2),
            "--- Proposed schedule ---\n" + schedule.model_dump_json(indent=2),
            "--- Deterministic grader report ---\n" + json.dumps(grader_report, indent=2),
        ])
        data = _chat_json(self._client, self.model_name, JUDGE_PROMPT, user)
        # Same rule as GeminiJudge: hard violations always make the schedule not good.
        if not grader_report.get("hard_pass", True):
            data["good"] = False
            data["critique"] = ("Hard constraints violated: "
                                + "; ".join(grader_report.get("hard_violations", [])))
        return data
