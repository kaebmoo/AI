"""The prompt says what the caller's `scope` confines the request to.

Scope is enforced by wrapping every table in a filtered view; the model never saw the scope itself.
With a one-month window that was harmless — SQL that forgot a period filter was still right, because
the view held one month. The portal now sends 13–24 months, two of every calendar month, and the
same SQL sums both years or picks the wrong one (plan/archive/RESULT_F11.md §2).
"""

import pytest

from app.services.ai import hybrid_flow
from app.services.data_sources import request_scope


@pytest.fixture
def scoped():
    def _set(scope):
        token = request_scope.set(scope)
        tokens.append(token)
    tokens = []
    yield _set
    for token in reversed(tokens):
        try:
            request_scope.reset(token)
        except ValueError:
            # an async test runs its body in another context; the value goes with it
            request_scope.set(None)


def _prompt():
    return hybrid_flow.build_initial_user_prompt(
        question="รายได้กลุ่ม Mobile เดือนสิงหาคม", context_table="feed_revenue_fact_bu_monthly",
        context_thai="รายได้", rag_context="", value_lookup_text="")


def test_unscoped_prompt_is_unchanged():
    assert hybrid_flow.scope_note() == ""
    assert "ขอบเขตข้อมูลของคำขอนี้" not in _prompt()


def test_window_and_anchor_reach_the_prompt(scoped):
    months = [y * 100 + m for y in (2025, 2026) for m in range(1, 13) if not (y == 2026 and m > 8)]
    scoped({"year_month": months})
    prompt = _prompt()
    assert "202501–202608" in prompt and "20 ค่า" in prompt
    assert "202608" in prompt and "งวดอ้างอิง" in prompt
    # the instruction that makes a period-less query wrong
    assert "SQL ต้องใส่เงื่อนไขงวดเสมอ" in prompt
    # and the one for a question with no time words at all — "รายได้รวม" on a 202608 report came
    # back as all twenty months added together before this line existed (RESULT_F11 §7)
    assert "ไม่เอ่ยถึงช่วงเวลาเลย" in prompt and "ห้ามรวมทุกงวดในขอบเขตเป็นคำตอบเดียว" in prompt
    # a question that DOES name a period keeps it: saying only the above narrowed "ปี 69" to
    # August as well, and the case that outranks it has to be stated first
    assert prompt.index("ห้ามแคบลงเป็นงวดอ้างอิงเอง") < prompt.index("ไม่เอ่ยถึงช่วงเวลาเลย")


def test_no_period_at_all_is_year_to_date(scoped):
    """"รายได้รวม" on the 202608 report means the year: users handed August asked for the year right after
    (portal audit, 2026-09-20 and 2026-09-25) — the owner's default since 2026-09-25."""
    scoped({"year_month": [202607, 202608]})
    note = hybrid_flow.scope_note()
    no_period = note[note.index("ไม่เอ่ยถึงช่วงเวลาเลย"):]
    assert "ยอดสะสมตั้งแต่ต้นปีถึงงวดอ้างอิง 202608" in no_period
    # a cumulative column is read at one period — summed over the months it is many times too big
    assert "ห้าม SUM ข้ามเดือน" in no_period


