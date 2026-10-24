"""Declared metric intent selection and compilation bypass SQL generation only."""

from dataclasses import fields, replace
from pathlib import Path
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
import yaml

from app.services.ai import hybrid_flow, metric_compiler as compiler


QUESTION = "ebt ของน่าน ถ้าไม่รวมค่าใช้จ่ายบุคลากร"
FILTER = {"column": "sub_unit", "operator": "=", "value": "ส่วนขายและบริการลูกค้า น่าน"}
OLD_RULES = """**กฎสำคัญ:**
1. ตรวจสอบ semantic mappings ใน system prompt ก่อน -- ถ้ามี keyword ที่ตรง ให้ใส่ใน matched_mappings พร้อม sql_condition ที่คัดลอกมาจาก mapping
2. ถ้า User ระบุปี พ.ศ. ให้แปลงเป็น ค.ศ. (พ.ศ. - 543) ใส่ใน time_range.year
3. ถ้าไม่แน่ใจค่า filter ให้ใช้ LIKE operator
4. **Follow-up context**: ถ้ามีประวัติสนทนาก่อนหน้า ให้ใช้เป็นบริบท เช่น ถ้าถามก่อนหน้าเรื่อง "ค่าล่วงเวลา" แล้วถาม "ค่าเฉลี่ยเท่าไหร่" → ต้อง inherit filter "ค่าล่วงเวลา" จากคำถามก่อนหน้าด้วย
5. ห้ามสร้าง SQL -- ระบุเฉพาะ intent เท่านั้น"""


@pytest.fixture
def metrics():
    contract = yaml.safe_load((Path(__file__).parents[1] / "fixtures/ebt_metrics_1_6_0.yaml").read_text())
    rows = []
    for declaration in contract["metrics"]:
        values = {f.name: declaration.get(f.name) for f in fields(compiler.Metric)}
        values["metric_id"] = declaration["id"]
        values["synonyms"] = tuple(values["synonyms"] or ())
        values["dimensions"] = tuple(values["dimensions"]) if values["dimensions"] is not None else None
        values["terms"] = values["terms"] or {}
        if values["dataset"] is not None:
            values["dataset"] = f"feed_{contract['domain']}_{values['dataset']}"
        if values["official_total"] is not None:
            total = values["official_total"]
            values["official_total"] = {**total, "dataset": f"feed_{contract['domain']}_{total['dataset']}"}
        rows.append(compiler.Metric(**values))
    return rows


@pytest.fixture
def intent():
    return {"intent_type": "aggregation", "metric_id": "ebt_excluding_personnel",
            "metrics": [], "dimensions": [], "filters": [dict(FILTER)],
            "time_range": {"year": 2026, "month": 9, "cumulative": True}}


@pytest.fixture(autouse=True)
def isolated_context(monkeypatch):
    monkeypatch.setattr(hybrid_flow, "_context_tables", lambda *a: {})
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: [])
    monkeypatch.setattr(hybrid_flow, "reference_period", lambda: 202609)
    monkeypatch.setattr(hybrid_flow, "scope_note", lambda: "")
    monkeypatch.setattr(hybrid_flow, "intent_period_note", lambda: "")
    monkeypatch.setattr(hybrid_flow, "get_column_hierarchies", lambda: {})


class _Provider:
    last_usage = None

    def __init__(self, intent):
        self.intent = intent
        self.prompts = []
        self.text_prompts = []

    async def generate_structured(self, prompt, *a, **kw):
        self.prompts.append(prompt)
        return self.intent

    async def generate_content(self, prompt, *a, **kw):
        self.text_prompts.append(prompt)
        return "not json"

    async def explain_result(self, question, *a, **kw):
        self.explanation_question = question
        return "คำอธิบาย"


def _service(intent):
    return SimpleNamespace(
        provider=_Provider(intent), provider_name="fake", parse_intent_json=lambda text: None,
        format_value_matches=lambda *a, **kw: "", get_pending_limit_warning=lambda: "",
        set_pending_limit_warning=lambda warning: None,
    )


async def _first(service, **kwargs):
    return await hybrid_flow.build_first_attempt_prompt(
        service=service, question=QUESTION, system_prompt="system", history=None,
        context_name="feed_ebt", context_table="feed_ebt_fact_ebt", context_thai="EBT",
        two_pass_enabled=True, cheap_model=None, detect_hierarchy_level=lambda *a: None,
        format_value_matches=service.format_value_matches, get_vanna_context_string=lambda q: "",
        lookup_values_from_question=lambda *a: [], on_status=None, attempt=0, max_retries=1,
        **kwargs,
    )


def test_metric_id_schema_is_optional():
    assert hybrid_flow.INTENT_SCHEMA["properties"]["metric_id"] == {"type": ["string", "null"]}
    assert "metric_id" not in hybrid_flow.INTENT_SCHEMA["required"]
    assert hybrid_flow._intent_rules() == OLD_RULES


async def test_no_metrics_keeps_the_previous_header_and_text_schema(monkeypatch):
    loader = Mock(return_value=[])
    monkeypatch.setattr(compiler, "load_metrics", loader)
    service = _service(None)
    prompt, two_pass, compiled = await _first(service)
    header = service.provider.prompts[0]
    assert header == (f"คำถาม: {QUESTION}\n\n**บริบท:** ข้อมูลEBT (ใช้ตาราง feed_ebt_fact_ebt)"
                      f"\n\n\n\n---\n**Task:** วิเคราะห์คำถามข้างต้นและระบุ intent\n\n{OLD_RULES}")
    for text in [header, *service.provider.text_prompts]:
        assert "metric ที่ประกาศ" not in text and "\n6." not in text and '"metric_id"' not in text
    assert prompt and not two_pass and compiled is None
    loader.assert_called_once_with("feed_ebt")


