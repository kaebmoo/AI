"""Pass-2 invariant retries refuse the final violation before tool-loop rescue."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest

from app.core import outbound
from app.services.ai import hybrid_flow, retry_loop
from app.services.ai.trace import new_trace


QUESTION = "EBT รายศูนย์ต้นทุน"
AUDIT_407 = ("SELECT cost_center, SUM(COALESCE(ebt, 0)) FROM t "
             "WHERE CAST(time_key AS INTEGER) BETWEEN 202601 AND 202609 GROUP BY cost_center")
SINGLE_PERIOD = "SELECT cost_center, SUM(COALESCE(ebt, 0)) FROM t WHERE time_key = 202609 GROUP BY cost_center"
NO_PERIOD = "SELECT cost_center, ebt FROM t WHERE cost_center = '1'"
ROWS = [{"cost_center": "1", "ebt": 59}]


@pytest.fixture
def execution(monkeypatch):
    monkeypatch.setattr(hybrid_flow, "_context_tables", lambda *a: {})
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: ["ebt"])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda *a: ["ebt_month"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda *a: ["time_key"])
    monkeypatch.setattr(hybrid_flow, "scope_note", lambda: "")
    monkeypatch.setattr(hybrid_flow, "resolve_context_info", lambda *a, **kw: (
        SimpleNamespace(get_context_info=lambda c: {}), "t", "EBT"))
    monkeypatch.setattr(hybrid_flow, "load_execution_metadata", lambda *a: (None, None, None))
    # Pass 1 is fixed; generation, guard, retry prompt, validation and execution stay real.
    monkeypatch.setattr(hybrid_flow, "build_first_attempt_prompt", AsyncMock(return_value=("pass 2", True, None)))

    async def call_tool(name, args):
        if name == "validate_sql":
            return {"valid": True}
        assert name == "execute_query"
        return {"success": True, "data": ROWS}

    return SimpleNamespace(
        provider=SimpleNamespace(last_usage=None, generate_content=AsyncMock(),
                                 explain_result=AsyncMock(return_value="คำอธิบาย")),
        provider_name="fake",
        mcp_client=SimpleNamespace(servers={"nt-query": object()}, call_tool=AsyncMock(side_effect=call_tool)),
        get_vanna_context_string=lambda q: "", lookup_values_from_question=lambda *a: [],
        detect_hierarchy_level=lambda *a: None, format_value_matches=lambda *a: "",
        extract_sql=lambda text: text, extract_explanation=lambda text: "",
        log_value_corrections=Mock(), prepare_data_for_explanation=lambda data, **kw: data,
        set_pending_limit_warning=lambda warning: None, get_pending_limit_warning=lambda: "",
    )


async def query(service, **kwargs):
    return await hybrid_flow.query_hybrid(
        service, QUESTION, "system", context_name="feed_ebt", max_retries=1,
        two_pass_enabled=True, value_verification_enabled=False, **kwargs,
    )


async def test_invariant_retry_can_answer_with_single_period(execution):
    execution.provider.generate_content.side_effect = [AUDIT_407, SINGLE_PERIOD]
    result = await query(execution)
    assert result.error is None and result.data == ROWS
    assert result.sql_query == SINGLE_PERIOD and result.retry_count == 1
    assert "I1 ytd_summed_across_periods" in execution.provider.generate_content.await_args_list[1].args[0]
    assert "ebt" in result.retry_history[0]["error"]
    assert execution.mcp_client.call_tool.await_args_list == [
        call("validate_sql", {"sql": SINGLE_PERIOD}),
        call("execute_query", {"sql": SINGLE_PERIOD, "limit": 1000, "validate_first": False}),
    ]


@pytest.mark.parametrize("sql,code", [(AUDIT_407, "I1"), (NO_PERIOD, "I2")])
@pytest.mark.parametrize("rescue_enabled", [False, True])
async def test_last_invariant_fails_closed(execution, monkeypatch, sql, code, rescue_enabled):
    execution.provider.generate_content.return_value = sql
    rescue = AsyncMock()
    monkeypatch.setattr(retry_loop, "query_with_retry", rescue)
    trace = new_trace(QUESTION)
    result = await query(execution, trace=trace, escalation_tool_loop_enabled=rescue_enabled)
    assert result.error == "query_failed"
    assert result.sql_query == "" and result.data == []
    assert result.explanation == outbound.message("query_failed")
    assert outbound.safe_answer(result) == outbound.message("query_failed")
    assert result.question == QUESTION and result.provider == "fake"
    assert result.retry_count == 2 and len(result.retry_history) == 2
    assert trace.stages["invariant"] == code
    assert result.tokens_used == 0 and result.usage_breakdown is None
    execution.mcp_client.call_tool.assert_not_awaited()
    rescue.assert_not_awaited()


async def test_invariant_refusal_accounts_for_trace_usage(execution):
    execution.provider.generate_content.return_value = AUDIT_407
    execution.provider.last_usage = SimpleNamespace(
        total=12, model="fake-model", input_tokens=7, output_tokens=5,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )
    trace = new_trace(QUESTION)
    trace.usage.append({"stage": "intent", "input_tokens": 3, "output_tokens": 1})
    result = await query(execution, trace=trace)
    assert result.error == "query_failed"
    assert result.tokens_used == 28  # intent + both SQL generation attempts
    assert result.usage_breakdown == trace.usage


async def test_no_point_in_time_columns_executes_as_before(execution, monkeypatch):
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: [])
    summable = Mock(side_effect=AssertionError("summable lookup without point-in-time columns"))
    monkeypatch.setattr(hybrid_flow, "_summable_columns", summable)
    execution.provider.generate_content.return_value = AUDIT_407
    result = await query(execution)
    assert result.error is None and result.sql_query == AUDIT_407
    assert call("execute_query", {"sql": AUDIT_407, "limit": 1000, "validate_first": False}) in (
        execution.mcp_client.call_tool.await_args_list)
    summable.assert_not_called()


async def test_later_validation_failure_keeps_existing_final_result(execution):
    execution.provider.generate_content.side_effect = [AUDIT_407, SINGLE_PERIOD]
    execution.mcp_client.call_tool.return_value = {"valid": False, "issues": ["invalid column"]}
    execution.mcp_client.call_tool.side_effect = None
    trace = new_trace(QUESTION)
    result = await query(execution, trace=trace)
    assert result.error == "Max retries exceeded"
    assert result.sql_query == SINGLE_PERIOD
    assert result.explanation == "ไม่สามารถสร้าง SQL ที่ถูกต้องได้หลังจากลอง 2 ครั้ง"
    assert result.retry_history[0]["error"].startswith("I1 ytd_summed_across_periods: ")
    assert result.retry_history[-1]["error"] == "Validation failed: ['invalid column']"
    assert "invariant" not in trace.stages
    execution.mcp_client.call_tool.assert_awaited_once_with("validate_sql", {"sql": SINGLE_PERIOD})


@pytest.mark.parametrize("error,expected", [
    ("I1 ytd_summed_across_periods: guidance", "I1"),
    ("I2 ytd_without_period: guidance", "I2"),
    ("I1 unrelated: guidance", None),
    ("I2 ytd_without_period_extra: guidance", None),
    ("I3 month_summed_as_ytd: guidance", None),
    ("Validation failed: I1 ytd_summed_across_periods: guidance", None),
    ("guard error", None),
])
def test_invariant_code_only_recognizes_our_blocking_messages(error, expected):
    assert hybrid_flow.invariant_code(error) == expected
