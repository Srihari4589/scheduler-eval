"""LLM-based qualitative judge for schedules (Level 2 evaluation).

This module uses a powerful model to critique schedule quality beyond what the
deterministic grader can check. The grader verifies hard constraints; the judge
evaluates qualitative dimensions like buffer time, meeting grouping, energy
management, and whether the schedule "feels" like something a human would want.

Following Hamel Husain's guidance:
- The judge is a meta-problem: it must be evaluated against human labels.
- We track precision/recall, not raw agreement.
- The judge's critiques can be used to curate fine-tuning data.
"""

from __future__ import annotations

import json
import os
from typing import Protocol

from .schemas import ScenarioInput, ScheduleOutput


JUDGE_PROMPT = """You are an expert scheduling assistant evaluating the quality of a weekly meeting schedule.

You will be given:
1. The original scheduling task (meetings, constraints, preferences)
2. The proposed schedule
3. A deterministic grader report (hard constraint violations, preference score)

Evaluate the schedule on these QUALITATIVE dimensions (not already covered by the hard rules):

- **Buffer time**: Are there reasonable gaps between meetings, or is the schedule back-to-back with no breathing room?
- **Meeting grouping**: Are related meetings clustered together sensibly, or scattered randomly across the week?
- **Energy management**: Are demanding meetings placed at reasonable times (not too early, not right after lunch, not at the end of the day)?
- **Fairness**: Is the schedule distributed fairly across attendees, or does one person get all the inconvenient slots?
- **Practicality**: Does this look like a schedule a real person could actually follow?

Respond with ONLY a JSON object matching this schema:
{
  "good": true/false,
  "critique": "2-3 sentences explaining your judgment",
  "scores": {
    "buffer_time": 0.0-1.0,
    "meeting_grouping": 0.0-1.0,
    "energy_management": 0.0-1.0,
    "fairness": 0.0-1.0,
    "practicality": 0.0-1.0
  }
}

A schedule is "good" if it is something a competent human assistant would produce. It does NOT need to be perfect, but it should be thoughtful and practical. If the grader already found hard violations, the schedule is automatically not good regardless of qualitative merit.
"""


class Judge(Protocol):
    """Anything that can qualitatively evaluate a schedule."""

    def evaluate(
        self,
        scenario_input: ScenarioInput,
        schedule: ScheduleOutput,
        grader_report: dict,
    ) -> dict: ...


class GeminiJudge:
    """Uses a Gemini model to critique schedule quality."""

    def __init__(
        self,
        model: str = "gemini-2.5-pro",
        api_key: str | None = None,
    ):
        try:
            import google.generativeai as genai
        except ImportError as exc:
            raise ImportError(
                "Install the Gemini SDK first: pip install google-generativeai"
            ) from exc

        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("Set GEMINI_API_KEY (or pass api_key=) to use GeminiJudge.")

        genai.configure(api_key=key)
        self._genai = genai
        self.model_name = model

    def evaluate(
        self,
        scenario_input: ScenarioInput,
        schedule: ScheduleOutput,
        grader_report: dict,
    ) -> dict:
        schema_hint = json.dumps(
            {
                "type": "object",
                "properties": {
                    "good": {"type": "boolean"},
                    "critique": {"type": "string"},
                    "scores": {
                        "type": "object",
                        "properties": {
                            "buffer_time": {"type": "number"},
                            "meeting_grouping": {"type": "number"},
                            "energy_management": {"type": "number"},
                            "fairness": {"type": "number"},
                            "practicality": {"type": "number"},
                        },
                    },
                },
            },
            indent=2,
        )

        parts = [
            JUDGE_PROMPT,
            "\nRespond with ONLY a JSON object matching this schema:\n" + schema_hint,
            "\n--- Original scheduling task ---\n" + scenario_input.model_dump_json(indent=2),
            "\n--- Proposed schedule ---\n" + schedule.model_dump_json(indent=2),
            "\n--- Deterministic grader report ---\n" + json.dumps(grader_report, indent=2),
        ]

        model = self._genai.GenerativeModel(
            self.model_name,
            generation_config={"response_mime_type": "application/json"},
        )
        response = model.generate_content("\n".join(parts))
        data = json.loads(response.text)

        # If the grader found hard violations, override the judge's "good" to False.
        if not grader_report.get("hard_pass", True):
            data["good"] = False
            data["critique"] = (
                "Hard constraints violated: " + "; ".join(grader_report.get("hard_violations", []))
            )

        return data


class StubbornJudge:
    """A judge that always says "good" - used as a negative control to verify
    the evaluation pipeline works. Its precision/recall against human labels
    should be near zero.
    """

    def evaluate(
        self,
        scenario_input: ScenarioInput,
        schedule: ScheduleOutput,
        grader_report: dict,
    ) -> dict:
        if not grader_report.get("hard_pass", True):
            violations = grader_report.get("hard_violations", [])
            return {
                "good": False,
                "critique": "Hard constraints violated: " + "; ".join(violations),
                "scores": {
                    "buffer_time": 0.0,
                    "meeting_grouping": 0.0,
                    "energy_management": 0.0,
                    "fairness": 0.0,
                    "practicality": 0.0,
                },
            }
        return {
            "good": True,
            "critique": "Stubborn judge: always says good when hard constraints pass.",
            "scores": {
                "buffer_time": 1.0,
                "meeting_grouping": 1.0,
                "energy_management": 1.0,
                "fairness": 1.0,
                "practicality": 1.0,
            },
        }
