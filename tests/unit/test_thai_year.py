"""The Buddhist-era years in an explanation are the years of its answer (RESULT_F11 §9).

The SQL chose 2026 and the text said "สิงหาคม 2568" / "ปี 2566" — the number was right and the year a
user reads it under was not. build_explanation now checks the text's years against the rows, the SQL
and the question.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.ai.hybrid_flow import build_explanation
from app.services.ai.response_utils import prepare_data_for_explanation
from app.services.ai.thai_year import answer_years, fix_explanation, fix_text


async def _explain(text: str, question: str, sql: str, data: list) -> dict:
    provider = SimpleNamespace(model="m", explain_result=AsyncMock(
        return_value={"explanation": text, "chart_title": text.split("\n")[0], "visualization": "table"}))
    return await build_explanation(
        SimpleNamespace(provider=provider), question=question, sql_query=sql, data=data, cheap_model=None,
        prepare_data_for_explanation=prepare_data_for_explanation, dim_families=None, hierarchy_info=None,
        schema_metadata=None)


@pytest.mark.asyncio
async def test_period_only_in_the_sql_gets_its_own_year():
    result = await _explain("รายได้รวมเดือนสิงหาคม 2568 อยู่ที่ 3,434.07 ล้านบาท", "รายได้รวม",
                            "SELECT SUM(revenue) FROM feed_revenue_fact_bu_monthly WHERE year_month = 202608",
                            [{"รายได้รวม": 3434072699.62}])
    assert result["explanation"] == "รายได้รวมเดือนสิงหาคม 2569 อยู่ที่ 3,434.07 ล้านบาท"
    assert result["chart_title"] == result["explanation"]


@pytest.mark.asyncio
async def test_a_year_in_the_rows_wins_over_the_models_conversion():
    # the rows said year 2026 in plain sight and the text still said 2566 / 2565
    text = "ยอดสะสมเดือนสิงหาคม 2566 เทียบกับเดือนเดียวกันของปี 2565 เพิ่มขึ้น 82.09%"
    result = await _explain(text, "เทียบงวดเดียวกันกับปีก่อนหน้า ของบริการ CCTV แบบสะสม",
                            "SELECT year, month, ... WHERE year_month IN (202608, 202508)",
                            [{"year": 2026, "month": 8, "curr": 69711711.33, "prev": 38283256.61}])
    assert result["explanation"] == "ยอดสะสมเดือนสิงหาคม 2569 เทียบกับเดือนเดียวกันของปี 2568 เพิ่มขึ้น 82.09%"


def test_the_prior_year_of_a_comparison_keeps_its_place():
    # SQL names 202608 only (the prior year is `year_month - 100`) — a slip of one on both stays relative
    years = answer_years("เทียบงวดเดียวกันกับปีก่อนหน้า", "WHERE curr.year_month = 202608", [{"งวด": 202608}])
    assert fix_text("เดือน 8 ปี 2568 เทียบ เดือน 8 ปี 2567", years) == "เดือน 8 ปี 2569 เทียบ เดือน 8 ปี 2568"
    # already right: nothing moves, although 2568 is not a literal of the SQL
    assert fix_text("เดือน 8 ปี 2569 เทียบ เดือน 8 ปี 2568", years) == "เดือน 8 ปี 2569 เทียบ เดือน 8 ปี 2568"
    # ...even when the prior year is named more often than the current one (it was shifted to 2570)
    right = "ส.ค. 2569 เทียบ ส.ค. 2568 | ปี 2569 | ปี 2568 ติดลบ | ปี 2568 ฐานต่ำ"
    assert fix_text(right, years) == right


def test_a_year_the_user_typed_is_left_alone():
    years = answer_years("รายได้ บริการ 102020019 ปี 69", "WHERE year = 2026", [{"s": 6630814636.83}])
    assert fix_text("รายได้ปี 2569 รวม 6,630.81 ล้านบาท", years) == "รายได้ปี 2569 รวม 6,630.81 ล้านบาท"
    # a year only the question names (no rows for it) is not "corrected" onto the data's year
    years = answer_years("รายได้ปี 2570", "WHERE year = 2026", [{"s": 1.0}])
    assert fix_text("ยังไม่มีข้อมูลปี 2570 จึงแสดงปี 2569", years) == "ยังไม่มีข้อมูลปี 2570 จึงแสดงปี 2569"


def test_amounts_and_period_keys_are_not_years():
    years = answer_years("รายได้รวม", "WHERE year_month = 202608", [])
    text = "งวด 202608 รวม 12,568.30 และ 2568.12 ล้านบาท ของสิงหาคม 2568"
    assert fix_text(text, years) == "งวด 202608 รวม 12,568.30 และ 2568.12 ล้านบาท ของสิงหาคม 2569"


def test_a_column_that_stores_buddhist_years_counts_as_it_is():
    years = answer_years("รายได้ปีนี้", 'WHERE "ปี" = 2569', [{"ปี": 2569, "s": 1.0}])
    assert fix_text("รายได้ปี 2569", years) == "รายได้ปี 2569"


@pytest.mark.asyncio
async def test_an_amount_is_never_rewritten_as_a_year():
    # "2500" after รายได้รวม is 2,500 million baht — rewriting every 25xx made it "2569 ล้านบาท"
    text = "รายได้รวม 2500 ล้านบาท"
    result = await _explain(text, "รายได้รวม", "SELECT SUM(revenue) AS total FROM revenue_search WHERE year = 2026",
                            [{"total": 2500000000}])
    assert result["explanation"] == text
    years = answer_years("รายได้", "WHERE year = 2026", [])
    assert fix_text("ค่าธรรมเนียมต่อปี 2500 บาท", years) == "ค่าธรรมเนียมต่อปี 2500 บาท"  # its unit says amount
    # a year next to an amount: only the year moves
    assert fix_text("รายได้ปี 2568 รวม 2568 ล้านบาท", years) == "รายได้ปี 2569 รวม 2568 ล้านบาท"


def test_an_amount_in_the_rows_names_no_year():
    # SQL chose 2026, the total was 2,568: that total made "ปี 2568" look like a year of the answer
    sql = "SELECT SUM(revenue) AS total FROM revenue_search WHERE year = 2026"
    assert fix_explanation("รายได้ปี 2568 รวม 2,568 บาท", "รายได้ปีนี้", sql, [{"total": 2568}]) == \
        "รายได้ปี 2569 รวม 2,568 บาท"
    # a measure named like a period (feed_ebt's ebt_month is baht) is known from the metadata
    meta = [{"column_name": "time_key", "is_summable": 0}, {"column_name": "ebt_month", "is_summable": 1}]
    assert answer_years("กำไรเดือนนี้", "SELECT ebt_month FROM t WHERE time_key = 202608", [{"ebt_month": 2568.0}],
                        meta) == {2569}


def test_only_the_sqls_period_conditions_count():
    sql = "SELECT gl_code, SUM(revenue) FROM t WHERE gl_code = 2025 AND revenue > 2568 AND year = 2026 LIMIT 2000"
    assert answer_years("รายได้", sql, []) == {2569}
    between = "SELECT SUM(x) FROM t WHERE time_key BETWEEN 202501 AND 202608 GROUP BY 1"
    assert answer_years("รายได้", between, []) == {2568, 2569}
    case = 'SELECT SUM(CASE WHEN "งวด" = 202508 THEN x END), SUM(CASE WHEN CAST(year_month AS INT) = 202608 THEN x END)'
    assert answer_years("เทียบปีก่อน", case, []) == {2568, 2569}


def test_every_year_the_text_marks_moves_together():
    years = answer_years("เทียบปีก่อน", "WHERE year_month IN (202608, 202508)", [])
    assert fix_text("ระหว่างปี 2566 กับ 2565 และช่วง ส.ค.2566", years) == "ระหว่างปี 2569 กับ 2568 และช่วง ส.ค.2569"
    assert fix_text("ปี 2566-2565 เพิ่มขึ้น", years) == "ปี 2569-2568 เพิ่มขึ้น"
    assert fix_text("รายได้รวมเดือนสิงหาคม 2568.", answer_years("", "WHERE year = 2026", [])) == \
        "รายได้รวมเดือนสิงหาคม 2569."  # a year that ends a sentence is still a year


@pytest.mark.asyncio
async def test_a_title_that_copied_the_question_keeps_its_year():
    # portal 2026-09-25: the title copied "ปี 2569" from the question, the body converted 2026 into 2566 — one
    # year right and one wrong, so no single shift gained anything and the text went out as it was
    text = "### สัดส่วนรายได้ของ ICT Solution ในปี 2569\n\nรายได้รวมในปี 2566 พบว่า ... ทั้งหมดในปี 2566 ขณะที่"
    result = await _explain(text, "สัดส่วนรายได้ ระหว่าง ict solution รายย่อย กับ บริการ ict solution เป็นกี่ % ของปี 2569",
                            "SELECT product_name, SUM(revenue) FROM feed_revenue_fact_product_monthly "
                            "WHERE year = 2026 AND product_name LIKE '%ict solution%' GROUP BY product_name",
                            [{"product_name": "ICT Solution", "รายได้รวม": 557427134.57}])
    assert result["explanation"] == text.replace("ปี 2566", "ปี 2569")
    # a comparison in the body moves as one; the title's right year is not dragged along to 2572
    years = answer_years("รายได้ปี 2569 เทียบปีก่อน", "WHERE year IN (2026, 2025)", [])
    assert fix_text("ปี 2569 เทียบ 2568: ปี 2566 สูงกว่าปี 2565", years) == "ปี 2569 เทียบ 2568: ปี 2569 สูงกว่าปี 2568"
    assert fix_text("ปี 2569: ปี 2566 สูงกว่าปี 2565", years) == "ปี 2569: ปี 2569 สูงกว่าปี 2568"


def test_the_explain_prompt_hands_over_the_converted_years():
    # converting 2026 was the model's own arithmetic — the prompt now carries the result
    from app.providers.chart_postprocessor import build_explain_prompt

    prompt = build_explain_prompt("สัดส่วนรายได้ของปี 2569", "SELECT p, SUM(revenue) FROM t WHERE year = 2026 GROUP BY p",
                                  [{"p": "ICT Solution", "s": 557427134.57}])
    assert "ค.ศ. 2026 = พ.ศ. 2569" in prompt
    assert "ปี พ.ศ. ของข้อมูลนี้" not in build_explain_prompt("รายได้แยกกลุ่ม", "SELECT bu, SUM(x) FROM t GROUP BY bu",
                                                             [{"bu": "Mobile", "s": 1.0}])
