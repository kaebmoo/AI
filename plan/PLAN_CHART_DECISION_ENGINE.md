# PLAN_CHART_DECISION_ENGINE — แยกการตัดสินใจกราฟออกจาก LLM payload อย่างถาวร

> อ้างอิงจากการ reproduce ด้วยข้อมูลจริง (ค่าใช้จ่าย 19 หมวด × 12 เดือน = 217 แถว) วันที่ 2026-07-13
> ต่อยอดจาก PLAN_UI_CHART_IMPROVEMENT (Wave 1 ✅) — ปัญหารอบนี้**ไม่ใช่** rule ผิด แต่เป็น "rule ที่ถูกต้องรันบนข้อมูลที่ถูกทำลายแล้ว"
> รูปแบบ wave เดียวกับ PLAN_FIX_MASTER

---

## Root cause (พิสูจน์แล้ว ไม่ใช่การเดา)

**เคสจริง:** คำถาม "ค่าใช้จ่ายรายหมวดบัญชี รายเดือน" → SQL ถูกต้อง (3 คอลัมน์: หมวดบัญชี, เดือน, ค่าใช้จ่ายรวม, 217 แถว) → แต่ได้ vertical bar ที่**รวมทุกเดือนเป็นก้อนเดียว** แทน heatmap/stacked bar

**ลำดับเหตุการณ์ที่ reproduce ได้:**

| ขั้น | ที่เกิด | สิ่งที่เกิด |
|------|---------|------------|
| 1 | `hybrid_flow.py` `build_explanation()` | เรียก `prepare_data_for_explanation(data)` ก่อนส่งเข้า provider |
| 2 | `response_utils.py:16` | 217 แถว > threshold 200 → เข้าโหมด aggregate |
| 3 | `response_utils.py:46-53, 66-69` | drop คอลัมน์ตาม cardinality **จากน้อยไปมาก** → `เดือน` (12 ค่า) โดนตัดก่อน `หมวดบัญชี` (19 ค่า) เสมอ → เหลือ 19 แถว **ไม่มีมิติเวลา** |
| 4 | `claude_provider.py:130-186` (ทุก provider เหมือนกัน) | ทั้ง LLM prompt และ `enforce_*` + `enrich_chart_config` รันบน data ที่ aggregate แล้ว → `_infer_matrix_shape` ไม่เห็น matrix (ไม่มีคอลัมน์เวลาแล้ว) → ได้ `bar_chart` ซึ่ง "ถูก" สำหรับข้อมูล 19 แถวที่มันเห็น |
| 5 | frontend | render จาก full data 217 แถว ด้วย config ที่ไม่มี series → aggregate ข้ามเดือนเป็นแท่งเดียว |

**หลักฐาน:** ตัวเลขในกราฟที่พัง (ค่าเสื่อมราคา ≈ 11.77 พันล้าน) = SUM ทั้งปีพอดี ตรงกับ output ของ `prepare_data_for_explanation` แถวต่อแถว

**การยืนยันฝั่งตรงข้าม:** รัน pipeline เดิม (`enforce_time_series_rule` → `enforce_categorical_axis_rule` → `enrich_chart_config`) บน**ข้อมูลเต็ม 217 แถว** โดยจำลอง LLM ตอบผิดเป็น `bar_chart` → `_infer_matrix_shape` จับ time_matrix ได้ (12 คาบ × 19 หมวด, coverage 0.95) → repair เป็น `heatmap` + chart_spec ถูกต้องครบ (temporal x, value_desc y, diverging_zero) **rule ที่มีอยู่ดีอยู่แล้ว — มันแค่ไม่เคยได้เห็นข้อมูลจริง**

**ขอบเขตความเสียหาย:** ทุกคำถามที่ผลลัพธ์ 201–1,000+ แถวและมีมิติเวลา (ซึ่งคือคำถาม "รายเดือน/รายไตรมาส × มิติอื่น" เกือบทั้งหมด) จะโดนแบบนี้ และ **explanation ของ LLM ก็ผิดด้วย** — เล่ายอดรวมทั้งปีทั้งที่ user ถามรายเดือน

---

## หลักการออกแบบ (ยั่งยืน)