async def test_catalog_and_specific_match_reach_pass_one_only(metrics, intent, monkeypatch):
    monkeypatch.setattr(compiler, "load_metrics", Mock(return_value=metrics))
    monkeypatch.setattr(compiler, "dimension_labels", Mock(return_value={"unit": "ฝ่าย"}))
    trace = SimpleNamespace(stages={}, usage=[])
    service = _service(intent)
    prompt, two_pass, compiled = await _first(service, trace=trace)
    header = service.provider.prompts[0]
    assert compiler.metric_catalog(metrics, {"unit": "ฝ่าย"}) in header
    assert "unit (ฝ่าย)" in header and "sub_unit" in header  # ฝ่ายไหน… → dimensions=["unit"], not division
    assert "metric ที่ประกาศไว้และตรงกับคำในคำถาม: ebt = " in header
    assert "ebt_excluding_personnel = EBT ไม่รวมค่าใช้จ่ายบุคลากร" in header
    assert "\n6. ถ้ามีรายการ" in header
    assert all(formula not in header for formula in ("measure_type", "SUM(", "rev - other"))
    assert isinstance(compiled, compiler.Compiled) and two_pass and prompt == ""
    assert '"sub_unit" = \'ส่วนขายและบริการลูกค้า น่าน\'' in compiled.sql
    assert 'AS "EBT ไม่รวมค่าใช้จ่ายบุคลากร"' in compiled.sql
    assert service.provider.text_prompts == []
    assert trace.stages["metric_compiled"] == "ebt_excluding_personnel"


@pytest.mark.parametrize("previous_intent", [None, {"intent_type": "aggregation"}])
async def test_metric_header_and_schema_in_fresh_and_followup(metrics, previous_intent):
    service = _service(None)
    note = "\nmetric ที่ประกาศของ context นี้:\n" + compiler.metric_catalog(metrics)
    await hybrid_flow.extract_intent(
        service, QUESTION, "system", "feed_ebt", "feed_ebt_fact_ebt", "EBT", "", "",
        previous_intent=previous_intent, value_note="VALUE", metric_note=note,
    )
    assert "VALUE" + note in service.provider.prompts[0]
    assert "\n6. ถ้ามีรายการ" in service.provider.prompts[0]
    assert '"metric_id": "id ของ metric ที่ประกาศ หรือ null"' in service.provider.text_prompts[0]


@pytest.mark.parametrize("changes", [
    {"intent_type": "trend"}, {"matched_mappings": [{"keyword": "น่าน", "sql_condition": "x = 1"}]},
    {"metric_id": "bogus"},
])
def test_plan_rejects_unsupported_selection(metrics, intent, changes):
    assert compiler.plan(intent | changes, QUESTION, compiler.resolve(metrics), [], 202609, set()) is None


@pytest.mark.parametrize("mappings,blocked", [
    ([{"keyword": "สายงาน", "sql_condition": "DIVISION LIKE '%สายงาน%'"}], False),
    ([{"keyword": "น่าน", "sql_condition": "DIVISION LIKE '%สายงาน%'"}], True),
    ([{"keyword": None}, "x"], False),
    ([{}, {"keyword": ""}, {"keyword": "   "}], False),
    ([{"keyword": " EBT "}], False),
    ([{"keyword": " น่าน "}], True),
])
def test_plan_ignores_mappings_the_question_did_not_trigger(metrics, intent, mappings, blocked):
    filters = [{"column": "sub_unit", "operator": "LIKE", "value": "%น่าน%"}]
    smoke_intent = intent | {"metric_id": "ebt_ex_personnel", "filters": filters,
                             "matched_mappings": mappings}
    req = compiler.plan(smoke_intent, QUESTION + " จะเป็นเท่าไหร่", compiler.resolve(metrics),
                        ["ebt", "ebt_excluding_personnel"], 202609, set())
    expected = compiler.CompileRequest("ebt_excluding_personnel", 202609, "cumulative",
                                       filters=tuple(filters), official_total_ok=False)
    assert req == (None if blocked else expected)


@pytest.mark.parametrize("extra_mapping", [False, True])
def test_plan_ignores_metric_mappings_but_other_triggered_mappings_block(metrics, intent, extra_mapping):
    question = "ถ้าไม่รวมค่าใช้จ่ายบุคลากร จะมี EBT เป็นเท่าไหร่ แบบสะสม"
    mappings = [{"keyword": "EBT", "sql_condition": "ebt"},
                {"keyword": "ไม่รวมค่าใช้จ่ายบุคลากร", "sql_condition": "x"}]
    if extra_mapping:
        mappings.append({"keyword": "แบบสะสม", "sql_condition": "..."})
    selection = intent | {"filters": [{"column": "time_key", "operator": "=", "value": 202609}],
                          "matched_mappings": mappings}
    req = compiler.plan(selection, question, compiler.resolve(metrics), [], 202609, set())
    expected = compiler.CompileRequest("ebt_excluding_personnel", 202609, "cumulative",
                                       filters=(), official_total_ok=False)
    assert req == (None if extra_mapping else expected)


def test_plan_ignores_parent_synonym_mapping(metrics, intent):
    selection = intent | {"metric_id": "ebt_margin", "filters": [],
                          "matched_mappings": [{"keyword": "กำไร", "sql_condition": "x"}]}
    req = compiler.plan(selection, "อัตรากำไร EBT ของกำไรสะสม", compiler.resolve(metrics), [], 202609, set())
    assert req == compiler.CompileRequest("ebt_margin", 202609, "cumulative", official_total_ok=False)


def test_plan_period_filters_and_official_table_registration(metrics, intent):
    resolved = compiler.resolve(metrics)
    total = resolved[intent["metric_id"]].official_total["dataset"]
    req = compiler.plan(intent, QUESTION, resolved, [], 202609, {total})
    assert req == compiler.CompileRequest("ebt_excluding_personnel", 202609, "cumulative",
                                          filters=(FILTER,), official_total_ok=True)
    assert not compiler.plan(intent, QUESTION, resolved, [], 202609, set()).official_total_ok
    assert not compiler.plan(intent | {"metric_id": "ebt_margin"}, QUESTION, resolved, [], 202609, {total}).official_total_ok


@pytest.mark.parametrize("metric_id", [None, "bogus"])
def test_plan_prefers_the_matching_child(metrics, intent, metric_id):
    req = compiler.plan(intent | {"metric_id": metric_id}, QUESTION, compiler.resolve(metrics),
                        ["ebt", "ebt_excluding_personnel"], 202609, set())
    assert req.metric_id == "ebt_excluding_personnel"


