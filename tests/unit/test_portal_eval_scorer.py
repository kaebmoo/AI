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


def test_bg8_raw_ytd_is_wrong_strict_and_right_only_when_lenient():
    ranked = SPEC["P10"]["accept"]
    raw = next(a for a in ranked if a.get("lenient"))
    data = [{"product_name": r["key"][0][0], "รายได้": r["value"] * 1e6} for r in raw["rows"]]
    answer = "10 บริการที่มีรายได้สูงสุดปี 2569"
    assert not score(SPEC["P10"], {"answer": answer, "data": data})["ok"]
    assert score(SPEC["P10"], {"answer": answer, "data": data}, lenient=True)["ok"]


def test_refusal_passes_only_without_amounts():
    q = SPEC["P12"]
    assert score(q, {"answer": "ชุดข้อมูลนี้ไม่มีค่าใช้จ่าย", "data": [{"message": "ไม่มีข้อมูลค่าใช้จ่าย"}]})["ok"]
    assert not score(q, {"answer": "ชุดข้อมูลนี้ไม่มีค่าใช้จ่าย", "data": [{"รายได้": 3434072699.62}]})["ok"]


def test_growth_needs_both_periods_and_the_percent():
    q = SPEC["P14"]
    raw = {"answer": "ส.ค. 2569 เทียบ ส.ค. 2568 ลดลง 305.97%",
           "data": [{"curr": 3434072699.62, "prev": -1667308484.01, "pct": -305.97}]}
    assert not score(q, raw)["numbers"]  # ⚠4: the raw base is negative — not a growth figure
    comparable = {"answer": "ส.ค. 2569 เทียบ ส.ค. 2568 เพิ่มขึ้น 3.62%",
                  "data": [{"curr": 3434072699.62, "prev": 3314216283.55, "pct": 3.6163}]}
    assert score(q, comparable)["ok"]