```
                    ┌─ full data ──→ [Data Profiler] ──→ [Decision Engine] ──→ ChartSpec ─┐
SQL → execute ──┤                                          ↑ (hint เท่านั้น)               ├─→ response
                    └─ explain payload (ตัดได้ตามใจ) ──→ [LLM] ──→ narrative + viz hint ──┘
```

1. **การตัดสินใจกราฟกิน "ข้อมูลเต็ม" เสมอ** — ไม่ผ่าน payload ที่ถูกตัด/ยุบเพื่อประหยัด token การ profile ข้อมูล 100k แถวเป็น O(n) ราคาถูกกว่า LLM call หลายพันเท่า ไม่มีเหตุผลต้อง profile จากข้อมูลย่อ
2. **LLM มีสิทธิ์เสนอ ไม่มีสิทธิ์ชี้ขาด** — `visualization` จาก LLM เป็นแค่ hint; Decision Engine (deterministic, test ได้) เป็นผู้ตัดสินจาก profile และมีสิทธิ์ veto
3. **payload ของ LLM ตัดเพื่อประหยัดได้เต็มที่** — แต่ต้องตัดแบบรักษาโครงเรื่อง (มิติเวลาห้ามหาย) เพราะมันกระทบ narrative ไม่ใช่แค่กราฟ
4. **การตัดสินใจอยู่ที่เดียว** — ตอนนี้ rule กระจายอยู่ใน providers ×3 + chat.py + template_answer + frontend legacy path; ทุกที่ที่ซ้ำคือโอกาส drift

---

## Wave A — Hotfix: อุดรูรั่ว (diff เล็ก ผลทันที)

### A1. Re-enrich ด้วยข้อมูลเต็มหลัง provider ตอบ

`enrich_chart_config()` ออกแบบมา repair config จาก data shape อยู่แล้ว (พิสูจน์แล้วว่า repair `bar_chart` → `heatmap` ได้กับเคสจริง) — แค่เรียกซ้ำด้วย **full data** หลังจาก provider ตอบ

ไฟล์: `app/services/ai/hybrid_flow.py` ใน `build_explanation()` หลังได้ `explanation` จาก provider:

```python
# provider เห็นแค่ explain_data (อาจถูก aggregate) — ตัดสินใจกราฟใหม่จาก full data
if isinstance(explanation, dict) and explanation.get("chart_config") and len(data) != len(explain_data):
    explanation = enrich_chart_config(
        parsed_result=explanation,
        data=data,                      # ← full result set
        schema_metadata=schema_metadata,
        chart_title=explanation.get("chart_title", ""),
    )
```

หมายเหตุ: เงื่อนไข `len(data) != len(explain_data)` ทำให้เคสปกติ (≤200 แถว) ไม่โดน enrich ซ้ำ — พฤติกรรมเดิมไม่เปลี่ยน

### A2. `prepare_data_for_explanation` ห้าม drop มิติเวลา

ไฟล์: `app/services/ai/response_utils.py` — ปัญหาคือ drop ตาม cardinality น้อย→มาก ซึ่งคอลัมน์เวลา (12 เดือน / 4 ไตรมาส) cardinality ต่ำสุดโดยธรรมชาติ โดนตัดก่อนเสมอ ทั้งที่เป็นแกนของคำถาม

แก้เป็น: (1) คอลัมน์เวลา (ใช้ `_is_time_column` / `dim_keywords` เดิม) เป็น **protected ไม่มีเงื่อนไข** (2) ถ้ายังเกิน 200 กลุ่ม ให้ยุบมิติ categorical ที่ cardinality สูงสุดเป็น **Top-N + "อื่นๆ"** แทนการ drop ทั้งคอลัมน์:

```python
# แทนที่ลูป drop เดิม (:66-69)
time_cols = {c for c in all_dim_cols if _is_time_col(c)}          # protected เสมอ
droppable = [c for c in cols_by_cardinality if c not in time_cols]
# ยุบ categorical ที่ใหญ่สุดเป็น Top-N + อื่นๆ ให้ groups ≤ 200 ก่อนจะยอม drop คอลัมน์อื่น
```