@pytest.mark.parametrize("time_range,period,mode", [
    (None, 202609, "cumulative"), ({"year": 2026, "month": 12}, 202609, "month"),
    ({"year": 2025, "month": 12, "cumulative": False}, 202512, "month"),
    ({"year": 2025}, 202509, "cumulative"),
])
def test_plan_period_selection(metrics, intent, time_range, period, mode):
    req = compiler.plan(intent | {"time_range": time_range}, QUESTION, compiler.resolve(metrics), [], 202609, set())
    assert (req.period, req.mode) == (period, mode)


@pytest.mark.parametrize("column,value", [("time_key", 202609), ("time_key", "202609"), ("TIME_KEY", 202609)])
def test_plan_removes_period_filters_without_mutating_intent(metrics, intent, column, value):
    period_filter = {"column": column, "operator": "=", "value": value}
    selection = intent | {"filters": [dict(period_filter)]}
    req = compiler.plan(selection, QUESTION, compiler.resolve(metrics), [], 202609, set())
    assert req == compiler.CompileRequest("ebt_excluding_personnel", 202609, "cumulative",
                                          official_total_ok=False)
    assert selection == intent | {"filters": [period_filter]}


@pytest.mark.parametrize("operator,value", [
    ("<", 202609), ("BETWEEN", [202607, 202609]), ("=", "2026-09"),
    ("=", 100000), ("=", 999913), ("=", 202609.0), ("=", None),
])
def test_plan_rejects_unsupported_period_filters(metrics, intent, operator, value):
    selection = intent | {"filters": [{"column": "time_key", "operator": operator, "value": value}]}
    assert compiler.plan(selection, QUESTION, compiler.resolve(metrics), [], 202609, set()) is None


@pytest.mark.parametrize("time_range,hint,period,mode", [
    (None, 202507, 202507, "cumulative"),
    ({"year": 2026, "month": 9, "cumulative": False}, 202609, 202609, "month"),
    ({"year": 2026, "month": 9, "cumulative": True}, 202507, 202609, "cumulative"),
    ({"year": 2025}, 202607, 202507, "cumulative"),
    ({"month": 8}, 202507, 202508, "month"),
    (None, 202612, 202609, "cumulative"),
    (None, 202513, None, None),
])
def test_plan_period_hint_precedence_and_mode(metrics, intent, time_range, hint, period, mode):
    selection = intent | {"time_range": time_range,
                          "filters": [{"column": "time_key", "operator": "=", "value": hint}]}
    req = compiler.plan(selection, QUESTION, compiler.resolve(metrics), [], 202609, set())
    if period is None:
        assert req is None
    else:
        assert (req.period, req.mode, req.filters) == (period, mode, ())


def test_plan_last_period_hint_wins_and_preserves_dimension_filters(metrics, intent):
    filters = [{"column": "time_key", "operator": "=", "value": 202501}, dict(FILTER),
               {"column": "time_key", "operator": "=", "value": "202507"}]
    selection = intent | {"time_range": None, "filters": filters}
    req = compiler.plan(selection, QUESTION, compiler.resolve(metrics), [], 202609, set())
    assert req == compiler.CompileRequest("ebt_excluding_personnel", 202507, "cumulative",
                                          filters=(FILTER,), official_total_ok=False)


@pytest.mark.parametrize("metric_id,expected", [
    ("ebt_ex_personnel", "ebt_excluding_personnel"),
    ("ebt_ex_personnel_month", "ebt_excluding_personnel"),
    ("EBT_EX_PERSONNEL", "ebt_excluding_personnel"),
    ("ebt", "ebt"), ("unknown_col", None),
])
def test_plan_resolves_official_total_column_names(metrics, intent, metric_id, expected):
    req = compiler.plan(intent | {"metric_id": metric_id}, QUESTION, compiler.resolve(metrics), [], 202609, set())
    if expected is None:
        assert req is None
    else:
        assert req.metric_id == expected and req.mode == "cumulative"


def test_plan_month_column_name_uses_time_range_mode(metrics, intent):
    selection = intent | {"metric_id": "ebt_ex_personnel_month",
                          "time_range": {"year": 2026, "month": 9, "cumulative": False}}
    req = compiler.plan(selection, QUESTION, compiler.resolve(metrics), [], 202609, set())
    assert (req.metric_id, req.mode) == ("ebt_excluding_personnel", "month")


def test_plan_column_alias_must_be_unique_and_metric_id_wins(metrics, intent):
    resolved = compiler.resolve(metrics)
    total = {**resolved["ebt"].official_total, "column": "ebt_ex_personnel"}
    resolved["ebt"] = replace(resolved["ebt"], official_total=total)
    selection = intent | {"metric_id": "ebt_ex_personnel"}
    assert compiler.plan(selection, QUESTION, resolved, [], 202609, set()) is None
    assert compiler.plan(selection, QUESTION, resolved, ["ebt"], 202609, set()).metric_id == "ebt"
    resolved["ebt_excluding_personnel"] = replace(resolved["ebt_excluding_personnel"],
                                                 official_total={**total, "column": "ebt"})
    assert compiler.plan(intent | {"metric_id": "ebt"}, QUESTION, resolved, [], 202609, set()).metric_id == "ebt"


def test_supports_still_rejects_period_filters(metrics, intent):
    selection = intent | {"filters": [{"column": "time_key", "operator": "=", "value": 202609}]}
    assert not compiler.supports(selection, compiler.resolve(metrics)[intent["metric_id"]])


@pytest.mark.parametrize("time_range", [
    {"year": "2026"}, {"year": True}, {"year": -1}, {"year": 10000},
    {"month": "9"}, {"month": True}, {"month": -1}, {"month": 13},
])
def test_plan_rejects_invalid_period_values(metrics, intent, time_range):
    assert compiler.plan(intent | {"time_range": time_range}, QUESTION, compiler.resolve(metrics), [], 202609, set()) is None


@pytest.mark.parametrize("direction,expected", [(None, True), ("ASC", False), ("DESC", True)])
def test_plan_ranking(metrics, intent, direction, expected):
    ranking = intent | {"intent_type": "ranking", "limit": 3, "dimensions": ["division"],
                        "ordering": {"direction": direction} if direction else None}
    req = compiler.plan(ranking, QUESTION, compiler.resolve(metrics), [], 202609, set())
    assert req.order_desc is expected and req.limit == 3 and req.dimensions == ("division",)


