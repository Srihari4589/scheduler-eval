"""The agent itself: a Provider that turns a scheduling task into a ScheduleOutput.

This file is the only place that talks to an actual AI model.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Protocol

from .schemas import ScenarioInput, ScheduleOutput

PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "planner_v1.txt"


def load_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8")


class Provider(Protocol):
    """Anything that can take a scheduling task (+ optional prior turns) and return a schedule."""

    def generate(
        self,
        scenario_input: ScenarioInput,
        prior_turns: list[dict] | None = None,
    ) -> ScheduleOutput: ...


class FixtureProvider:
    """Returns a trivially-valid, empty-ish schedule. Used only to sanity-check the harness
    itself (grading code, runner, CLI). Its score must never be reported as a real result.
    """

    def generate(
        self,
        scenario_input: ScenarioInput,
        prior_turns: list[dict] | None = None,
    ) -> ScheduleOutput:
        # Naively places meetings back to back starting Monday 09:00, ignoring most rules.
        # This is intentionally a weak, mechanical placement - NOT a "correct answer" -
        # it exists so we can test that the grader correctly flags violations.
        from .schemas import ScheduleAssignment, WORK_DAYS

        assignments = []
        day_idx = 0
        minutes_used = 0
        for m in scenario_input.meetings:
            day = WORK_DAYS[day_idx % len(WORK_DAYS)]
            hour = 9 + minutes_used // 60
            minute = minutes_used % 60
            assignments.append(
                ScheduleAssignment(
                    meeting_id=m.id, day=day, start_time=f"{hour:02d}:{minute:02d}"
                )
            )
            minutes_used += m.duration_minutes
            if minutes_used >= 8 * 60:
                minutes_used = 0
                day_idx += 1
        return ScheduleOutput(assignments=assignments, notes="fixture: naive placement")


class GeminiProvider:
    """Calls Google's Gemini API and parses its response into a ScheduleOutput."""

    def __init__(self, model: str = "gemini-2.0-flash", api_key: str | None = None):
        try:
            import google.generativeai as genai
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "Install the Gemini SDK first: pip install google-generativeai"
            ) from exc

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY (or pass api_key=) to use GeminiProvider.")

        genai.configure(api_key=key)
        self._genai = genai
        self.model_name = model
        self.system_prompt = load_prompt()

    def generate(
        self,
        scenario_input: ScenarioInput,
        prior_turns: list[dict] | None = None,
    ) -> ScheduleOutput:
        schema_hint = json.dumps(ScheduleOutput.model_json_schema(), indent=2)

        parts = [
            self.system_prompt,
            "\nRespond with ONLY a JSON object matching this schema, no other text:\n"
            + schema_hint,
            "\nCurrent scheduling task (JSON):\n"
            + scenario_input.model_dump_json(indent=2),
        ]

        if prior_turns:
            history = "\n".join(
                f"[{turn['role']}]: {turn['content']}" for turn in prior_turns
            )
            parts.append("\nConversation so far:\n" + history)

        model = self._genai.GenerativeModel(
            self.model_name,
            generation_config={"response_mime_type": "application/json"},
        )
        response = model.generate_content("\n".join(parts))
        data = json.loads(response.text)
        return ScheduleOutput.model_validate(data)


class SimulatedUser:
    """A lightweight stand-in for a real user reacting to the agent's first schedule.

    Two modes:
    - scripted: just returns the pre-written correction text from the scenario
      (used when we need a known ground truth to grade compliance against).
    - interactive: asks a real person (you) to type the correction at the terminal.
    """

    def __init__(self, mode: str = "scripted"):
        if mode not in ("scripted", "interactive"):
            raise ValueError("mode must be 'scripted' or 'interactive'")
        self.mode = mode

    def get_correction(self, scripted_text: str | None, proposed_schedule: ScheduleOutput) -> str:
        if self.mode == "interactive":
            print("\nAgent proposed this schedule:")
            print(proposed_schedule.model_dump_json(indent=2))
            return input("\nType your correction (or press Enter to accept as-is): ").strip()
        return scripted_text or ""
