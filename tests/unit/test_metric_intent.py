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
    contract = yaml.safe_load((Path(__file__).parents[1] / "fixtures/ebt_metrics_1_5_0.yaml").read_text())
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
    trace = SimpleNamespace(stages={}, usage=[])
    service = _service(intent)
    prompt, two_pass, compiled = await _first(service, trace=trace)
    header = service.provider.prompts[0]
    assert compiler.metric_catalog(metrics) in header
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
    ([{"keyword": " EBT "}], True),
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
    expected_question = (f"{QUESTION}\n(ตัวชี้วัดที่ใช้: {compiled.name_th} — {compiled.note_th}"
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