@pytest.mark.parametrize("limit", [None, 0, -1, True, "3"])
def test_plan_ignores_invalid_limits(metrics, intent, limit):
    assert compiler.plan(intent | {"limit": limit}, QUESTION, compiler.resolve(metrics), [], 202609, set()).limit is None


def test_plan_needs_a_reference_and_honors_explicit_selection(metrics, intent):
    resolved = compiler.resolve(metrics)
    assert compiler.plan(intent, QUESTION, resolved, [], None, set()) is None
    assert compiler.plan(intent | {"metric_id": "ebt"}, QUESTION, resolved,
                         ["ebt_excluding_personnel"], 202609, set()).metric_id == "ebt"


async def test_unsupported_shape_keeps_pass_two(metrics, intent, monkeypatch):
    monkeypatch.setattr(compiler, "load_metrics", lambda c: metrics)
    service = _service(intent | {"intent_type": "trend"})
    prompt, two_pass, compiled = await _first(service)
    assert compiled is None and two_pass and "Structured Intent" in prompt


async def test_compile_failure_keeps_pass_two(metrics, intent, monkeypatch, caplog):
    monkeypatch.setattr(compiler, "load_metrics", lambda c: metrics)
    monkeypatch.setattr(compiler, "compile", Mock(side_effect=ValueError("bad declaration")))
    prompt, two_pass, compiled = await _first(_service(intent))
    assert compiled is None and two_pass and "Structured Intent" in prompt
    assert "Metric compilation failed" in caplog.text


def _attempt_kwargs(service, compiled, trace=None):
    return dict(
        service=service, question=QUESTION, system_prompt="system", history=None, on_status=None,
        context_name="feed_ebt", context_table="feed_ebt_fact_ebt", attempt=0, max_retries=1,
        value_verification_enabled=False, cheap_model=None, user_prompt="", temp_schema=SimpleNamespace(),
        retry_history=[], total_tokens=7, extract_sql=Mock(side_effect=AssertionError("SQL extraction called")),
        extract_explanation=Mock(side_effect=AssertionError("response extraction called")),
        log_value_corrections=Mock(), prepare_data_for_explanation=lambda data, **kw: data,
        start_request=time.perf_counter(), precompiled=compiled, trace=trace, required_columns=["sub_unit"],
    )


@pytest.fixture
def compiled(metrics, intent):
    resolved = compiler.resolve(metrics)
    return compiler.compile(compiler.plan(intent, QUESTION, resolved, [], 202609, set()), resolved)


@pytest.fixture
def execution(monkeypatch, intent):
    service = _service(intent)
    service.provider.generate_content = AsyncMock(side_effect=AssertionError("SQL generation called"))

    async def call_tool(name, args):
        if name == "validate_sql":
            return {"valid": True}
        assert name == "execute_query"
        return {"success": True, "data": [{"EBT ไม่รวมค่าใช้จ่ายบุคลากร": 59}]}

    service.mcp_client = SimpleNamespace(servers={"nt-query": object()}, call_tool=AsyncMock(side_effect=call_tool))
    monkeypatch.setattr(hybrid_flow, "load_execution_metadata", lambda *a: (None, None, None))
    return service


@pytest.mark.parametrize("official", [False, True])
async def test_precompiled_execution_skips_generation_and_explains_metric(execution, compiled, official):
    compiled = replace(compiled, official=official)
    result, total, sql = await hybrid_flow.run_hybrid_attempt(**_attempt_kwargs(execution, compiled))
    execution.provider.generate_content.assert_not_awaited()
    assert result.sql_query == sql == compiled.sql and total == 7
    assert result.metric == {"id": "ebt_excluding_personnel", "name_th": compiled.name_th,
                             "unit": compiled.unit, "official": official, "table": compiled.table}
    assert result.question == QUESTION
    unit = f" หน่วย: {compiled.unit}" if compiled.unit else ""
    expected_question = (f"{QUESTION}\n(ตัวชี้วัดที่ใช้: {compiled.name_th}{unit} — {compiled.note_th}"
                         + (" ; ยอดทางการตามขอบเขตของ metric" if official
                            else " ; ยอดเฉพาะมิติ/หน่วยงานที่กรอง ไม่ใช่ยอดทางการ") + ")")
    assert execution.provider.explanation_question == expected_question
    assert [call.args[0] for call in execution.mcp_client.call_tool.await_args_list] == ["validate_sql", "execute_query"]


@pytest.mark.parametrize("guard", ["dropped_filter_error", "cumulative_sum_error"])
async def test_precompiled_sql_still_runs_guards(execution, compiled, monkeypatch, guard):
    check = Mock(return_value="guard error")
    monkeypatch.setattr(hybrid_flow, guard, check)
    kwargs = _attempt_kwargs(execution, compiled)
    result, total, sql = await hybrid_flow.run_hybrid_attempt(**kwargs)
    assert result is None and sql == compiled.sql and total == 7
    assert kwargs["retry_history"] == [{"sql": compiled.sql, "error": "guard error"}]
    assert check.call_args.args[0] == compiled.sql
    execution.mcp_client.call_tool.assert_not_awaited()


async def test_failed_compilation_execution_retries_with_provider_once(execution, metrics, intent, monkeypatch):
    loader = Mock(return_value=metrics)
    monkeypatch.setattr(compiler, "load_metrics", loader)
    monkeypatch.setattr(hybrid_flow, "resolve_context_info", lambda *a, **kw: (
        SimpleNamespace(get_context_info=lambda c: {}), "feed_ebt_fact_ebt", "EBT"))
    execution.get_vanna_context_string = lambda q: ""
    execution.lookup_values_from_question = lambda *a: []
    execution.detect_hierarchy_level = lambda *a: None
    execution.extract_sql = lambda text: text
    execution.extract_explanation = lambda text: ""
    execution.log_value_corrections = Mock()
    execution.prepare_data_for_explanation = lambda data, **kw: data
    execution.provider.generate_content = AsyncMock(return_value='SELECT 59 AS "EBT ไม่รวมค่าใช้จ่ายบุคลากร"')
    executions = []

    async def call_tool(name, args):
        if name == "validate_sql":
            return {"valid": True}
        assert name == "execute_query"
        executions.append(args["sql"])
        if len(executions) == 1:
            return {"success": False, "error": "retry me"}
        return {"success": True, "data": [{"EBT ไม่รวมค่าใช้จ่ายบุคลากร": 59}]}

    execution.mcp_client.call_tool = AsyncMock(side_effect=call_tool)
    result = await hybrid_flow.query_hybrid(execution, QUESTION, "system", max_retries=1,
                                            two_pass_enabled=True, value_verification_enabled=False,
                                            context_name="feed_ebt")
    loader.assert_called_once_with("feed_ebt")
    execution.provider.generate_content.assert_awaited_once()
    assert len(execution.provider.prompts) == 1 and result.retry_count == 1
    assert result.metric is None and result.sql_query == executions[1]
    assert result.retry_history == [{"sql": executions[0], "error": "Execution failed: retry me"}]
    assert executions[0] != executions[1]


