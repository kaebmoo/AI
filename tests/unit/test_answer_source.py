"""The chat says which data source answered, and warns when the picked one does not fit the question.

"ข้อมูล EBT เป็นอย่างไรบ้าง" with the revenue feed selected came back as revenue named "EBT"; in auto mode it went
to pl_costtype and an empty month. Neither answer said where it came from (2026-10-22).
"""

from app.api.v1 import chat
from app.services.query_engine import QueryEngineResult, context_keyword_hits, detect_context_from_question
from app.providers.base import QueryResult

CONTEXTS = [
    {"name": "pl_costtype", "display_name": "ผลดำเนินงาน", "description": "P&L ทั้งบริษัท", "priority": 5,
     "keywords": ["กำไร", "EBT"]},
    {"name": "revenue", "display_name": "รายได้", "description": "รายได้", "priority": 10, "keywords": ["รายได้"]},
    {"name": "feed_revenue", "display_name": "DataFeed revenue", "description": "รายได้ feed", "priority": 1,
     "keywords": ["รายได้", "feed"]},
    {"name": "feed_ebt", "display_name": "DataFeed ebt", "description": "EBT 2 สายงานขาย", "priority": 1,
     "keywords": ["ebt", "กำไร"]},
    {"name": "transfer price", "display_name": "ราคาโอน", "description": "", "priority": 9, "keywords": ["ราคาโอน"]},
]


class _Schema:
    def get_all_contexts(self):
        return CONTEXTS

    def get_context_info(self, name):
        return next((c for c in CONTEXTS if chat._same_context(c["name"], name)), None)


def test_the_router_picks_what_it_picked_before():
    """The scoring moved into context_keyword_hits; the choice is the same — keywords found, priority × 0.1."""
    schema = _Schema()
    assert detect_context_from_question("ข้อมูล EBT เป็นอย่างไรบ้าง", schema) == "pl_costtype"  # 1.5 against 1.1
    assert detect_context_from_question("รายได้ feed เดือนนี้", schema) == "feed_revenue"  # 2.1 against revenue 2.0
    assert detect_context_from_question("สวัสดี", schema) == "pl_costtype"  # no hit: the first context, as before
    hits = context_keyword_hits("กำไร EBT", schema)
    assert hits["pl_costtype"]["keywords"] == ["กำไร", "EBT"] and hits["feed_ebt"]["keywords"] == ["ebt", "กำไร"]
    assert context_keyword_hits("x", None) == {}


def _result(context, period=None):
    return QueryEngineResult(query_result=QueryResult(question="q", sql_query="", data=[], explanation="", tokens_used=0,
                                                         provider="matcha"),
                             context_name=context, data_period=period)


def test_the_answer_says_where_it_came_from_and_where_else_to_ask():
    source = chat._answer_source(_result("pl_costtype", 202602), "ข้อมูล EBT เป็นอย่างไรบ้าง", _Schema())
    assert source["display_name"] == "ผลดำเนินงาน" and source["description"] == "P&L ทั้งบริษัท"
    assert source["data_period"] == 202602 and source["data_period_th"] == "ก.พ. 2569"
    assert [a["context"] for a in source["alternatives"]] == ["feed_ebt"]  # not itself
    assert source["alternatives"][0]["keywords"] == ["ebt"]
    assert chat._answer_source(_result(None), "q", _Schema()) is None


def test_period_in_thai():
    from app.services.ai.thai_year import period_th

    assert period_th(202609) == "ก.ย. 2569" and period_th(202512) == "ธ.ค. 2568"
    assert period_th(None) is None and period_th(2026) is None and period_th("202609") is None and period_th(True) is None


def test_a_picked_context_the_question_does_not_name_is_flagged():
    mismatch = chat._context_mismatch("feed_revenue", "ข้อมูล EBT เป็นอย่างไรบ้าง", _Schema())
    assert mismatch["warning"]["code"] == "context_mismatch" and mismatch["warning"]["severity"] == "important"
    assert "“EBT”" in mismatch["warning"]["message"] and "DataFeed revenue" in mismatch["warning"]["message"]
    assert "ผลดำเนินงาน" in mismatch["warning"]["message"] and "DataFeed ebt" in mismatch["warning"]["message"]
    # the prompt is told not to rename another column as the thing asked — what the revenue feed did
    assert "ห้ามนำคอลัมน์อื่นมาตั้งชื่อ" in mismatch["prompt_note"]


def test_no_flag_when_it_fits_or_nothing_points_elsewhere():
    schema = _Schema()
    assert chat._context_mismatch(None, "ข้อมูล EBT", schema) is None  # auto: the router followed the keywords
    assert chat._context_mismatch("feed_ebt", "ข้อมูล EBT", schema) is None  # the picked one has the keyword
    assert chat._context_mismatch("feed_revenue", "ยอด Mobile เดือนนี้", schema) is None  # no keyword anywhere
    assert chat._context_mismatch("transfer_price", "ราคาโอน ฝ่าย X", schema) is None  # stored as 'transfer price'


def test_source_and_warning_are_added_before_the_render_payload_is_saved():
    response = {"warnings": [{"code": "w", "message": "m", "severity": "info"}]}
    mismatch = chat._context_mismatch("feed_revenue", "ข้อมูล EBT", _Schema())
    chat._add_source(response, _result("feed_revenue", 202609), "ข้อมูล EBT", _Schema(), mismatch)
    assert response["warnings"][0]["code"] == "context_mismatch" and response["warnings"][1]["code"] == "w"
    assert response["source"]["context"] == "feed_revenue"
    assert {a["context"] for a in response["source"]["alternatives"]} == {"pl_costtype", "feed_ebt"}
