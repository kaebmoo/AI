"""The real-question scorer reads what the user sees — text and period, not only the numbers in data.

RESULT_F11 §9: the answer to "รายได้รวม" had the right 3,434.07 in `data` and said "สิงหาคม 2568"
in the text (the rows were 2569); a score that read only `data` called it right.
"""

import json

from scripts.eval.run_portal_questions import QUESTIONS, score

SPEC = {q["id"]: q for q in json.loads(QUESTIONS.read_text())["questions"]}
AUG_2569 = [{"รายได้รวม": 3434072699.62}]


def test_right_number_wrong_year_in_text_fails():
    s = score(SPEC["P01"], {"answer": "รายได้รวมเดือนสิงหาคม 2568 = 3,434.07 ล้านบาท", "data": AUG_2569})
    assert s["numbers"] and not s["years"] and not s["ok"]


def test_right_number_right_year_and_base_passes():
    s = score(SPEC["P01"], {"answer": "รายได้รวมเดือนสิงหาคม 2569 = 3,434.07 ล้านบาท", "data": AUG_2569})
    assert s["ok"], s


def test_question_without_a_period_needs_the_answer_to_name_one():
    s = score(SPEC["P01"], {"answer": "รายได้รวม 3,434.07 ล้านบาท", "data": AUG_2569})
    assert s["numbers"] and s["years"] and not s["base"] and not s["ok"]


def test_amounts_and_period_keys_are_not_years():
    s = score(SPEC["P01"], {"answer": "สิงหาคม 2569 (งวด 202608) รวม 12,568.3 และ 2568.12 ล้านบาท", "data": AUG_2569})
    assert s["years"], s


def test_bg8_is_net_or_left_out_never_a_sum_of_months():
    """Owner 2026-09-21: other income's months do not add up to its year to date, and a business view
    need not count it. A ranking that sums BG8's months fails; one without BG8 passes."""
    net = next(a for a in SPEC["P10"]["accept"] if "ไม่รวม BG8" not in a["base"])
    core = next(a for a in SPEC["P10"]["accept"] if "ไม่รวม BG8" in a["base"])
    answer = "10 บริการที่มีรายได้สูงสุดปี 2569 — อันดับ 1 บริการ NT Broadband 6,630.81 ล้านบาท"
    rows = lambda alt: [{"product_name": r["key"][0][0], "รายได้": r["value"] * 1e6} for r in alt["rows"]]  # noqa: E731
    raw = rows(net)
    raw[2] = {"product_name": "รายได้อื่น", "รายได้": 2476.07e6}  # Jan–Aug added up, not the year to date
    assert raw[2]["product_name"] == net["rows"][2]["key"][0][0]
    assert not score(SPEC["P10"], {"answer": answer, "data": raw})["ok"]
    assert score(SPEC["P10"], {"answer": answer, "data": rows(net)})["ok"]
    assert score(SPEC["P10"], {"answer": answer, "data": rows(core)})["ok"]


def test_refusal_passes_only_without_amounts():
    q = SPEC["P12"]
    assert score(q, {"answer": "ชุดข้อมูลนี้ไม่มีค่าใช้จ่าย", "data": [{"message": "ไม่มีข้อมูลค่าใช้จ่าย"}]})["ok"]
    assert not score(q, {"answer": "ชุดข้อมูลนี้ไม่มีค่าใช้จ่าย", "data": [{"รายได้": 3434072699.62}]})["ok"]


def test_growth_needs_both_periods_and_the_percent():
    q = SPEC["P14"]
    raw = {"answer": "ส.ค. 2569 เทียบ ส.ค. 2568 ลดลง 305.97%",
           "data": [{"curr": 3434072699.62, "prev": -1667308484.01, "pct": -305.97}]}
    assert not score(q, raw)["numbers"]  # ⚠4: the raw base is negative — not a growth figure
    comparable = {"answer": "ส.ค. 2569 3,434.07 ล้านบาท เทียบ ส.ค. 2568 3,314.22 ล้านบาท เพิ่มขึ้น 3.62%",
                  "data": [{"curr": 3434072699.62, "prev": 3314216283.55, "pct": 3.6163}]}
    assert score(q, comparable)["ok"]
    only_percent = {**comparable, "answer": "ส.ค. 2569 เทียบ ส.ค. 2568 เพิ่มขึ้น 3.62%"}
    assert not score(q, only_percent)["said"]  # "เพิ่มขึ้นหรือลดลงเท่าไหร่" asks for the amounts too


def test_the_text_must_state_the_figure_the_rows_carry():
    """P01 said "1 ล้านบาท" over rows of 3,434.07 million and passed on `data` alone."""
    s = score(SPEC["P01"], {"answer": "รายได้รวมเดือนสิงหาคม 2569 = 1 ล้านบาท", "data": AUG_2569})
    assert s["numbers"] and not s["said"] and not s["ok"]
    for said in ("ประมาณ 3,434 ล้านบาท", "**3,434.07** ล้านบาท", "3.4 พันล้านบาท", "3,434,072,699.62 บาท"):
        assert score(SPEC["P01"], {"answer": f"รายได้รวมเดือนสิงหาคม 2569 {said}", "data": AUG_2569})["ok"], said
    assert not score(SPEC["P01"], {"answer": "รายได้รวมเดือนสิงหาคม 2569 3,434.07 บาท", "data": AUG_2569})["said"]


def test_years_come_from_the_oracle_not_from_the_cells():
    """A count of 2025 in the response made 2568 a year of the answer; so would any cell that looks like one."""
    s = score(SPEC["P01"], {"answer": "รายได้เดือนสิงหาคม 2569 3,434.07 ล้านบาท เทียบปี 2568",
                            "data": [{"รายได้รวม": 3434072699.62, "count": 2025}]})
    assert not s["years"] and not s["ok"]
    # a year that ends a sentence is still a year
    assert not score(SPEC["P01"], {"answer": "รายได้รวม 3,434.07 ล้านบาท ของเดือนสิงหาคม 2568.", "data": AUG_2569})["years"]