RANKING = {"metric_id": "ebt", "dimensions": ["cost_center", "division"], "filters": []}


@pytest.mark.parametrize("changes,order_desc,limit", [
    ({"intent_type": "ranking", "ordering": {"column": "ebt", "direction": "DESC"}, "limit": 10}, True, 10),
    ({"intent_type": "aggregation", "ordering": {"column": "ebt", "direction": "DESC"}, "limit": 10}, True, 10),
    ({"intent_type": "aggregation", "ordering": {"column": "EBT (กำไรก่อนภาษี ตามรายงาน EBT)"}}, True, None),
    ({"intent_type": "aggregation", "ordering": {"column": "ebt", "direction": "ASC"}}, False, None),
    ({"intent_type": "aggregation", "limit": 10}, True, 10),
    ({"intent_type": "aggregation", "ordering": {"column": "division", "direction": "ASC"}}, None, None),
    ({"intent_type": "ranking", "ordering": None}, True, None),
])
def test_plan_ranks_by_the_metric_value(metrics, intent, changes, order_desc, limit):
    """หน่วยงานไหนได้ EBT สูงสุด 10 อันดับแรก — pass 1 names the value in `ordering.column`,
    or sends aggregation + limit; both compile with ORDER BY the value (query_audit 406/407)."""
    req = compiler.plan(intent | RANKING | changes, "ศูนย์ต้นทุนไหนมี EBT สะสมสูงสุด 10 อันดับแรก",
                        compiler.resolve(metrics), ["ebt"], 202609, set())
    assert req == compiler.CompileRequest("ebt", 202609, "cumulative", dimensions=("cost_center", "division"),
                                          order_desc=order_desc, limit=limit, official_total_ok=False)


def test_plan_ranks_child_metric_by_parent_name(metrics, intent):
    selection = intent | RANKING | {"metric_id": "ebt_excluding_personnel", "intent_type": "aggregation",
                                    "ordering": {"column": "ebt", "direction": "DESC"}}
    req = compiler.plan(selection, "EBT ไม่รวมบุคลากร รายศูนย์ต้นทุน", compiler.resolve(metrics), [], 202609, set())
    assert req is not None and req.order_desc is True


def test_plan_rejects_ordering_by_an_unknown_column(metrics, intent):
    selection = intent | RANKING | {"intent_type": "aggregation", "ordering": {"column": "revenue", "direction": "DESC"}}
    assert compiler.plan(selection, "EBT รายศูนย์ต้นทุน", compiler.resolve(metrics), [], 202609, set()) is None


@pytest.mark.parametrize("changes,question,reference,reason", [
    ({"metric_id": "unknown"}, QUESTION, 202609, "no_metric"),
    ({"matched_mappings": [{"keyword": " น่าน "}, {"keyword": "บุคลากร"}]},
     QUESTION, 202609, "mapping_triggered:น่าน"),
    ({"filters": "invalid"}, QUESTION, 202609, "shape:filter:invalid"),
    ({"filters": [None]}, QUESTION, 202609, "shape:filter:invalid"),
    ({"intent_type": "trend"}, QUESTION, 202609, "shape:intent_type:trend"),
    ({"intent_type": None}, QUESTION, 202609, "shape:intent_type:invalid"),
    ({"dimensions": "division"}, QUESTION, 202609, "shape:dimension:invalid"),
    ({"dimensions": [5]}, QUESTION, 202609, "shape:dimension:invalid"),
    ({"dimensions": ["  \n "]}, QUESTION, 202609, "shape:dimension:invalid"),
    ({"dimensions": ["division", "unknown", "other"]}, QUESTION, 202609, "shape:dimension:unknown"),
    ({"filters": [{"column": "unknown", "operator": ">", "value": "private"}]},
     QUESTION, 202609, "shape:filter:unknown"),
    ({"filters": [{"column": None, "operator": "="}]}, QUESTION, 202609, "shape:filter:invalid"),
    ({"filters": [{"column": "division", "operator": ">", "value": "private"}]},
     QUESTION, 202609, "shape:filter:>"),
    ({"filters": [{"column": "division", "operator": "=", "value": 5}]},
     QUESTION, 202609, "shape:filter:="),
    ({"filters": [{"column": "division", "operator": "LIKE", "value": None}]},
     QUESTION, 202609, "shape:filter:LIKE"),
    ({"filters": [{"column": "division", "operator": "IN", "value": []}]},
     QUESTION, 202609, "shape:filter:IN"),
    ({"filters": [{"column": "division", "operator": "IN", "value": ["private", 5]}]},
     QUESTION, 202609, "shape:filter:IN"),
    ({"filters": [{"column": "division", "operator": None, "value": "private"}]},
     QUESTION, 202609, "shape:filter:invalid"),
    ({"ordering": []}, QUESTION, 202609, "shape:ordering:invalid"),
    ({"ordering": {"column": "unknown", "direction": "invalid"}},
     QUESTION, 202609, "shape:ordering:unknown"),
    ({"ordering": {"column": 5}}, QUESTION, 202609, "shape:ordering:invalid"),
    ({"ordering": {"column": "division", "direction": "desc"}},
     QUESTION, 202609, "shape:ordering:direction"),
    ({"metrics": 5, "ordering": {"column": "ebt"}}, QUESTION, 202609, "shape:invalid"),
    ({}, QUESTION, None, "reference_missing"),
    ({}, QUESTION, "202609", "reference_missing"),
    ({}, QUESTION, True, "reference_missing"),
    ({}, QUESTION, 202600, "reference_missing"),
    ({}, QUESTION, 202613, "reference_missing"),
    ({}, QUESTION, 12, "reference_missing"),
    ({}, QUESTION, 1000001, "reference_missing"),
    ({"time_range": [1]}, QUESTION, 202609, "time_range_invalid"),
    ({"time_range": {"year": 10000}}, QUESTION, 202609, "time_range_invalid"),
    ({"time_range": {"month": 13}}, QUESTION, 202609, "time_range_invalid"),
    ({"time_range": {"year": "2026"}}, QUESTION, 202609, "time_range_invalid"),
    ({"time_range": {"month": True}}, QUESTION, 202609, "time_range_invalid"),
    *[pytest.param({"filters": [{"column": "time_key", "operator": operator, "value": value}]},
                   QUESTION, 202609, reason, id=case)
      for case, operator, value, reason in [
          ("period-operator", "<", 202609, "period_filter:operator"),
          ("period-operator-before-value", ">", [202601, 202609], "period_filter:operator"),
          ("period-nondecimal", "=", "2026-09", "period_filter:value"),
          ("period-too-small", "=", 100000, "period_filter:value"),
          ("period-too-large", "=", 999913, "period_filter:value"),
          ("period-bool", "=", True, "period_filter:value"),
          ("period-list", "=", [202609], "period_filter:value"),
          ("period-float", "=", 202609.0, "period_filter:value"),
          ("period-none", "=", None, "period_filter:value"),
          ("period-int-conversion", "=", "1" * 5000, "period_filter:value"),
      ]],
])
def test_plan_with_reason_declines(metrics, intent, changes, question, reference, reason):
    selection = intent | changes
    resolved = compiler.resolve(metrics)
    assert compiler.plan_with_reason(selection, question, resolved, [], reference, set()) == (None, reason)
    assert compiler.plan(selection, question, resolved, [], reference, set()) is None
    expected_support = not reason.startswith(("shape:", "period_filter:"))
    assert compiler.supports(selection, resolved[intent["metric_id"]]) is expected_support


