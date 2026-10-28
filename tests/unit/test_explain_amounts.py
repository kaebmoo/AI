"""The amounts an explanation states must be ones its result holds (plan/PLAN_ANOMALY_AVG_FIX.md §6): audit 518 wrote
"หลายหมื่นล้านบาท" for differences of 50–1,112 million, and practice answers wrote 99.37 million as "993.7 ล้านบาท"."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai import explain_amounts, hybrid_flow
from app.services.ai.trace import new_trace

# audit 518's own rows (its SQL on the sales feed, 2025): หน่วยงาน, ก.ย., เฉลี่ยก่อน ก.ย., ส่วนต่าง, %
AUDIT_518 = [
    {"หน่วยงาน": "ฝ่ายธุรกิจลูกค้าภาครัฐ", "รายได้เดือนกันยายน": 1113223812.8099997,
     "รายได้เฉลี่ยก่อนกันยายน": 1656934.6092071452, "ส่วนต่างรายได้": 1111566878.2007926,
     "เปอร์เซ็นต์เปลี่ยนแปลง": 67085.74206997131},
    {"หน่วยงาน": "ฝ่ายขายและปฏิบัติการลูกค้า ภาคตะวันออกตอนบน", "รายได้เดือนกันยายน": 50819536.480000004,
     "รายได้เฉลี่ยก่อนกันยายน": 352011.10921470344, "ส่วนต่างรายได้": 50467525.3707853,
     "เปอร์เซ็นต์เปลี่ยนแปลง": 14336.91268533331},
    {"หน่วยงาน": "ฝ่ายขายและปฏิบัติการลูกค้า ภาคตะวันออกเฉียงเหนือตอนล่าง", "รายได้เดือนกันยายน": 101345009.65,
     "รายได้เฉลี่ยก่อนกันยายน": 381161.4011221122, "ส่วนต่างรายได้": 100963848.2488779,
     "เปอร์เซ็นต์เปลี่ยนแปลง": 26488.47652245151},
]
AUDIT_518_TEXT = ("- **ฝ่ายขายฯ หลายภูมิภาค** รายได้เพิ่มขึ้นหลายหมื่นล้านบาท เช่น ภาคตะวันออกตอนบน เพิ่มขึ้น 14,336.91%\n"
                  "- หน่วยงานส่วนใหญ่รายได้เพิ่มขึ้นอย่างมาก")
# practice r2 (2026-10-28): the right rows, the differences written ten times too large
PRACTICE = [
    {"หน่วยงาน": "ฝ่ายบริหารการเงินและติดตามหนี้", "รายได้เดือนกันยายน": 134026919.09000002,
     "รายได้เฉลี่ยก่อนกันยายน": 233396867.44500002, "ส่วนต่างรายได้": -99369948.355,
     "เปอร์เซ็นต์เปลี่ยนแปลง": -42.57552787353349},
    {"หน่วยงาน": "ฝ่ายแสวงหาโอกาสและพัฒนาธุรกิจ", "รายได้เดือนกันยายน": -13347538.15,
     "รายได้เฉลี่ยก่อนกันยายน": 38856341.599999994, "ส่วนต่างรายได้": -52203879.74999999,
     "เปอร์เซ็นต์เปลี่ยนแปลง": -134.35099034130377},
]
PRACTICE_WRONG = ("- ฝ่ายบริหารการเงินและติดตามหนี้ รายได้ลดลงประมาณ **993.7 ล้านบาท** (-42.58%)\n"
                  "- ฝ่ายแสวงหาโอกาสและพัฒนาธุรกิจ รายได้ลดลงประมาณ **522.0 ล้านบาท** (-134.35%)")
PRACTICE_RIGHT = ("### สรุปผลการวิเคราะห์รายได้เดือนกันยายน 2569\n"
                  "- ฝ่ายบริหารการเงินและติดตามหนี้ ลดลงประมาณ **99.37 ล้านบาท** (-42.58%) จาก 233.40 ล้านบาท เหลือ 134.03 ล้านบาท\n"
                  "- ฝ่ายแสวงหาโอกาสและพัฒนาธุรกิจ ลดลง **52.2 ล้านบาท**; สองหน่วยรวมกันเดือนกันยายน 120.68 ล้านบาท")


def test_the_incidents_amounts_are_caught():
    assert explain_amounts.unsupported(AUDIT_518_TEXT, AUDIT_518) == ["หลายหมื่นล้าน"]
    assert explain_amounts.unsupported(PRACTICE_WRONG, PRACTICE) == ["993.7 ล้านบาท", "522.0 ล้านบาท"]


def test_amounts_the_result_holds_pass():
    assert explain_amounts.unsupported(PRACTICE_RIGHT, PRACTICE) == []
    assert explain_amounts.unsupported("ฝ่ายธุรกิจลูกค้าภาครัฐ 1,113.22 ล้านบาท เพิ่มขึ้น 1,111.57 ล้านบาท", AUDIT_518) == []
    assert explain_amounts.unsupported("ประมาณ 1,000 ล้านบาท", [{"v": 993_700_000.0}]) == []  # within 1%


@pytest.mark.parametrize("text,expected", [
    ("ปี 2569 ยอด 2,568 ล้านบาท", [2_568_000_000.0]),  # a money amount, not a year; the year is not money
    ("เพิ่มขึ้น 67,085.74% ในงวด 202609 ของปี 2568", []),  # percents, periods and years have no money unit
    ("612 บาท และ 49.8 พันบาท, 3 แสนบาท", [612.0, 49_800.0, 300_000.0]),
    ("**2,993** ล้าน และ 1.2 ล้านล้านบาท", [2_993_000_000.0, 1.2e12]),
    ("8 เดือน 65 หน่วยงาน 1.5 พัน", []),
])
def test_what_is_read_as_money(text, expected):
    assert [value for value, _, _ in explain_amounts.stated(text)] == pytest.approx(expected)


def test_amounts_quoted_from_the_question_or_the_rule_pass():
    question = "หน่วยงานที่ยอดขายเกิน 20 ล้านบาท"
    text = "หน่วยงานที่ยอดเกิน 20 ล้านบาท และส่วนต่าง ≥ 5 ล้านบาท ตามเกณฑ์: ลดลง 99.37 ล้านบาท"
    assert explain_amounts.unsupported(text, PRACTICE) == ["20 ล้านบาท", "5 ล้านบาท"]
    assert explain_amounts.unsupported(text, PRACTICE, explain_amounts.quoted(question)) == []


def test_display_advice_is_cut_and_other_advice_stays():
    text = ("### สรุป\nลดลง 99.37 ล้านบาท\n\n### ข้อเสนอแนะการแสดงผล\n- ใช้กราฟแท่ง\n\n"
            "#### รายละเอียด\n- x\n\n**ข้อเสนอแนะสำหรับการนำเสนอข้อมูล / แผนภูมิ**\nใช้ตาราง")
    assert explain_amounts.drop_display_advice(text) == "### สรุป\nลดลง 99.37 ล้านบาท\n\n#### รายละเอียด\n- x"
    kept = "### สรุป\nx\n\n### ข้อเสนอแนะ\n- ควรตรวจสอบสาเหตุ"
    assert explain_amounts.drop_display_advice(kept) == kept


def test_from_rows_keeps_the_chart_and_writes_numbers_in_code():
    out = explain_amounts.from_rows({"explanation": PRACTICE_WRONG, "visualization": "table"}, PRACTICE)
    assert out["visualization"] == "table"
    assert "ส่วนต่างรายได้ = -99,369,948.36 (-99.4 ล้าน)" in out["explanation"]
    assert "993.7" not in out["explanation"] and out["explanation"].startswith("ผลลัพธ์ 2 รายการ\n")


@pytest.fixture
def service():
    return SimpleNamespace(provider=SimpleNamespace(explain_result=AsyncMock(), last_usage=None, model="m"))


async def explain(service, trace=None):
    return await hybrid_flow.build_explanation(service, "เดือน กันยายน ผิดปกติ", "SELECT 1", PRACTICE, None,
                                               lambda data, **kw: data, None, None, None, trace=trace)


@pytest.mark.parametrize("answers,stage,expected", [
    ([PRACTICE_RIGHT], None, PRACTICE_RIGHT),
    ([PRACTICE_WRONG, PRACTICE_RIGHT], "retried", PRACTICE_RIGHT),
    ([PRACTICE_WRONG, PRACTICE_WRONG], "from_rows", "ผลลัพธ์ 2 รายการ"),
])
async def test_one_reask_then_the_rows_own_text(service, answers, stage, expected):
    service.provider.explain_result.side_effect = [{"explanation": a, "visualization": "table"} for a in answers]
    trace = new_trace("q")
    out = await explain(service, trace)
    assert out["explanation"].startswith(expected)
    assert trace.stages.get("explain_amounts") == stage
    calls = service.provider.explain_result.await_args_list
    assert len(calls) == len(answers)
    if len(calls) == 2:
        assert "993.7 ล้านบาท, 522.0 ล้านบาท" in calls[1].args[0] and calls[1].args[0].startswith("เดือน กันยายน ผิดปกติ\n")


# D-3 = ก: "รายได้" asked of the sales report is answered from sales, called sales — said in the explanation only
SALES_CONTEXTS = [
    {"name": "feed_sales", "display_name": "DataFeed sales", "priority": 1, "keywords": ["ยอดขาย", "sales"],
     "description": "ยอดขายจาก Sales DW รายเดือน — แยกสายการขาย / กลุ่มธุรกิจ. คนละฐานกับรายได้"},
    {"name": "feed_revenue", "display_name": "DataFeed revenue", "priority": 1, "keywords": ["รายได้"],
     "description": "รายได้ตามรายงานรายได้"},
]


class _Schema:
    def get_all_contexts(self):
        return SALES_CONTEXTS

    def get_context_info(self, name):
        return next((c for c in SALES_CONTEXTS if c["name"] == name), None)


def test_the_explanation_note_names_the_data_used():
    from app.services.query_engine import context_mismatch

    mismatch = context_mismatch("feed_sales", "เดือน กันยายน มีรายได้ของหน่วยงานไหน ผิดปกติ", _Schema())
    assert mismatch["explain_note"] == (
        "**ชื่อตัวเลข:** คำถามมีคำว่า “รายได้” แต่ข้อมูลที่ใช้ตอบคือ ยอดขายจาก Sales DW รายเดือน (DataFeed sales) — "
        "เรียกตัวเลขตามข้อมูลนี้ และบอกหนึ่งบรรทัดว่าตัวเลขนี้ไม่ใช่ข้อมูลของ DataFeed revenue")
    assert mismatch["prompt_note"].startswith("**แหล่งข้อมูลอาจไม่ตรงกับคำถาม:**")  # chat's, unchanged
    assert context_mismatch("feed_sales", "ยอดขายเดือนกันยายน", _Schema()) is None


def test_the_note_and_the_rules_reach_the_explanation_only():
    from app.providers.chart_postprocessor import build_explain_prompt
    from app.services.data_sources import request_explain_note

    token = request_explain_note.set("**ชื่อตัวเลข:** ทดสอบ")
    try:
        prompt = build_explain_prompt("q", "SELECT 1", PRACTICE)
        assert "**ชื่อตัวเลข:** ทดสอบ" in prompt and "แหล่งข้อมูลอาจไม่ตรง" not in prompt
        assert "ทดสอบ" not in hybrid_flow.scope_note()  # pass 1 / pass 2 prompts stay as they were
    finally:
        request_explain_note.reset(token)
    prompt = build_explain_prompt("q", "SELECT 1", PRACTICE)
    assert "ชื่อตัวเลข" not in prompt
    assert ("เฉพาะแถวที่ส่วนต่าง ≥ 5 ล้านบาท และ (เปลี่ยน ≥ 30% หรือ ≥ 2 SD เมื่อผลมี SD) และบอกเกณฑ์นี้ในคำบรรยาย"
            in prompt)
    assert "เดือนมกราคมถึงเดือนก่อนเดือนที่ถามของปีเดียวกัน" in prompt
