"""Data models for the scheduling agent and its evaluation.

Everything here is plain data (Pydantic models). No AI involved in this file.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

Day = Literal["Mon", "Tue", "Wed", "Thu", "Fri"]

WORK_DAYS: list[Day] = ["Mon", "Tue", "Wed", "Thu", "Fri"]
WORK_START = "09:00"
WORK_END = "17:00"


class Meeting(BaseModel):
    """One meeting that needs to be scheduled somewhere in the week."""

    id: str
    title: str
    duration_minutes: int
    attendees: list[str] = Field(default_factory=list)

    # Hard constraints specific to this meeting (all optional).
    not_before: Optional[str] = None       # e.g. "10:00" - can't start earlier than this, any day
    not_after_day: Optional[Day] = None    # e.g. "Thu" - must be scheduled on or before this day
    fixed_day: Optional[Day] = None        # if set, must be on this exact day

    # Soft preference (not a hard requirement, used for the preference score).
    prefer_before: Optional[str] = None    # e.g. "12:00" - ideally starts before this time


class BlockedTime(BaseModel):
    """A chunk of time that is off-limits to schedule anything in."""

    day: Day
    start: str  # "HH:MM"
    end: str    # "HH:MM"
    reason: str = ""


class ScenarioInput(BaseModel):
    """Everything the agent is given at the start of a scheduling task."""

    meetings: list[Meeting]
    blocked_times: list[BlockedTime] = Field(default_factory=list)
    notes: str = ""  # free-text context given to the agent (e.g. "this is a light week")


class Correction(BaseModel):
    """A natural-language instruction the user gives mid-task."""

    text: str
    # Structured ground truth about what the correction implies, used ONLY by the grader,
    # never shown to the agent. Lets us check the agent actually complied.
    adds_meeting: Optional[Meeting] = None
    removes_meeting_id: Optional[str] = None
    adds_blocked_time: Optional[BlockedTime] = None
    reassign_attendee_unavailable: Optional[dict] = None  # {"attendee": str, "day": Day}


class ScheduleAssignment(BaseModel):
    """Where the agent decided to put one meeting."""

    meeting_id: str
    day: Day
    start_time: str  # "HH:MM"


class ScheduleOutput(BaseModel):
    """The agent's structured answer: a full proposed schedule."""

    assignments: list[ScheduleAssignment]
    notes: Optional[str] = None


class ScenarioCase(BaseModel):
    """One full test case: an initial scheduling task, plus an optional mid-task correction."""

    id: str
    description: str
    input: ScenarioInput
    correction: Optional[Correction] = None