ผลพลอยได้: narrative ของ LLM สำหรับคำถาม "รายเดือน" กลับมาถูกต้องด้วย (เดิมเล่ายอดปีโดยไม่บอกใคร)

### A3. Unit test ล็อกเคสนี้

`tests/unit/test_chart_postprocessor.py` เพิ่ม: ข้อมูล 19 หมวด × 12 เดือน (217 แถว มี negative 1 ค่า) → assert หลัง pipeline เต็มได้ family heatmap/stacked_bar และ `series_column` ต้องไม่ว่าง; `tests/unit/test_response_utils.py`: aggregate แล้วคอลัมน์เวลาต้องยังอยู่

---

## Wave B — Chart Decision Engine: รวมการตัดสินใจไว้ที่เดียว

> Wave A ทำให้หายเจ็บ แต่โครงยังเปราะ: การตัดสินใจยังฝังใน provider ×3 (`claude_provider.py:171-186`, `gemini_provider.py:206-221`, `matcha_provider.py:134-150`) + `template_answer.py:78` + chart-switch ใน `chat.py:406` — ที่ใดที่หนึ่งจะ drift อีก

### B1. สร้าง `app/services/chart/` package

```
app/services/chart/
├── profiler.py    # profile_result(data, schema_metadata) → DataProfile
├── engine.py      # decide(profile, llm_hint=None, requested_type=None) → ChartDecision
└── __init__.py
```

**profiler.py** — pure function, O(n) รอบเดียว, ไม่มี DB/LLM:

```python
@dataclass(frozen=True)
class ColumnProfile:
    name: str
    kind: Literal["temporal", "nominal", "quantitative"]  # schema_metadata ก่อน, heuristic สำรอง
    cardinality: int
    has_negative: bool = False       # เฉพาะ quantitative

@dataclass(frozen=True)
class DataProfile:
    row_count: int
    columns: list[ColumnProfile]
    pair_coverage: dict[tuple[str, str], float]   # ความหนาแน่น matrix ของคู่ dimension
```

**engine.py** — decision table เดียว รวม logic ที่มีอยู่แล้วทั้งหมดเข้ามา (ย้าย ไม่เขียนใหม่): `_infer_matrix_shape`, `enforce_time_series_rule`, `enforce_categorical_axis_rule`, `enforce_dimension_family_rule`, negative-value rules, Top-N/max_series → output เป็น `ChartDecision` ที่มี `ChartSpec` (โครงสร้างเดิมใน `app/models/chart.py` ใช้ต่อได้เลย) + `available_types` + `warnings`

ลำดับความเชื่อ: **data profile > requested_type (user กด toolbar) > llm_hint** โดย requested_type ที่ขัด profile (เช่น line โดยไม่มีแกนเวลา) โดน veto พร้อม warning อธิบายเหตุผล

### B2. ถอดการตัดสินใจออกจาก providers

`explain_result()` ของทุก provider เหลือหน้าที่: narrative + `chart_title` + `visualization` (เป็น hint) — ตัดการเรียก `enforce_*`/`auto_detect`/`enrich_chart_config` ออก แล้วผู้เรียก (`hybrid_flow.py`, `chat.py`, `template_answer.py`) เรียก engine ด้วย full data ที่เดียว:

```python
profile = profile_result(data, schema_metadata)          # full data เสมอ
decision = decide(profile, llm_hint=explanation.get("visualization"))
```

ข้อดีที่ได้ฟรี: provider ใหม่ในอนาคต (หรือ model ที่ตอบ chart_config มั่ว) ไม่มีทางทำกราฟพังได้อีก เพราะไม่ได้อยู่ใน critical path ของการตัดสินใจแล้ว

### B3. chart-switch ใช้ engine เดียวกัน

`chat.py:395-425` (is_chart_only path) เปลี่ยนจาก mock_result + enrich เป็น `decide(profile, requested_type=intent["requested_type"])` — ปิดช่องที่ user กด horizontal_bar กับ 19 หมวด × 12 เดือนแล้วได้กราฟสูง 2,600px (engine จะ apply Top-N + อื่นๆ หรือ veto พร้อมคำอธิบาย)