@pytest.mark.parametrize("changes,matched", [
    ({}, []),
    ({"metric_id": "ebt_ex_personnel_month", "time_range": {"year": 2025, "month": 7}}, []),
    ({"metric_id": None}, ["ebt", "ebt_excluding_personnel"]),
    (RANKING | {"intent_type": "ranking", "ordering": {"column": "ebt", "direction": "ASC"}}, []),
])
def test_plan_with_reason_success_matches_plan(metrics, intent, changes, matched):
    selection = intent | changes
    resolved = compiler.resolve(metrics)
    request = compiler.plan(selection, QUESTION, resolved, matched, 202609, set())
    assert request is not None
    assert compiler.plan_with_reason(selection, QUESTION, resolved, matched, 202609, set()) == (request, None)
    assert compiler.supports(selection | {"filters": list(request.filters)}, resolved[request.metric_id])


def test_plan_with_reason_sanitizes_mapping_keyword(metrics, intent):
    keyword = "  MIXED\n  " + "Long   Keyword " * 10
    selection = intent | {"matched_mappings": [{"keyword": keyword, "sql_condition": "private SQL"}]}
    resolved = compiler.resolve(metrics)
    question = QUESTION + keyword
    expected = "mapping_triggered:" + " ".join(keyword.casefold().strip().split())[:64]
    assert compiler.plan_with_reason(selection, question, resolved, [], 202609, set()) == (None, expected)
    assert compiler.plan(selection, question, resolved, [], 202609, set()) is None
    assert len(expected.split(":", 1)[1]) <= 64
    assert "\n" not in expected and "private" not in expected


@pytest.mark.parametrize("time_range,reason", [(None, "time_range_invalid"), ({"year": 2026, "month": 9}, None)])
def test_plan_with_reason_preserves_period_hint_precedence(metrics, intent, time_range, reason):
    selection = intent | {"time_range": time_range,
                          "filters": [{"column": "time_key", "operator": "=", "value": 202513}]}
    resolved = compiler.resolve(metrics)
    request = compiler.plan(selection, QUESTION, resolved, [], 202609, set())
    assert compiler.plan_with_reason(selection, QUESTION, resolved, [], 202609, set()) == (request, reason)
    assert not compiler.supports(selection, resolved[intent["metric_id"]])
    if reason is None:
        assert request == compiler.CompileRequest(intent["metric_id"], 202609, "month", official_total_ok=False)
    else:
        assert request is None


@pytest.mark.parametrize("outcome,reason", [
    ("declined", "shape:intent_type:trend"), ("compile_error", "compile_error"), ("compiled", None),
])
@pytest.mark.parametrize("with_trace", [True, False])
async def test_metric_decline_trace_and_log(metrics, intent, monkeypatch, caplog, outcome, reason, with_trace):
    monkeypatch.setattr(compiler, "load_metrics", lambda c: metrics)
    monkeypatch.setattr(compiler, "dimension_labels", lambda *a: {})
    selection = intent | {"intent_type": "trend"} if outcome == "declined" else intent
    if outcome == "compile_error":
        monkeypatch.setattr(compiler, "compile", Mock(side_effect=ValueError("private declaration")))
    trace = SimpleNamespace(stages={}, usage=[]) if with_trace else None
    caplog.set_level("INFO", logger=hybrid_flow.__name__)
    prompt, two_pass, compiled = await _first(_service(selection), trace=trace)
    assert two_pass
    decline_lines = [record.getMessage() for record in caplog.records
                     if record.getMessage().startswith("Metric declined:")]
    if reason is None:
        assert compiled is not None and prompt == ""
        assert decline_lines == []
        if trace is not None:
            assert trace.stages["metric_compiled"] == intent["metric_id"]
            assert "metric_declined" not in trace.stages
    else:
        assert compiled is None and "Structured Intent" in prompt
        assert decline_lines == [f"Metric declined: {reason}"]
        if trace is not None:
            assert trace.stages["metric_declined"] == reason
            assert "metric_compiled" not in trace.stages
        if outcome == "compile_error":
            assert "Metric compilation failed: private declaration" in caplog.text