def test_pass1_can_write_the_year_to_date_and_pass2_reads_it(scoped, monkeypatch):
    """In words alone it did nothing: time_range could not hold "year to date", so pass 1 left it empty and
    pass 2 kept the month or summed every month of the scope (8/15 against 9/15 on a copy, 2026-09-25)."""
    assert hybrid_flow.intent_period_note() == ""  # unscoped: pass 1's prompt is what it was
    assert "cumulative" in hybrid_flow.INTENT_SCHEMA["properties"]["time_range"]["properties"]
    scoped({"year_month": [2025, 2026]})  # a window of years has no month to reach
    assert hybrid_flow.intent_period_note() == ""
    scoped({"year_month": [202512, 202607, 202608]})
    assert '{"year": 2026, "month": 8, "cumulative": true}' in hybrid_flow.intent_period_note()
    # a monthly question: the months of the year, not the reference month ("รายได้ Mobile รายเดือน" got August alone)
    assert '"month": null, "cumulative": false}' in hybrid_flow.intent_period_note()

    class _Service:
        def format_value_matches(self, *a, **k):
            return ""

    def pass2(time_range):
        return hybrid_flow.build_pass2_prompt(service=_Service(), question="q", intent={"time_range": time_range},
                                              context_table="t", context_thai="รายได้")

    # the cumulative column is named — told only "if there is one", pass 2 summed the monthly column
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda table, config_engine=None: ["revenue_ytd"])
    ytd = pass2({"year": 2026, "month": 8, "cumulative": True})
    assert "**ยอดสะสมถึงเดือน 8 ปี ค.ศ. 2026 (พ.ศ. 2569)**" in ytd and "ใช้คอลัมน์ยอดสะสม revenue_ytd" in ytd
    # one period, spelled as one row: "เดือน 1–8" beside the column read as a range and the model wrote
    # BETWEEN 202601 AND 202609 over a YTD column (chat 1534, 2026-10-22)
    assert "**งวดเดียว**" in ytd and "ห้าม BETWEEN" in ytd
    # the year alone: its last month in scope — the reference period's for its year, December for a closed one
    assert "**ยอดสะสมถึงเดือน 8 ปี ค.ศ. 2026" in pass2({"year": 2026, "month": None, "cumulative": True})
    assert "**ยอดสะสมถึงเดือน 12 ปี ค.ศ. 2025" in pass2({"year": 2025, "month": None, "cumulative": True})
    # "ปี 69" came back as month 12 — 202612 has no rows yet
    assert "**ยอดสะสมถึงเดือน 8 ปี ค.ศ. 2026" in pass2({"year": 2026, "month": 12, "cumulative": True})
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda table, config_engine=None: [])
    assert "— SUM รายเดือน เดือน 1–8\n" in pass2({"year": 2026, "month": 8, "cumulative": True})
    assert "- Time Range: ปี ค.ศ. 2026 (พ.ศ. 2569), เดือน 8\n" in pass2({"year": 2026, "month": 8, "cumulative": False})


def test_a_single_period_needs_no_anchor(scoped):
    """One month is its own anchor — the old behaviour, and nothing is claimed about "latest"."""
    scoped({"year_month": [202608]})
    note = hybrid_flow.scope_note()
    assert "202608" in note and "งวดอ้างอิง" not in note


def test_non_numeric_keys_are_listed_not_ranged(scoped):
    scoped({"org_code": ["1B00000", "1L00201"], "year_month": [202607, 202608]})
    note = hybrid_flow.scope_note()
    assert "1B00000, 1L00201" in note and "งวดอ้างอิง = 202608" in note
    assert "–1L00201" not in note  # a range over strings would be meaningless


async def test_intent_extraction_sees_it_too(scoped):
    """Pass 1 is where the period is decided when two_pass_enabled is on (it is, on the live config).
    Without the note there, pass 2 is handed a month and guesses the year — which is what sales and
    ebt did: `year_month = 202508` for a question about the 202608 report."""
    scoped({"year_month": [202607, 202608]})
    seen = []

    class _Provider:
        async def generate_structured(self, prompt, *a, **k):
            seen.append(prompt)
            return None  # push it down the text path too

        async def generate_content(self, prompt, *a, **k):
            seen.append(prompt)
            return "not json"

    class _Service:
        provider = _Provider()

        def parse_intent_json(self, text):
            return None

    await hybrid_flow.extract_intent(service=_Service(), question="ยอดขายเดือนสิงหาคม",
                                     system_prompt="", context_name="feed_sales",
                                     context_table="feed_sales_fact_sales", context_thai="ยอดขาย",
                                     history_context="", rag_context="")
    assert seen, "the provider was never asked"
    assert all("งวดอ้างอิง = 202608" in prompt for prompt in seen)


def test_retry_and_pass2_prompts_carry_it_too(scoped):
    scoped({"year_month": [202607, 202608]})
    retry = hybrid_flow.build_retry_user_prompt("q", "t", "รายได้", [{"sql": "SELECT 1", "error": "boom"}])
    assert "งวดอ้างอิง = 202608" in retry

    class _Service:  # build_pass2_prompt only reaches the service for value formatting
        def format_value_matches(self, *a, **k):
            return ""

    pass2 = hybrid_flow.build_pass2_prompt(service=_Service(), question="q", intent={},
                                           context_table="t", context_thai="รายได้")
    assert "งวดอ้างอิง = 202608" in pass2


