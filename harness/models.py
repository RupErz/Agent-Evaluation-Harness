"""Pydantic / dataclass models shared across the harness.

`AgentAnswer` does real work: validating the agent's final output against it is
one of the assertion types (`OutputMatchesSchema`), so a malformed or
under-specified answer is a *detectable* failure, not a silent one.
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class AgentAnswer(BaseModel):
    """The structured final answer the agent is asked to emit."""

    model_config = {"extra": "forbid"}

    answer: str                       # human-readable
    value: Optional[float] = None     # the number, when the question has one
    currency: Optional[str] = None
    sources: list[str] = Field(default_factory=list)  # tool calls relied on
    confidence: Literal["high", "low"]
    refused: bool
    refusal_reason: Optional[str] = None


class ToolCall(BaseModel):
    step: int
    tool_name: str
    arguments: dict
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0


class Trace(BaseModel):
    """One agent run. This is the artifact that makes a failure diagnosable."""

    run_id: str
    case_id: str
    repetition: int                   # 0..k-1
    model: str                        # pinned string, recorded
    temperature: float
    frozen_now: str
    seed: Optional[int] = None
    input: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    raw_messages: list[dict] = Field(default_factory=list)  # full array, for replay
    final_output: str = ""
    parsed_output: Optional[dict] = None
    parse_error: Optional[str] = None
    termination_reason: Literal["answered", "step_limit", "error"] = "answered"
    total_steps: int = 0
    duration_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0

    def answer(self) -> Optional[AgentAnswer]:
        """Parsed answer as a model, or None if it never parsed."""
        if self.parsed_output is None:
            return None
        try:
            return AgentAnswer.model_validate(self.parsed_output)
        except Exception:
            return None


class AssertionResult(BaseModel):
    name: str
    passed: bool
    message: str = ""
    evidence: Any = None


class CaseResult(BaseModel):
    case_id: str
    failure_mode: str
    notes: str = ""
    k: int
    outcome: Literal["pass", "flaky", "fail"]
    pass_count: int
    pass_rate: float
    per_assertion_pass_rate: dict[str, float] = Field(default_factory=dict)
    # index of the first failing repetition, for the report (-1 if none failed)
    first_failure_rep: int = -1
