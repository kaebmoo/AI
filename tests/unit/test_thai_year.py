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
from app.services.ai.thai_year import answer_years, fix_text


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