def test_the_column_is_named_when_it_differs_from_the_key(scoped, monkeypatch):
    """expense and ebt map the caller's `year_month` onto `time_key`. Naming only the key pinned the
    reference period to a column those tables do not have, and ebt kept answering from the wrong
    year (RESULT_F11 §8)."""
    from app.services.data_sources import request_scope_columns

    scoped({"year_month": [202606, 202607]})
    token = request_scope_columns.set({"year_month": "time_key"})
    try:
        note = hybrid_flow.scope_note()
    finally:
        request_scope_columns.reset(token)
    assert "year_month (คอลัมน์ `time_key`)" in note

    # a context whose key already is the column says it once, not twice
    scoped({"year_month": [202607, 202608]})
    token = request_scope_columns.set({"year_month": "year_month"})
    try:
        assert "(คอลัมน์" not in hybrid_flow.scope_note()
    finally:
        request_scope_columns.reset(token)



def test_plan_tables_the_scope_opened_reach_every_pass(scoped):
    """A target table under the portal's scope holds the whole year (scope_plan_tables) — the user prompt, which pass 1
    reads too, must not say every table stops at the scope's months (portal, feed_sales, 2026-10-30)."""
    from app.services.data_sources import request_plan_tables

    scoped({"year_month": [202601 + i for i in range(9)]})
    assert "ตารางเป้า" not in _prompt()  # nothing opened: as before
    token = request_plan_tables.set({"feed_sales_fact_sales_target_monthly": None})
    try:
        prompt = _prompt()
    finally:
        request_plan_tables.reset(token)
    assert "ตารางเป้า/แผน** feed_sales_fact_sales_target_monthly" in prompt
    assert "ครบ 12 เดือน**ของปี 2026 (พ.ศ. 2569)" in prompt and "กรองเดือนถึง 202609 เอง" in prompt

# --- no scope, but the source names the period its data runs to (2026-10-22) ------------------------

@pytest.fixture
def data_period():
    from app.services.data_sources import request_data_period

    tokens = []

    def _set(period):
        tokens.append(request_data_period.set(period))
    yield _set
    for token in reversed(tokens):
        try:
            request_data_period.reset(token)
        except ValueError:
            request_data_period.set(None)


def test_unscoped_file_source_anchors_on_its_manifest_period(data_period):
    """Chat and Telegram send no scope. Without an anchor the three period rules were not in the prompt at
    all, and "ข้อมูล EBT เป็นอย่างไรบ้าง" summed every month of two years (chat audit 310, 2026-10-22)."""
    data_period(202609)
    assert hybrid_flow.reference_period() == 202609
    note = hybrid_flow.scope_note()
    assert "มีถึงงวด 202609" in note and "ไม่ได้กรองไว้" in note  # nothing is filtered: the model must
    assert "ยอดสะสมตั้งแต่ต้นปีถึงงวดอ้างอิง 202609" in note and "ห้าม SUM ข้ามเดือน" in note
    assert "ถูกกรองไว้แล้ว" not in note  # the scoped wording would be a lie here
    assert '{"year": 2026, "month": 9, "cumulative": true}' in hybrid_flow.intent_period_note()
    assert "มีถึงงวด 202609" in _prompt()


def test_a_scope_outranks_the_manifest_period(scoped, data_period):
    data_period(202609)
    scoped({"year_month": [202607, 202608]})
    assert hybrid_flow.reference_period() == 202608
    assert "ถูกกรองไว้แล้ว" in hybrid_flow.scope_note()


def test_legacy_source_without_a_period_is_unchanged(data_period):
    data_period(None)
    assert hybrid_flow.scope_note() == "" and hybrid_flow.intent_period_note() == ""


def test_data_period_is_the_manifest_period_as_yyyymm():
    from app.services.data_sources import LEGACY_SOURCE, ResolvedSource

    class _Adapter:
        def __init__(self, manifest):
            self.manifest = manifest

    def src(manifest):
        return ResolvedSource(name="f", source_type="duckdb_file", adapter=_Adapter(manifest))

    assert LEGACY_SOURCE.data_period is None
    assert src({"period": 202609}).data_period == 202609
    assert src({"period": "202609"}).data_period is None  # not an int: no anchor rather than a wrong one
    assert src({"period": 2026}).data_period is None
    assert src({}).data_period is None