def _period(*items):
    return [{"column": "time_key", "operator": operator, "value": value} for operator, value in items]


YTD = {"year": 2026, "month": 9, "cumulative": True}
MONTH = {"year": 2026, "month": 9, "cumulative": False}


@pytest.mark.parametrize("period_filters,time_range,period,mode", [
    # "สะสมปี 2569" as pass 1 writes it (Phase D measurement: 39 BETWEEN, 6 >=/<= pairs, 1 <= alone)
    (_period(("BETWEEN", [202601, 202609])), YTD, 202609, "cumulative"),
    (_period(("BETWEEN", ["202601", "202609"])), MONTH, 202609, "cumulative"),  # the range wins over cumulative: false
    (_period((">=", 202601), ("<=", 202609)), YTD, 202609, "cumulative"),
    (_period(("<=", 202609)), YTD, 202609, "cumulative"),
    (_period(("IN", [202603, 202601, 202602])), None, 202603, "cumulative"),
    (_period(("BETWEEN", [202606, 202606])), {"month": 6}, 202606, "month"),  # one month is not a range
])
def test_plan_reads_a_year_to_date_range_as_cumulative(metrics, intent, period_filters, time_range, period, mode):
    selection = intent | {"time_range": time_range, "filters": [dict(FILTER), *period_filters]}
    req, reason = compiler.plan_with_reason(selection, QUESTION, compiler.resolve(metrics), [], 202609, set())
    assert reason is None
    assert (req.period, req.mode, req.filters) == (period, mode, (FILTER,))


@pytest.mark.parametrize("period_filters,time_range,reason", [
    (_period(("BETWEEN", [202607, 202609])), YTD, "period_filter:range"),  # Jul–Sep sum: not declared
    (_period(("BETWEEN", [202509, 202609])), YTD, "period_filter:range"),
    (_period(("IN", [202601, 202603])), YTD, "period_filter:range"),
    (_period(("<=", 202609)), MONTH, "period_filter:range"),  # no lower bound and not cumulative
    (_period((">=", 202601)), YTD, "period_filter:range"),
    (_period(("=", 202609), ("BETWEEN", [202601, 202609])), YTD, "period_filter:range"),
    (_period((">=", 202609), ("<=", 202601)), YTD, "period_filter:range"),
    (_period(("BETWEEN", [202601])), YTD, "period_filter:value"),
    (_period(("BETWEEN", "202601")), YTD, "period_filter:value"),
    (_period(("BETWEEN", [202601, 202613])), YTD, "period_filter:value"),
    (_period(("IN", [])), YTD, "period_filter:value"),
    (_period(("<", 202609)), YTD, "period_filter:operator"),
])
def test_plan_declines_ranges_it_cannot_express(metrics, intent, period_filters, time_range, reason):
    selection = intent | {"time_range": time_range, "filters": period_filters}
    assert compiler.plan_with_reason(selection, QUESTION, compiler.resolve(metrics), [], 202609, set()) == (None, reason)


LEVEL_QUESTION = "สายงานไหนมี EBT สะสมปี 2569 สูงสุด"


def test_a_dimension_label_mapping_does_not_block(metrics, intent):
    selection = intent | RANKING | {"intent_type": "ranking", "metric_id": "ebt", "dimensions": ["division"],
                                    "filters": [], "matched_mappings": [{"keyword": "สายงาน", "sql_condition": "x"}]}
    resolved = compiler.resolve(metrics)
    assert compiler.plan_with_reason(selection, LEVEL_QUESTION, resolved, [], 202609, set()) == (
        None, "mapping_triggered:สายงาน")
    req, reason = compiler.plan_with_reason(selection, LEVEL_QUESTION, resolved, [], 202609, set(),
                                            {"division": "สายงาน", "unit": "ฝ่าย"})
    assert reason is None and req.dimensions == ("division",) and req.metric_id == "ebt"
    # a label of a column the metric does not declare is not a level word of this metric
    assert compiler.plan(selection, LEVEL_QUESTION, resolved, [], 202609, set(), {"region": "สายงาน"}) is None
    # another triggered mapping still blocks
    other = selection | {"matched_mappings": [{"keyword": "สายงาน"}, {"keyword": "สะสม"}]}
    assert compiler.plan_with_reason(other, LEVEL_QUESTION, resolved, [], 202609, set(), {"division": "สายงาน"}) == (
        None, "mapping_triggered:สะสม")


@pytest.mark.parametrize("labels,compiled_expected", [({"sub_unit": "น่าน"}, True), ({}, False)])
async def test_hybrid_flow_hands_the_labels_to_plan(metrics, intent, monkeypatch, labels, compiled_expected):
    monkeypatch.setattr(compiler, "load_metrics", lambda c: metrics)
    monkeypatch.setattr(compiler, "dimension_labels", lambda *a: labels)
    selection = intent | {"matched_mappings": [{"keyword": "น่าน", "sql_condition": "x"}]}
    trace = SimpleNamespace(stages={}, usage=[])
    prompt, two_pass, compiled = await _first(_service(selection), trace=trace)
    assert (compiled is not None) is compiled_expected
    assert trace.stages.get("metric_declined") == (None if compiled_expected else "mapping_triggered:น่าน")


# the intents pass 1 wrote for comparison questions on the practice server (2026-10-25, PLAN_METRICS_COMPARISON §1)
COMPARE = {"intent_type": "comparison", "metrics": ["ebt"], "metric_id": "ebt", "dimensions": ["division"],
           "filters": [], "time_range": YTD, "ordering": None, "limit": None}


