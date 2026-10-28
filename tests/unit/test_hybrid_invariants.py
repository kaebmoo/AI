"""Pass-2 invariant retries refuse the final violation before tool-loop rescue."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, call

import pytest
from sqlalchemy import create_engine, text

from app.core import outbound
from app.services.ai import hybrid_flow, retry_loop
from app.services.ai.trace import new_trace


QUESTION = "EBT รายศูนย์ต้นทุน"
AUDIT_407 = ("SELECT cost_center, SUM(COALESCE(ebt, 0)) FROM t "
             "WHERE CAST(time_key AS INTEGER) BETWEEN 202601 AND 202609 GROUP BY cost_center")
SINGLE_PERIOD = "SELECT cost_center, SUM(COALESCE(ebt, 0)) FROM t WHERE time_key = 202609 GROUP BY cost_center"
NO_PERIOD = "SELECT cost_center, ebt FROM t WHERE cost_center = '1'"
ROWS = [{"cost_center": "1", "ebt": 59}]


def test_double_columns_use_active_schema_metadata(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'c.db'}")
    with engine.begin() as conn:
        conn.execute(text(
            "CREATE TABLE schema_metadata (table_name TEXT, column_name TEXT, data_type TEXT, "
            "is_summable INTEGER, status TEXT)"
        ))
        conn.execute(text(
            "INSERT INTO schema_metadata VALUES "
            "('t', 'amount_ytd', 'double', 0, 'active'), "
            "('t', 'amount', 'double', 1, 'active'), "
            "('t', 'old_ytd', 'double', 0, 'rejected'), "
            "('t', 'name', 'string', 0, 'active')"
        ))
    monkeypatch.setattr(hybrid_flow, "_context_tables", lambda *a: {})
    try:
        assert hybrid_flow._cumulative_columns("t", engine) == ["amount_ytd"]
        assert hybrid_flow._summable_columns("t", engine) == ["amount"]
    finally:
        engine.dispose()


@pytest.fixture
def execution(monkeypatch):
    monkeypatch.setattr(hybrid_flow, "_context_tables", lambda *a: {})
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: ["ebt"])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda *a: ["ebt_month"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda *a: ["time_key"])
    monkeypatch.setattr(hybrid_flow, "_grain_keys", lambda *a: {})
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
    ("I4 avg_over_fact_rows: guidance", "I4"),
    ("I5 month_outside_reference_year: guidance", "I5"),
    ("I1 unrelated: guidance", None),
    ("I2 ytd_without_period_extra: guidance", None),
    ("I3 month_summed_as_ytd: guidance", None),
    ("Validation failed: I1 ytd_summed_across_periods: guidance", None),
    ("guard error", None),
])
def test_invariant_code_only_recognizes_our_blocking_messages(error, expected):
    assert hybrid_flow.invariant_code(error) == expected


# I4 avg_over_fact_rows (plan/PLAN_ANOMALY_AVG_FIX.md §4): feed_sales has no point-in-time column, so before
# I4 its SQL never reached the checker (F10) — audit 518 averaged raw rows and was answered.
ROW_AVERAGE = ("SELECT unit_fname, AVG(amount) FROM t WHERE metric = 'actual' "
               "AND year_month BETWEEN 202601 AND 202608 GROUP BY unit_fname")
MONTHLY_AVERAGE = ("WITH m AS (SELECT unit_fname, year_month, SUM(amount) AS amt FROM t WHERE metric = 'actual' "
                   "AND year_month BETWEEN 202601 AND 202608 GROUP BY 1, 2) "
                   "SELECT unit_fname, SUM(amt) / 8 FROM m GROUP BY unit_fname")
SALES_KEYS = ("year_month", "cost_center", "product_code", "metric", "sales_line")


@pytest.fixture
def sales(execution, monkeypatch):
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: [])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda *a: ["amount"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda *a: ["year_month"])
    monkeypatch.setattr(hybrid_flow, "_grain_keys", lambda *a: {"t": SALES_KEYS})
    return execution


async def test_context_without_point_in_time_still_gets_i4(sales):
    sales.provider.generate_content.side_effect = [ROW_AVERAGE, MONTHLY_AVERAGE]
    result = await query(sales)
    assert result.error is None and result.sql_query == MONTHLY_AVERAGE and result.retry_count == 1
    error = result.retry_history[0]["error"]
    assert error.startswith("I4 avg_over_fact_rows: AVG(amount) บนแถวดิบของ t "
                            "(grain: year_month, cost_center, product_code, metric, sales_line)")
    assert "SUM ต่อมิติที่ถาม × year_month ใน CTE ก่อน" in error and "เดือนที่ไม่มีแถวนับเป็น 0" in error
    assert error in sales.provider.generate_content.await_args_list[1].args[0]


@pytest.mark.parametrize("rescue_enabled", [False, True])
async def test_last_i4_fails_closed(sales, monkeypatch, rescue_enabled):
    sales.provider.generate_content.return_value = ROW_AVERAGE
    rescue = AsyncMock()
    monkeypatch.setattr(retry_loop, "query_with_retry", rescue)
    trace = new_trace(QUESTION)
    result = await query(sales, trace=trace, escalation_tool_loop_enabled=rescue_enabled)
    assert result.error == "query_failed" and result.sql_query == "" and result.data == []
    assert trace.stages["invariant"] == "I4"
    sales.mcp_client.call_tool.assert_not_awaited()
    rescue.assert_not_awaited()


def test_grain_keys_come_from_the_contract_and_follow_its_changes(tmp_path):
    import os

    contract = tmp_path / "sales.yaml"
    contract.write_text("domain: sales\ndatasets:\n- name: fact_sales\n  keys: [year_month, cost_center]\n"
                        "- name: dim_product\n  keys: [product_code]\n- name: notes\n")
    engine = create_engine(f"sqlite:///{tmp_path/'c.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE data_sources (id INTEGER, contract_file TEXT)"))
        conn.execute(text("CREATE TABLE schema_contexts (main_view TEXT, source_id INTEGER, is_active INTEGER, "
                          "status TEXT)"))
        conn.execute(text("INSERT INTO data_sources VALUES (1, :p), (2, NULL)"), {"p": str(contract)})
        conn.execute(text("INSERT INTO schema_contexts VALUES ('feed_sales_fact_sales', 1, 1, 'active'), "
                          "('legacy_view', 2, 1, 'active')"))
    try:
        assert hybrid_flow._grain_keys("feed_sales_fact_sales", engine) == {
            "feed_sales_fact_sales": ("year_month", "cost_center"), "feed_sales_dim_product": ("product_code",)}
        contract.write_text("domain: sales\ndatasets:\n- name: fact_sales\n  keys: [year_month]\n")
        stat = contract.stat()
        os.utime(contract, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        assert hybrid_flow._grain_keys("feed_sales_fact_sales", engine) == {"feed_sales_fact_sales": ("year_month",)}
        assert hybrid_flow._grain_keys("legacy_view", engine) == {}
        assert hybrid_flow._grain_keys("unknown", engine) == {}
        contract.unlink()
        assert hybrid_flow._grain_keys("feed_sales_fact_sales", engine) == {}
    finally:
        engine.dispose()


# I5 month_outside_reference_year (plan §5): audit 518 asked "เดือน กันยายน" from the Sep 2569 sales report
# (scope 202501..202609) and was answered from 202509 — a month without a year is the latest one up to the
# reference period.
INCIDENT = "เดือน กันยายน มีรายได้ของหน่วยงานไหน ผิดปกติไปจากค่าเฉลี่ยก่อนหน้าบ้าง"
PORTAL_SCOPE = {"year_month": [*range(202501, 202513), *range(202601, 202610)]}
SEP_2025 = ("WITH m AS (SELECT unit_fname, year_month, SUM(amount) AS amt FROM t WHERE metric = 'actual' "
            "AND year_month BETWEEN 202501 AND 202509 GROUP BY 1, 2) "
            "SELECT unit_fname, SUM(amt) FILTER (WHERE year_month = 202509), "
            "SUM(amt) FILTER (WHERE year_month < 202509) / 8 FROM m GROUP BY unit_fname")
SEP_2026 = SEP_2025.replace("2025", "2026")


@pytest.fixture
def portal_scope():
    from app.services.data_sources import request_scope

    token = request_scope.set(PORTAL_SCOPE)
    yield
    request_scope.reset(token)


@pytest.mark.parametrize("question,sql,expected", [
    (INCIDENT, SEP_2025, "เดือนกันยายนที่ไม่ระบุปี = 202609 (งวดอ้างอิง 202609)"),
    (INCIDENT, SEP_2026, None),
    ("ยอดขาย ก.ย. ของทั้งสองปี", "SELECT year_month, SUM(amount) FROM t WHERE year_month IN (202509, 202609) GROUP BY 1",
     None),
    ("ยอดขาย ก.ย. รายหน่วยงาน", "SELECT SUM(amount) FROM t WHERE year_month = 202509", "= 202609"),
    ("ยอดขายเดือนธันวาคม", "SELECT SUM(amount) FROM t WHERE year_month = 202512", None),
    ("ยอดขายเดือนธันวาคม", "SELECT SUM(amount) FROM t WHERE year_month = 202612",
     "เดือนธันวาคมที่ไม่ระบุปี = 202512 (งวดอ้างอิง 202609)"),
    ("ยอดขายมกราคมถึงสิงหาคม", "SELECT SUM(amount) FROM t WHERE year_month BETWEEN 202501 AND 202508", "= 202601"),
    ("ยอดขายเดือนกันยายน 2568", SEP_2025, None),
    ("ยอดขายเดือนกันยายนปี 68", SEP_2025, None),
    ("ยอดขายเดือนกันยายน 2025", SEP_2025, None),
    ("ยอดขายกันยายนเทียบปีก่อน", "SELECT SUM(amount) FROM t WHERE year_month = 202509", None),
    ("ยอดขายกันยายนปีที่แล้ว", "SELECT SUM(amount) FROM t WHERE year_month = 202509", None),
    ("ยอดขายกันยายน YoY", "SELECT SUM(amount) FROM t WHERE year_month = 202509", None),
    ("ยอดขายรายเดือน", SEP_2025, None),
    (INCIDENT, "SELECT SUM(amount) FROM t WHERE year = 2025 AND month = 9", None),
])
def test_month_without_a_year_is_the_reference_year(portal_scope, question, sql, expected):
    error = hybrid_flow.unasked_year_error(question, sql)
    if expected is None:
        assert error is None
    else:
        assert error.startswith("I5 month_outside_reference_year: ") and expected in error


def test_no_reference_period_no_check():
    from app.services.data_sources import request_data_period

    assert hybrid_flow.unasked_year_error(INCIDENT, SEP_2025) is None
    token = request_data_period.set(202609)  # chat / Telegram: the source's data period
    try:
        assert hybrid_flow.unasked_year_error(INCIDENT, SEP_2025).startswith("I5 ")
    finally:
        request_data_period.reset(token)


async def ask_incident(service, **kwargs):
    return await hybrid_flow.query_hybrid(
        service, INCIDENT, "system", context_name="feed_sales", max_retries=1,
        two_pass_enabled=True, value_verification_enabled=False, **kwargs,
    )


async def test_i5_retry_answers_from_the_reference_year(sales, portal_scope):
    sales.provider.generate_content.side_effect = [SEP_2025, SEP_2026]
    result = await ask_incident(sales)
    assert result.error is None and result.sql_query == SEP_2026 and result.retry_count == 1
    assert result.retry_history[0]["error"].startswith(
        "I5 month_outside_reference_year: เดือนกันยายนที่ไม่ระบุปี = 202609 (งวดอ้างอิง 202609) — ใช้ 202609")
    assert result.retry_history[0]["error"] in sales.provider.generate_content.await_args_list[1].args[0]


async def test_last_i5_fails_closed(sales, portal_scope):
    sales.provider.generate_content.return_value = SEP_2025
    trace = new_trace(INCIDENT)
    result = await ask_incident(sales, trace=trace)
    assert result.error == "query_failed" and trace.stages["invariant"] == "I5"
    sales.mcp_client.call_tool.assert_not_awaited()