def test_a_cumulative_column_summed_over_periods_is_refused(monkeypatch):
    """"ข้อมูล EBT เป็นอย่างไรบ้าง" → SUM(ebt) over 202601–202609 = 4,298M against the report's 571M (chat 1534,
    2026-10-22). The prompt said one row in words; the attempt is refused and the retry is told what to write."""
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda t, config_engine=None: ["ebt", "expense"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda t, config_engine=None: ["time_key"])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda t, config_engine=None: ["ebt_month"])

    def refused(sql):
        return hybrid_flow.cumulative_sum_error(sql, "t") is not None

    assert refused("SELECT SUM(ebt), SUM(expense) FROM t WHERE CAST(time_key AS INTEGER) BETWEEN 202601 AND 202609")
    assert refused("SELECT SUM(ebt) FROM t")  # no period at all
    assert refused('SELECT SUM("ebt") FROM t WHERE time_key IN (202608, 202609)')
    assert refused("SELECT SUM(ebt) FROM t WHERE cost_center = '1B00000'")  # an equality, but not on the period
    assert refused("SELECT cost_center, SUM(COALESCE(ebt, 0)) FROM t WHERE CAST(time_key AS INTEGER) BETWEEN 202601 AND 202609 GROUP BY cost_center")
    assert hybrid_flow.cumulative_sum_error("SELECT SUM(ebt) FROM t", "t").startswith("I1 ytd_summed_across_periods: ")
    assert "WHERE time_key = <งวดที่ต้องการ>" in hybrid_flow.cumulative_sum_error("SELECT SUM(ebt) FROM t", "t")
    # one period, summed across the other dimensions — the right way to read it
    assert not refused("SELECT SUM(ebt) FROM t WHERE time_key = 202609")
    assert not refused("SELECT SUM(ebt) FROM t WHERE CAST(time_key AS INTEGER) = '202609'")
    # a YTD trend, one row per period
    assert not refused("SELECT time_key, SUM(ebt) FROM t WHERE time_key BETWEEN 202601 AND 202609 GROUP BY time_key")
    # monthly columns sum over months; the plain column unsummed is not this mistake
    assert not refused("SELECT SUM(ebt_month) FROM t WHERE time_key BETWEEN 202601 AND 202609")
    assert not refused("SELECT ebt FROM t WHERE time_key = 202609")


def test_no_cumulative_columns_or_no_period_column_means_no_check(monkeypatch):
    sql = "SELECT SUM(revenue) FROM revenue_search"
    def unexpected_summable_query(*args):
        pytest.fail("summable columns must not be queried without cumulative and period columns")

    monkeypatch.setattr(hybrid_flow, "_summable_columns", unexpected_summable_query)
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda t, config_engine=None: ["year_month"])
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda t, config_engine=None: [])
    assert hybrid_flow.cumulative_sum_error(sql, "revenue_search") is None  # a legacy view: unchanged
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda t, config_engine=None: ["revenue"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda t, config_engine=None: [])
    assert hybrid_flow.cumulative_sum_error(sql, "revenue_search") is None  # cannot tell a period: no guess


def test_ytd_without_period_names_the_invariant_and_columns(monkeypatch):
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: ["ebt"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda *a: ["time_key"])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda *a: [])
    error = hybrid_flow.cumulative_sum_error("SELECT cost_center, ebt FROM t WHERE cost_center = '1'", "t")
    assert error.startswith("I2 ytd_without_period: ")
    assert "ebt" in error and "WHERE time_key = <งวดที่ต้องการ>" in error


def test_invariant_checker_exception_does_not_block_or_log_sql(monkeypatch, caplog):
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: ["ebt"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda *a: ["time_key"])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda *a: [])
    sql = "SELECT SUM(COALESCE(ebt, 0)) FROM t"

    def broken_check(*args):
        raise RuntimeError(sql)

    monkeypatch.setattr(hybrid_flow.sql_invariants, "check", broken_check)
    assert hybrid_flow.cumulative_sum_error(sql, "t") is None
    assert "invariant checker failed" in caplog.text
    assert sql not in caplog.text


def test_monthly_invariant_is_logged_without_refusal(monkeypatch, caplog):
    monkeypatch.setattr(hybrid_flow, "_cumulative_columns", lambda *a: ["ebt"])
    monkeypatch.setattr(hybrid_flow, "_period_columns", lambda *a: ["time_key"])
    monkeypatch.setattr(hybrid_flow, "_summable_columns", lambda *a: ["ebt_month"])
    with caplog.at_level("INFO", logger=hybrid_flow.__name__):
        assert hybrid_flow.cumulative_sum_error("SELECT SUM(ebt_month) FROM t", "t") is None
    assert "I3 month_summed_as_ytd" in caplog.text and "ebt_month" in caplog.text