@pytest.mark.parametrize("question,changes,expected", [
    ("สายงานไหน EBT ดีกว่าปีก่อนหน้าบ้าง", {}, (202609, 202509, "cumulative", "up", True)),
    ("สายงานไหนมี EBT สะสมแย่ลงกว่าปีที่แล้ว", {"ordering": {"column": "ebt", "direction": "ASC"}, "limit": 10},
     (202609, 202509, "cumulative", "down", False)),
    ("EBT เดือนกันยายนเทียบกับเดือนสิงหาคม ฝ่ายไหนเพิ่มขึ้น",
     {"metrics": ["ebt_month"], "dimensions": ["unit"], "time_range": None,
      "filters": _period(("IN", [202608, 202609])), "ordering": {"column": "diff_ebt", "direction": "DESC"}},
     (202609, 202608, "month", "up", True)),
    ("สายงานไหนมี EBT margin เทียบกับปีก่อน", {"metric_id": "ebt_margin", "filters": _period(("BETWEEN", [202509, 202609])),
                                               "ordering": {"column": "ebt_margin", "direction": "ASC"}},
     (202609, 202509, "cumulative", None, False)),
    ("EBT ปีนี้เทียบกับปีก่อนดีขึ้นหรือแย่ลง", {"dimensions": []}, (202609, 202509, "cumulative", None, True)),
])
def test_plan_compiles_a_comparison(metrics, question, changes, expected):
    req, reason = compiler.plan_with_reason(COMPARE | changes, question, compiler.resolve(metrics), [], 202609, set())
    assert reason is None
    assert (req.period, req.base_period, req.mode, req.change, req.order_desc) == expected


@pytest.mark.parametrize("changes,reason", [
    ({"filters": _period(("IN", [202507, 202508, 202509]))}, "period_filter:compare"),
    ({"filters": _period((">=", 202509))}, "period_filter:operator"),
    ({"filters": _period(("IN", ["2025-09"]))}, "period_filter:value"),
    ({"filters": _period(("IN", [202609]))}, None),  # one period: compared with a year before
    ({"time_range": {"year": 1, "month": 9}}, "period_filter:compare"),  # nothing a year before
    ({"dimensions": ["region"]}, "shape:dimension:region"),
])
def test_plan_comparison_period_and_shape_errors(metrics, changes, reason):
    req, got = compiler.plan_with_reason(COMPARE | changes, "EBT เทียบกับปีก่อน", compiler.resolve(metrics), [], 202609, set())
    assert got == reason
    if reason is None:
        assert (req.period, req.base_period) == (202609, 202509)


def test_supports_still_says_no_to_a_comparison(metrics):
    assert not compiler.supports(COMPARE, compiler.resolve(metrics)["ebt"])
    assert compiler.plan(COMPARE | {"intent_type": "aggregation"}, "EBT", compiler.resolve(metrics), [], 202609,
                         set()).base_period is None


HIERARCHY = [{"level": 0, "label_th": "สายงาน", "label_en": "division", "columns": ["division"],
              "detection_keywords": ["สายงาน"]},
             {"level": 3, "label_th": "ส่วน", "label_en": "sub_unit", "columns": ["sub_unit"],
              "detection_keywords": ["ส่วนงาน", "รายส่วน"]}]


async def _ask(service, question, **kwargs):
    return await hybrid_flow.build_first_attempt_prompt(
        service=service, question=question, system_prompt="system", history=None,
        context_name="feed_ebt", context_table="feed_ebt_fact_ebt", context_thai="EBT",
        two_pass_enabled=True, cheap_model=None, detect_hierarchy_level=lambda *a: None,
        format_value_matches=service.format_value_matches, get_vanna_context_string=lambda q: "",
        lookup_values_from_question=lambda *a: [], on_status=None, attempt=0, max_retries=1, **kwargs,
    )


@pytest.mark.parametrize("question,dimensions,asks", [
    ("EBT ของหน่วยงานไหน ดีกว่าปีก่อนหน้าบ้าง", ["division"], True),
    ("จังหวัดไหน มี ebt ดีขึ้นกว่าปีก่อนบ้าง", ["sub_division_fname"], True),
    ("ส่วนงานไหน EBT ดีกว่าปีก่อน (หน่วยงานขาย)", ["sub_unit"], False),  # a level is named
    ("EBT ของหน่วยงาน ส่วนขายและบริการลูกค้า น่าน", [], False),           # one named unit, no breakdown
    ("สายงานไหน EBT ดีกว่าปีก่อน", ["division"], False),
])
async def test_a_breakdown_by_a_generic_unit_word_asks_back(metrics, monkeypatch, question, dimensions, asks):
    monkeypatch.setattr(compiler, "load_metrics", lambda c: metrics)
    monkeypatch.setattr(compiler, "dimension_labels", lambda *a: {})
    monkeypatch.setattr(hybrid_flow, "get_column_hierarchies", lambda: {"feed_ebt": HIERARCHY})
    trace = SimpleNamespace(stages={}, usage=[])
    prompt, _, result = await _ask(_service(COMPARE | {"dimensions": dimensions}), question, trace=trace)
    if asks:
        assert isinstance(result, compiler.Clarification) and prompt == ""
        assert "สายงาน, ส่วน" in result.text and trace.stages["metric_declined"] == "clarify:level"
        assert "SELECT" not in result.text
    else:
        assert not isinstance(result, compiler.Clarification)


async def test_the_question_back_reaches_the_caller_without_sql(execution, metrics, monkeypatch):
    from app.core import outbound
    monkeypatch.setattr(compiler, "load_metrics", lambda c: metrics)
    monkeypatch.setattr(compiler, "dimension_labels", lambda *a: {})
    monkeypatch.setattr(hybrid_flow, "get_column_hierarchies", lambda: {"feed_ebt": HIERARCHY})
    monkeypatch.setattr(hybrid_flow, "resolve_context_info", lambda *a, **kw: (
        SimpleNamespace(get_context_info=lambda c: {}), "feed_ebt_fact_ebt", "EBT"))
    execution.provider.intent = COMPARE
    execution.get_vanna_context_string = lambda q: ""
    execution.lookup_values_from_question = lambda *a: []
    execution.detect_hierarchy_level = lambda *a: None
    execution.extract_sql = execution.extract_explanation = lambda text: text
    execution.log_value_corrections = Mock()
    execution.prepare_data_for_explanation = lambda data, **kw: data
    result = await hybrid_flow.query_hybrid(execution, "EBT ของหน่วยงานไหน ดีกว่าปีก่อนหน้าบ้าง", "system",
                                            max_retries=1, two_pass_enabled=True, value_verification_enabled=False,
                                            context_name="feed_ebt")
    assert result.clarification is True and result.sql_query == "" and result.data == [] and not result.error
    execution.mcp_client.call_tool.assert_not_awaited()
    assert outbound.safe_answer(result) == result.explanation and "ระดับไหน" in result.explanation
