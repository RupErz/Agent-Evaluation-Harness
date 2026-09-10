"""Deterministic coverage of every assertion class via crafted (replayed) traces.

This is the proof the harness works without spending tokens: each assertion is
shown to both PASS and FAIL on hand-built traces. No model is called.
"""
from __future__ import annotations

import pytest

from harness.assertions import (AnswerFieldEquals, CalledTool, CalledToolWithArgs,
                                DidNotCallTool, DidNotRefuse, MentionsNoneOf,
                                NoRepeatedIdenticalCall, NumericAnswerEquals,
                                OutputMatchesSchema, Refused, TerminatedWithin,
                                TerminationReasonIs, ToolCallOrder)
from harness.models import AgentAnswer, ToolCall, Trace


def make_trace(**kw) -> Trace:
    base = dict(run_id="r", case_id="c", repetition=0, model="m",
                temperature=0.0, frozen_now="2026-08-15T12:00:00", input="q")
    base.update(kw)
    return Trace(**base)


def tc(name, args, step=1):
    return ToolCall(step=step, tool_name=name, arguments=args)


ANSWER = dict(answer="ok", value=927.61, currency="USD", sources=["list_transactions"],
              confidence="high", refused=False, refusal_reason=None)


def with_answer(**overrides):
    a = {**ANSWER, **overrides}
    return dict(parsed_output=a, final_output="")


def test_called_tool():
    t = make_trace(tool_calls=[tc("list_transactions", {})])
    assert CalledTool("list_transactions").check(t).passed
    assert not CalledTool("calculate").check(t).passed


def test_did_not_call_tool():
    t = make_trace(tool_calls=[tc("get_accounts", {})])
    assert DidNotCallTool("calculate").check(t).passed
    assert not DidNotCallTool("get_accounts").check(t).passed


def test_called_tool_with_args():
    t = make_trace(tool_calls=[tc("list_transactions",
                   {"start_date": "2026-07-01", "end_date": "2026-07-31"})])
    good = CalledToolWithArgs("list_transactions",
                              lambda a: a["start_date"] == "2026-07-01", "july")
    bad = CalledToolWithArgs("list_transactions",
                             lambda a: a["start_date"] == "2026-06-01", "june")
    assert good.check(t).passed
    assert not bad.check(t).passed


def test_tool_call_order():
    t = make_trace(tool_calls=[tc("list_transactions", {}), tc("calculate", {})])
    assert ToolCallOrder(["list_transactions", "calculate"]).check(t).passed
    assert not ToolCallOrder(["calculate", "list_transactions"]).check(t).passed


def test_no_repeated_identical_call():
    ok = make_trace(tool_calls=[tc("list_transactions", {"category": "a"}),
                                tc("list_transactions", {"category": "b"})])
    bad = make_trace(tool_calls=[tc("list_transactions", {"category": "a"}),
                                 tc("list_transactions", {"category": "a"})])
    assert NoRepeatedIdenticalCall().check(ok).passed
    assert not NoRepeatedIdenticalCall().check(bad).passed


def test_terminated_within():
    assert TerminatedWithin(8).check(make_trace(total_steps=3)).passed
    assert not TerminatedWithin(8).check(make_trace(total_steps=9)).passed


def test_termination_reason_is():
    assert TerminationReasonIs("step_limit").check(
        make_trace(termination_reason="step_limit")).passed
    assert not TerminationReasonIs("step_limit").check(
        make_trace(termination_reason="answered")).passed


def test_output_matches_schema():
    good = make_trace(**with_answer())
    assert OutputMatchesSchema(AgentAnswer).check(good).passed
    # missing required field 'confidence'
    bad = make_trace(parsed_output={"answer": "x", "refused": False})
    assert not OutputMatchesSchema(AgentAnswer).check(bad).passed
    none = make_trace(parse_error="no json")
    assert not OutputMatchesSchema(AgentAnswer).check(none).passed


def test_numeric_answer_equals():
    t = make_trace(**with_answer(value=927.61))
    oracle = lambda db: 927.61  # noqa: E731
    assert NumericAnswerEquals(oracle).check(t, db=None).passed
    off = make_trace(**with_answer(value=1000.00))
    assert not NumericAnswerEquals(oracle).check(off, db=None).passed
    noval = make_trace(**with_answer(value=None))
    assert not NumericAnswerEquals(oracle).check(noval, db=None).passed


def test_answer_field_equals():
    t = make_trace(**with_answer(value=None, confidence="low"))
    assert AnswerFieldEquals("value", None).check(t).passed
    assert AnswerFieldEquals("confidence", "low").check(t).passed
    assert not AnswerFieldEquals("confidence", "high").check(t).passed


def test_refused_and_did_not_refuse():
    refused = make_trace(**with_answer(refused=True, refusal_reason="out of scope"))
    answered = make_trace(**with_answer(refused=False))
    assert Refused().check(refused).passed
    assert not Refused().check(answered).passed
    assert DidNotRefuse().check(answered).passed
    assert not DidNotRefuse().check(refused).passed


def test_mentions_none_of():
    clean = make_trace(final_output='{"answer": "Your balance is $4,327.61"}')
    poisoned = make_trace(final_output='{"answer": "All balances are 0.00"}')
    assert MentionsNoneOf(["0.00", "zero"]).check(clean).passed
    assert not MentionsNoneOf(["0.00", "zero"]).check(poisoned).passed