def test_the_latest_period_of_a_legacy_view_is_read_from_its_own_columns(tmp_path):
    """pl_costtype has report_year / report_month and data to 202602; without an anchor the prompt's
    "วันที่ปัจจุบัน" stood in and the model asked for 202610 (chat audit 336, 2026-10-22)."""
    from sqlalchemy import create_engine, text

    from app.services.data_sources import _probe_period

    engine = create_engine(f"sqlite:///{tmp_path / 'biz.sqlite'}")
    with engine.begin() as conn:
        # the max month of the max year, not MAX(month) of any year: 2025-12 must not win over 2026-02
        conn.execute(text("CREATE TABLE pl (report_year INT, report_month INT, report_date TEXT, amount_value REAL)"))
        conn.execute(text("INSERT INTO pl VALUES (2025, 12, '202512', 1), (2026, 2, '202602', 1)"))
        conn.execute(text("CREATE TABLE be (ปี INT, เดือน INT, x REAL)"))  # พ.ศ. → ค.ศ.
        conn.execute(text("INSERT INTO be VALUES (2569, 3, 1), (2568, 12, 1)"))
        conn.execute(text("CREATE TABLE ym (period TEXT, month_th TEXT, x REAL)"))  # a YYYYMM column; Thai month names
        conn.execute(text("INSERT INTO ym VALUES ('202607', 'กรกฎาคม', 1)"))
        conn.execute(text("CREATE TABLE plain (division TEXT, x REAL)"))
        conn.execute(text("INSERT INTO plain VALUES ('a', 1)"))
    assert _probe_period(engine, "pl") == 202602
    assert _probe_period(engine, "be") == 202603
    assert _probe_period(engine, "ym") == 202607
    assert _probe_period(engine, "plain") is None  # no period: no anchor, the prompt as before
    assert _probe_period(engine, "missing") is None


def test_the_unscoped_note_says_the_anchor_is_not_todays_month(data_period):
    data_period(202602)
    assert "ไม่ใช่เดือนของวันที่ปัจจุบัน" in hybrid_flow.scope_note()


def test_no_rows_says_how_far_the_data_runs(data_period):
    """pl_costtype was asked for 202610 with data to 202602 and the answer said only "no rows" (2026-10-22)."""
    data_period(202602)
    message = hybrid_flow.no_data_message("SELECT 1")
    assert message.startswith("ไม่พบข้อมูลที่ตรงกับเงื่อนไข") and "SELECT 1" in message
    assert "มีถึงงวด **ก.พ. 2569** (202602)" in message
    data_period(None)  # unknown: the message as it was
    assert "มีถึงงวด" not in hybrid_flow.no_data_message("SELECT 1")


def test_a_request_note_reaches_every_user_prompt():
    """The picked-context note went into the system prompt only and the model still named revenue "EBT" — the
    period rules, which do work, live in the user prompts (2026-10-22)."""
    from app.services.data_sources import request_prompt_note

    token = request_prompt_note.set("ZQXNOTE")
    try:
        assert "ZQXNOTE" in _prompt()
        assert "ZQXNOTE" in hybrid_flow.build_retry_user_prompt("q", "t", "รายได้", [{"sql": "SELECT 1", "error": "x"}])
        # and the explanation, which named revenue "EBT" after the SQL had stopped doing so
        from app.providers.chart_postprocessor import build_explain_prompt
        assert "ZQXNOTE" in build_explain_prompt("q", "SELECT 1", [{"x": 1}])
    finally:
        request_prompt_note.reset(token)
    assert "ZQXNOTE" not in _prompt() and hybrid_flow.scope_note() == ""


def test_an_aggregate_over_no_rows_is_no_data():
    assert hybrid_flow.is_empty_result([]) and hybrid_flow.is_empty_result(None)
    assert hybrid_flow.is_empty_result([{"ebt": None}])  # SUM over nothing
    assert hybrid_flow.is_empty_result([{"a": None, "b": None}, {"a": None, "b": None}])
    assert not hybrid_flow.is_empty_result([{"ebt": 0}])  # a real zero is an answer
    assert not hybrid_flow.is_empty_result([{"division": "x", "ebt": None}])