### B4. เก็บ contract test ระหว่าง backend ↔ frontend

frontend เชื่อ `chart_spec` เป็นหลัก (`chartDataTransform.ts:188`) — เพิ่ม JSON Schema ของ ChartSpec เป็นไฟล์เดียวที่สอง repo อ้างร่วมกัน + test ว่า `decide()` ทุก path ผลิต spec ที่ validate ผ่าน

---

## Wave C — Guardrails ปลายทาง + Feedback loop

### C1. Renderer guardrails (frontend)

- horizontal_bar: จำกัดจำนวนแท่ง = `max_series` เดิม (Top-N + อื่นๆ ที่ระดับ transform) + จำกัดความสูง canvas; แกน Y ใช้ `axisLabel.width` + `overflow: 'truncate'` ของ ECharts (ตัดที่ระดับแสดงผล ไม่ใช่ระดับข้อมูล — ชื่อเต็มอยู่ใน tooltip) — สอดคล้อง Wave 2 ของ PLAN_UI_CHART_IMPROVEMENT ไม่ทำซ้ำ
- ทุก chart type ที่ไม่มี case ใน `buildEChartsOption` ต้อง throw ไม่ใช่ silent fallback (บทเรียนจาก mixed_bar_line/scatter)

### C2. Golden case suite

`tests/golden_charts/*.json` — fixture ละเคส: `{name, rows (ย่อส่วนแต่โครงจริง), schema_metadata, expected_family, forbidden_families}` รัน parametrized ใน pytest เริ่มจาก 6 เคส:

1. 19 หมวด × 12 เดือน + negative (เคสวันนี้) → heatmap/stacked_bar, ห้าม bar เดี่ยว
2. 5 หมวด × 12 เดือน → multi_line
3. 8 หมวด ไม่มีเวลา → bar/horizontal_bar, ห้าม line
4. 250 แถว 1 มิติ + 1 measure → horizontal_bar Top-N
5. matrix สายงาน × สายงาน → heatmap
6. 1 แถว → single_value ไม่มีกราฟ

### C3. Feedback loop จากพฤติกรรมจริง

ทุกครั้งที่ user กดเปลี่ยนชนิดกราฟ (chart-switch) = สัญญาณว่า engine เลือกไม่ตรงใจ → log `(question, DataProfile summary, decision, requested_type)` ลงตาราง feedback ที่มีอยู่ → รีวิวรายเดือน เคสไหนซ้ำ ๆ ให้เพิ่มเป็น golden case แล้วแก้ decision table — นี่คือกลไกที่ทำให้ระบบ "ดีขึ้นเรื่อย ๆ" แทนการไล่แก้ทีละ screenshot

---

## ลำดับการทำ + Definition of Done

| Wave | ขนาด | DoD |
|------|------|-----|
| A1–A3 | ~1 วัน | เคส 217 แถวได้ heatmap end-to-end; pytest เดิมผ่านครบ; narrative กล่าวถึงรายเดือน |
| B1–B4 | ~3-4 วัน | `grep enforce_\|enrich_chart_config app/providers/` = 0 ผลลัพธ์; ทุก path ผ่าน `decide()`; golden 6 เคสผ่าน |
| C1–C3 | ~2 วัน | ไม่มีกราฟสูงเกิน viewport จาก chart-switch; feedback log ใช้งานจริง |

**ความเสี่ยงที่ต้องระวังตอน implement:**
- A1 ทำให้ `visualization` ใน narrative ของ LLM กับกราฟจริงต่างกันได้ — ดี แต่ต้องแน่ใจว่า explanation ไม่พูดถึงชนิดกราฟ (prompt ห้ามไว้แล้วใน `build_explain_prompt` ข้อ DO NOT)
- B2 เปลี่ยน contract ของ `explain_result` — ทำทีละ provider โดยให้ engine ทำงานแบบ "ทับ" ผลของ provider ก่อน (Wave A pattern) แล้วค่อยถอด enforce ออกจาก provider เมื่อ test ครอบแล้ว
- threshold 200 แถวใน `response_utils` เป็นคนละเรื่องกับ row cap ของ SQL (F4) — อย่าสับสนตอนแก้
