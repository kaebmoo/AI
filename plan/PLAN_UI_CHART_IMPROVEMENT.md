# PLAN_UI_CHART_IMPROVEMENT — ปรับปรุง Chart/UI ของ NT AI Assistant

> อ้างอิงจากการอ่านโค้ดจริง (frontend/ และ app/) วันที่ 2026-07-12
> เกณฑ์เปรียบเทียบ: skill `dashboard-design` (Databricks มิ.ย. 2026) และ `nt-brand-guidelines` (#FFD100 official)
> รูปแบบ wave เดียวกับ PLAN_FIX_MASTER

---

## สรุป root cause (จากโค้ดจริง ไม่ใช่การเดา)

### ปัญหา 1: line chart กับข้อมูลหมวดบัญชี (ไม่มีคาบเวลา)

การเลือกชนิดกราฟเป็น pipeline 3 ชั้นใน `app/providers/chart_postprocessor.py`:
LLM เลือก `visualization` ผ่าน prompt (`build_explain_prompt()` :281–316) → กฎ deterministic แก้ทับ (`enforce_time_series_rule()` :61–110, `enforce_dimension_family_rule()` :113–166) → `enrich_chart_config()` map เป็น ECharts type

**ช่องโหว่:** `enforce_time_series_rule` บังคับแค่ "ถ้ามีคอลัมน์เวลา ต้องอยู่แกน X" แต่**ไม่มีกฎกลับด้าน** — ถ้า LLM ตอบ `line_chart` ทั้งที่ `category_column` ไม่ใช่เวลา ไม่มีอะไรดักเลย ฝั่ง frontend (`chartDataTransform.ts:126,150-151`) เชื่อ `suggested_type` จาก backend 100% ไม่ validate ว่าแกน X เป็น temporal

ช่องโหว่รอง:
- `_suggest_available_types()` (:543–561) ใส่ `line` ใน `available_types` แม้ category ไม่ใช่เวลา → toolbar ให้ user กดเลือกผิดเองได้
- fallback `auto_detect_chart_config()` (:321–492 — ตัวนี้มีกฎ time ถูกต้อง) ต่อเฉพาะ `matcha_provider.py:139` — Claude/Gemini ไม่ได้ใช้
- frontend legacy path (`DataChart.tsx:1320-1328`) ตรวจ time ด้วย substring ชื่อคอลัมน์ (`'ปี'`, `'เดือน'`) — คำไทยที่มี "ปี" ปนจะถูกมองเป็น time series

### ปัญหา 2: ตัวอักษรแกนแสดงไม่ครบ

Renderer หลักคือ ECharts (`DataChart.tsx:712`, web ใช้ ECharts เสมอ) — สาเหตุเรียงตามน้ำหนัก:

1. **ตัด label ทิ้งที่ระดับข้อมูล ไม่ใช่ระดับแสดงผล** — ทุก builder เรียก `truncateLabel()` (`chartUtils.ts:120-122`) ตัดเหลือ 12–20 ตัวอักษร*ก่อน*ส่งเข้า ECharts ชื่อเต็มหายถาวร แม้แต่ tooltip ก็โชว์ชื่อที่ถูกตัดแล้ว (`tooltipFormatter` `chartDataTransform.ts:59`)
2. **`truncateLabel` ใช้ `.length`/`.slice` แบบ UTF-16 code unit** — ภาษาไทยมีสระ/วรรณยุกต์เป็น combining mark การ slice อาจตัดกลางพยางค์ ได้ glyph พิการก่อน `...`
3. **horizontal bar และ heatmap ใช้ `containLabel: false` + `left: '25%'` ตายตัว** (`chartDataTransform.ts:348, 646-651`) — ชื่อหมวดบัญชียาว ๆ ถูก clip ที่ 25%
4. ไม่มี `axisLabel.width / overflow / ellipsis / hideOverlap` ที่ไหนเลย; rotate มีแค่ `> 6 categories ? 30 : 0`
5. **ไม่ set `fontFamily` ให้ ECharts เลย** — `Fonts` ใน `constants/theme.ts` ไม่ถูก import ใช้ในโค้ด chart; ฟอนต์ default อาจ render ไทยด้วย fallback metrics เพี้ยน
6. Pattern "ตัดบนแกน + ชื่อเต็มใน tooltip" มีเฉพาะ legacy gifted-charts path (`fullLabel`, `DataChart.tsx:1434-1439,1500`) — path หลัก (ECharts/web) ไม่มี

### ปัญหา 3: UI ไม่ตรง NT brand / หลัก dashboard

- `NT_CHART_PALETTE` (`chartColors.ts:6-17`) แท้จริงคือ Tailwind-500 สิบสี (น้ำเงิน `#3B82F6` เป็นสีนำ) — ขัดข้อห้าม NT "NO generic blue color schemes" และไม่มี `#FFD100` เลยทั้งที่ชื่อ NT_
- ขัดหลัก 60-30-10: ไม่มี accent color ที่สงวนไว้สำหรับ interactive element (toolbar เลือกชนิดกราฟ ควรใช้ NT yellow เป็น active state)
- palette 10 สี เกินช่วงแนะนำ 5–9 และมี emerald/red ใกล้กัน + `FINANCIAL_COLORS` เขียว/แดงล้วน — เสี่ยง colorblind (deuteranopia ~4.5%)
- `mixed_bar_line` และ `scatter` อยู่ใน enum backend (`app/models/chart.py:16-32`) และ toolbar label แต่ไม่มี case ใน switch ของ `buildEChartsOption` → เงียบ ๆ fallback เป็น vertical_bar (ผลลัพธ์ไม่ตรงปุ่มที่ user กด)

---

## Wave 1 — Correctness: กฎชนิดกราฟ (ทำก่อน, กระทบความถูกต้องของสารที่สื่อ)

> **สถานะ: ✅ DONE (2026-07-12)** — C1–C5 implement ครบ, unit test 19 เคสใหม่ผ่าน,
> pytest -q ทั้ง suite 572 passed / 3 skipped (baseline ก่อนแก้ 553 passed / 3 skipped),
> `tsc --noEmit` และ `eslint` บน frontend ไฟล์ที่แก้ไม่มี error ใหม่ (ของเดิมที่มีอยู่ก่อนไม่แตะ)
> **Post-review patch:** `_is_time_column()` เปลี่ยนจาก either/or (exact-match schema_metadata
> เท่านั้นถ้ามี `time_columns`) เป็น union (schema_metadata exact-match OR TIME_KEYS heuristic)
> — เดิมถ้า SQL alias คอลัมน์เวลา (เช่น `month AS "เดือน"`) จะไม่ match schema_metadata และถูก
> downgrade line→bar ผิด ตอนนี้ครอบทั้งสองทาง (false positive ฝั่งนี้แค่ "ไม่ downgrade" ปลอดภัยกว่า
> false negative ที่ทำลายกราฟถูก)
> ไฟล์ที่แก้: `app/providers/chart_postprocessor.py`, `claude_provider.py`, `gemini_provider.py`,
> `matcha_provider.py`, `app/schemas/chat.py`, `frontend/types/chart.ts`,
> `frontend/components/Chat/DataChart.tsx`, `tests/unit/test_chart_postprocessor.py` (ใหม่)
> ดูรายละเอียดความต่างจากแผนท้ายบทนี้ในสรุปงาน

### C1. เพิ่มกฎ "line/area ต้องมีแกนเวลา" (backend, deterministic)

ไฟล์: `app/providers/chart_postprocessor.py` — เพิ่มฟังก์ชันใหม่ เรียกต่อจาก `enforce_time_series_rule` ในทุก provider (`claude_provider.py:168-176`, `gemini_provider.py:204-206`, `matcha_provider.py:133-142`)

```python
TEMPORAL_TYPES = {"line_chart", "multi_line", "area", "stacked_area", "mixed_bar_line"}

def enforce_categorical_axis_rule(parsed_result, time_columns, data=None):
    """ถ้า LLM เสนอกราฟตระกูลเส้น แต่ category_column ไม่ใช่คอลัมน์เวลา
    ให้ downgrade เป็นตระกูลแท่ง (deterministic — ไม่เชื่อ LLM)"""
    viz = parsed_result.get("visualization")
    if viz not in TEMPORAL_TYPES:
        return parsed_result
    cat = (parsed_result.get("chart_config") or {}).get("category_column")
    if cat and _is_time_column(cat, time_columns):   # ใช้ helper เดียวกับ enforce_time_series_rule
        return parsed_result
    downgrade = {
        "line_chart": "bar_chart",
        "area": "bar_chart",
        "multi_line": "grouped_bar",
        "stacked_area": "stacked_bar",
        "mixed_bar_line": "grouped_bar",
    }
    parsed_result["visualization"] = downgrade[viz]
    cfg = parsed_result.setdefault("chart_config", {})
    cfg["warning"] = "ปรับจากกราฟเส้นเป็นกราฟแท่ง เนื่องจากแกน X ไม่ใช่คาบเวลา"
    return parsed_result
```

หมายเหตุ: ใช้ time detection แบบเดียวกับ `enforce_time_series_rule` (`schema_metadata` `dimension_group == 'time_period'` ก่อน แล้วค่อย `TIME_KEYS` :17–21) — อย่า copy heuristic ใหม่

### C2. กรอง `available_types` ตามแกนเวลา

ไฟล์: `chart_postprocessor.py` `_suggest_available_types()` (:543–561) — เมื่อ category ไม่ใช่ time ให้ตัด `line_chart / multi_line / area / stacked_area` ออกจาก list ป้องกัน toolbar เสนอตัวเลือกที่ผิดหลัก (path ที่ user สั่งเองผ่าน `intent_classifier.py` `CHART_TYPE_MAP` ยังคงทำงานได้ — explicit request ชนะ)

### C3. เสริม prompt (belt-and-braces, ไม่ใช่ที่พึ่งหลัก)

ไฟล์: `build_explain_prompt()` (:281–316) เพิ่มบรรทัด:

```
- 'line_chart', 'area': ONLY when category_column is a time dimension (Month/Year/Date).
  For categorical breakdowns (account, department, product) with no time axis,
  use 'bar_chart' (<=6 categories) or 'horizontal_bar' (>6 or long Thai labels).
```

### C4. ต่อ `auto_detect_chart_config()` fallback ให้ Claude/Gemini ด้วย

ตอนนี้ fallback (ซึ่งมีกฎ time ถูกต้องอยู่แล้ว :473–482) wired เฉพาะ Matcha — ให้ Claude/Gemini ใช้เมื่อ parse LLM ล้มเหลว

### C5. แก้ frontend heuristic substring (legacy path)

`DataChart.tsx:1320-1328` — ให้เชื่อ flag จาก backend แทน: เพิ่ม `is_time_axis: bool` ใน `ChartConfig` (`app/schemas/chat.py:57-70`, set ใน `enrich_chart_config`) แล้ว frontend ใช้ flag นี้แทนการเดาจากชื่อคอลัมน์

**เกณฑ์เลือกชนิดกราฟที่ถูกต้อง (ใช้ทั้งใน prompt และกฎ):**

| ลักษณะข้อมูล | ชนิดที่ถูก |
|---|---|
| หมวดหมู่ (บัญชี/หน่วยงาน) ≤ 6 รายการ | vertical bar |
| หมวดหมู่ > 6 หรือชื่อไทยยาว | **horizontal bar เรียงมาก→น้อย** (เคสค่าใช้จ่ายตามหมวดบัญชีควรได้ตัวนี้) |
| สัดส่วนของทั้งหมด ≤ 5–6 ชิ้น | pie/donut (เกินนั้นใช้ horizontal bar) |
| แนวโน้มตามเวลา | line / area |
| เวลา × มิติ ≤ 5 series | multi_line หรือ grouped_bar |
| เวลา × มิติ > 5 series | stacked_bar |
| องค์ประกอบการเปลี่ยนแปลง (budget→actual) | waterfall |

---

## Wave 2 — การแสดง label ภาษาไทย (frontend)

> **สถานะ: ✅ DONE (2026-07-12)** — L1–L8 implement ครบ
> - L8 เลือกทาง **(ข) ตัด mixed_bar_line/scatter ทิ้ง** (ไม่ใช่ implement) เพราะ
>   ChartConfig ปัจจุบันไม่มี shape รองรับ (ไม่มี dual-measure สำหรับ mixed_bar_line,
>   ไม่มี x/y คู่ตัวเลขสำหรับ scatter) — ตัดครบ: `app/models/chart.py` (enum +
>   VISUALIZATION_TO_ECHARTS), `chart_postprocessor.py` (prompt enum, TEMPORAL_TYPES,
>   downgrade dict), `frontend/types/chart.ts`, `DataChart.tsx` CHART_LABELS
>   **+ พบเพิ่ม:** `app/services/intent_classifier.py` CHART_TYPE_MAP มี
>   `'scatter'/'กระจาย'` เป็น explicit-request path ที่จะ silently fallback เป็น
>   vertical_bar เหมือนกัน (ไม่ได้อยู่ในแผนเดิม) — ตัดออกด้วยเพื่อปิดช่องเดียวกัน
>   (`_suggest_available_types` ตรวจแล้วไม่เคย emit สองชนิดนี้อยู่แล้ว ไม่ต้องแก้)
> - L4: ใส่ fontFamily stack ใน ECharts textStyle เท่านั้น — **ยังไม่ได้โหลด font asset จริง**
>   (Sarabun/Noto Sans Thai ไม่มีอยู่ใน bundle) เพราะไฟล์เป้าหมาย (global.css/index.html)
>   ไม่อยู่ใน "ไฟล์หลัก" ที่ระบุไว้ — fallback เป็น system-ui ตอนนี้ (ไม่ regression แต่ไม่ตรง
>   brand เป๊ะ) ต้องทำต่อถ้าต้องการ
> - พบ `treemap` ใน `CHART_LABELS` (DataChart.tsx) มีบั๊กแบบเดียวกับ L8 (ไม่มี case ใน
>   `buildEChartsOption`, ไม่ถูก suggest จาก backend) แต่ไม่อยู่ใน scope ของแผน/คำสั่งนี้ —
>   ปล่อยไว้ ไม่แตะ
> - Manual test: compile TS จริงด้วย `tsc` (ไม่ bundle ผ่าน Metro) แล้วเรียก
>   `buildEChartsOption` จริงกับ label "ค่าใช้จ่ายผลประโยชน์พนักงานหลังออกจากงาน" +
>   render ผ่าน echarts UMD จริงใน browser (ไม่ mock) — ยืนยัน: ellipsis บนแกน
>   horizontal_bar/vertical_bar, tooltip เต็มชื่อ (ทั้งจาก axis-trigger และเรียก
>   pie tooltip formatter ตรงๆ), truncateLabel grapheme-safe (ไม่มี glyph พิการ)
> - `tsc --noEmit`: 0 errors | `eslint` บนไฟล์ที่แก้: 9 findings ทั้งหมด pre-existing บน
>   main (verify ด้วย git stash) ไม่มีของใหม่ | `pytest -q`: 572 passed / 3 skipped (คงเดิม)

### L1. เลิกตัด label แบบทำลายข้อมูล — ย้ายไปตัดที่ระดับแสดงผล

ไฟล์: `frontend/utils/chartDataTransform.ts` ทุก builder — ส่ง**ชื่อเต็ม**เข้า `xAxis/yAxis.data` แล้วให้ ECharts ตัดเอง:

```ts
axisLabel: {
    fontSize: 11,
    width: 90,              // ปรับตามชนิดกราฟ (แกน y ของ horizontal bar ให้กว้างกว่า เช่น 140)
    overflow: 'truncate',
    ellipsis: '…',
    hideOverlap: true,
},
```

ผลพลอยได้สำคัญ: tooltip (`trigger: 'axis'`) จะแสดง**ชื่อเต็ม**อัตโนมัติเพราะ data ไม่ถูกตัดแล้ว — ได้ pattern "ellipsis บนแกน + ชื่อเต็มใน tooltip" ที่ตอนนี้มีแค่ฝั่ง mobile legacy

### L2. horizontal bar / heatmap: เลิก `left:'25%', containLabel:false`

`chartDataTransform.ts:348` และ :646–651 → เปลี่ยนเป็น

```ts
grid: { left: 8, right: '5%', bottom: '10%', containLabel: true },
yAxis: { ..., axisLabel: { fontSize: 11, width: 140, overflow: 'truncate' }, interval: 0 },
```

`containLabel: true` + `axisLabel.width` = grid ขยายพอดีป้าย ไม่ clip และไม่กินพื้นที่กราฟเกินจำเป็น

### L3. แก้ `truncateLabel` ให้ตัดตาม grapheme (จุดที่ยังต้องใช้ เช่น pie label)

ไฟล์: `frontend/utils/chartUtils.ts:120-122`

```ts
const thSegmenter = typeof Intl !== 'undefined' && 'Segmenter' in Intl
    ? new Intl.Segmenter('th', { granularity: 'grapheme' }) : null;

export const truncateLabel = (label: string, maxLen = 12): string => {
    if (!thSegmenter) return label.length > maxLen ? label.slice(0, maxLen) + '…' : label;
    const g = [...thSegmenter.segment(label)].map(s => s.segment);
    return g.length > maxLen ? g.slice(0, maxLen).join('') + '…' : label;
};
```

### L4. ตั้ง fontFamily ไทยที่ root ของ ECharts option

`buildEChartsOption()` เพิ่ม:

```ts
textStyle: { fontFamily: "'Sarabun','Noto Sans Thai',system-ui,sans-serif" },
```

และโหลดฟอนต์ฝั่ง web (global.css / index.html) — ถ้าต้องการตรง brand ที่สุดใช้ฟอนต์ NT แต่ต้องตรวจก่อนว่า NT_Regular.ttf ครอบคลุม glyph ไทยครบ; Sarabun เป็น fallback ที่ปลอดภัย

### L5. นโยบาย rotate สำหรับภาษาไทย

ตัวอักษรไทยเอียง 30° อ่านยากและสูงขึ้นเพราะสระบน/ล่าง — แนวทาง:
- categories > 6 และ label ยาว → backend ควรแนะ `horizontal_bar` ตั้งแต่ต้น (สอดคล้อง C1)
- ถ้าจำเป็นต้อง rotate จริง ใช้ 45° + `hideOverlap: true` แทน 30°

### L6. horizontal bar สูงตามจำนวนแถว

`DataChart.tsx:749-750` ตอนนี้ height ตายตัว 400 — สำหรับ horizontal bar ให้ `height = Math.max(300, rows * 32 + 96)` (legacy path ทำอยู่แล้วที่ :1138–1139 แต่ ECharts path ไม่มี)

### L7. Mobile ไม่ resize

`EChartsWrapper.tsx:130-140` ไม่มี listener + `Dimensions.get()` อ่านครั้งเดียว (`DataChart.tsx:191`) → เปลี่ยนไปใช้ `useWindowDimensions()` hook ทั้งสองไฟล์

### L8. mixed_bar_line / scatter

เลือกอย่างใดอย่างหนึ่ง: (ก) implement case ใน switch `buildEChartsOption` (`chartDataTransform.ts:143-177`) หรือ (ข) ตัดออกจาก `available_types`/toolbar — ห้ามปล่อยให้ปุ่มกดแล้วได้ vertical_bar เงียบ ๆ

---

## Wave 3 — Brand & dashboard polish

> **สถานะ: ✅ DONE (2026-07-12)** — B1–B4 implement ครบ
> - **Colorblind finding (real, quantified):** ΔE76 (CIELAB) ของคู่ Brick Red/Brown ภายใต้
>   protanopia = 10.7 (แค่เหนือเกณฑ์ "perceptible on close inspection", ไม่ถึง "clearly
>   distinct") และเป็น worst-case อยู่แล้วเพราะแผนเดิมวางสองสีนี้ติดกัน (index 4,5) —
>   รายงานให้ user ตัดสินก่อนตาม rule 3 → user เลือก **reorder เป็น
>   [Yellow, Teal, Brown, Dark Grey, Brick Red]** (dark grey กั้นทั้งคู่ brick-red/brown
>   ที่พบใหม่ และคู่ teal/brick-red เดิมของแผน — แยกห่างขึ้นเป็น 2 ตำแหน่งแทน 1)
> - B1: `buildLine` ใช้ `NT_LINE_PALETTE[0]` (teal) ไม่ใช้ palette[0] (เหลือง) กับเส้นเดี่ยว —
>   เพิ่ม `NT_LINE_PALETTE` (`chartColors.ts`, = `NT_CHART_PALETTE.slice(1)`) เป็น shared
>   constant **หลัง user สั่ง "เจอ bug ก็แก้เลย"** ได้แก้เพิ่มอีก 3 จุดที่เคยรายงานว่าพบแต่
>   ไม่แก้ (ไม่ใช่แค่ multi_line):
>   1. `buildMultiSeries` สำหรับ `multi_line` ใช้ `NT_LINE_PALETTE` แทน `NT_CHART_PALETTE`
>      เมื่อ `isLine=true` (bar-family series ยังใช้ palette เต็มรวมเหลืองได้ปกติ)
>   2. `buildEChartsOption` เพิ่ม guard คืน `null` ทันทีเมื่อ `visualization` เป็น
>      `'table'`/`'single_value'` — root cause จริงกว้างกว่าที่วินิจฉัยครั้งแรก: ไม่ใช่แค่
>      `single_value` render ซ้อนกับ Key Metric box แต่ `'table'` เองก็โดนบั๊กเดียวกัน
>      (resolveChartType() ไปเจอ `chartConfig.available_types` fallback ก่อนเช็ค
>      `visualization` เสมอ เพราะ `available_types` ถูกเซ็ตไว้ทุกกรณีไม่ว่า viz จะเป็น
>      อะไร — ทำให้กราฟ bar ผิดๆ โผล่เหนือ table ทั้งที่ AI สั่งไม่ให้มีกราฟ) แก้จุดเดียวจบ
>      ทั้งสองเคส ไม่ต้องแตะ backend หรือ ChatBubble.tsx
>   3. `treemap` ใน `CHART_LABELS` (DataChart.tsx) — ตรวจซ้ำแล้วว่า dead จริง (ไม่มี case
>      ใน switch, ไม่ถูก suggest, ไม่มีใน backend enum/intent_classifier) ตัดออกตาม
>      pattern เดียวกับ L8 (mixed_bar_line/scatter)
>   Verify รอบสอง: `tsc --noEmit` 0 errors, `eslint` 7 findings ทั้งหมด pre-existing,
>   เรียก `buildEChartsOption` จริงยืนยัน multi_line idx0=teal ไม่ใช่เหลือง, stacked_bar
>   idx0=เหลืองยังคงปกติ (แท่งใช้เหลืองได้), table/single_value คืน `null`, `pytest -q`
>   572 passed/3 skipped ไม่เปลี่ยน
>
> **รอบสาม (คำสั่งตรงเจาะจง 3 ข้อ):**
> - เก็บ `stacked_area` ที่หลุดจากรอบสอง: `buildArea()` delegate ไป `buildMultiSeries`
>   ด้วย chartType=`'stacked_bar'` (ไม่ใช่ `'multi_line'`) เพื่อเอา `isStacked` logic
>   ทำให้ข้าม `isLine` color guard ไปได้ แล้ว series ก็ถูกแปลงเป็น `type:'line'` อยู่ดี
>   ในลูปด้านล่าง — แก้โดย re-color ทุก series ด้วย `NT_LINE_PALETTE` ที่จุดเดียวกับที่
>   บังคับ `s.type='line'` ใน `buildArea()` เอง (idempotent กับ path ที่ถูกอยู่แล้ว,
>   แก้เฉพาะ path `stacked_area` ที่ผิด) ยืนยันด้วย `buildEChartsOption` จริง +
>   screenshot จริงทั้ง 3 ชนิด (multi_line/area/stacked_area) ไม่มีเส้นเหลืองเลย
> - Font asset (ค้างจาก Wave 2/รอบก่อน): ดาวน์โหลด `Sarabun-Regular.ttf` +
>   `Sarabun-SemiBold.ttf` จาก github.com/google/fonts (SIL OFL, ~90KB/ไฟล์) **หลัง user
>   อนุมัติแหล่งที่มาชัดเจนตาม safety rule เรื่อง file download** — ลองวางใน
>   `frontend/assets/fonts/` + `@font-face { url('./assets/fonts/...') }` ก่อน **ไม่ทำงาน
>   จริง** (network request 404 เพราะ Metro web dev server ไม่ serve `assets/` เป็น static
>   path ตรงๆ, asset ต้อง require() ผ่าน bundler ถึงจะ hash+serve ได้) แก้โดยย้ายไป
>   `frontend/public/fonts/` (Expo Router `output:"static"` serve `public/` ที่ root ตรงๆ)
>   แล้วอ้างด้วย absolute path `/fonts/Sarabun-*.ttf` ใน `global.css` — **verify กับ dev
>   server จริงที่รันอยู่** (ไม่ mock): `document.fonts.load()` ทั้ง weight 400/600 status
>   `"loaded"`, network request 200 (ไม่ใช่ 404 เหมือนรอบแรก), และ element จริงที่ใช้
>   `THAI_FONT_FAMILY` string เดียวกับใน chart render ด้วย glyph width ต่างจาก Arial
>   บังคับ (538px vs 547px) ยืนยันว่าใช้ font จริงไม่ใช่ fallback เงียบๆ — ทดสอบผ่านหน้า
>   login เท่านั้น (ไม่มี credential เข้าหน้า chat จริงได้) แต่ mechanism เดียวกันกับที่
>   chart/ChatBubble ใช้ทุกประการเพราะอ้าง `THAI_FONT_FAMILY` constant เดียวกัน — เพิ่ม
>   `.claude/launch.json` (`frontend-web`) ไว้ด้วยสำหรับ dev server รอบถัดไป
>   Verify รอบสาม: `tsc --noEmit` 0 errors | `eslint` 7 findings pre-existing (เท่าเดิม) |
>   `pytest -q` 572 passed/3 skipped ไม่เปลี่ยน
> - B2: toolbar active state ตอนนี้ #FFD100/#212121 (contrast 11:1, ผ่าน ≥4.5:1);
>   `ChatBubble.tsx` `colors.assistantText`→`#212121`, `colors.assistantBg`→`#FCFCFD` —
>   **พบว่า `assistantBg` เดิมถูกประกาศไว้แต่ไม่เคย apply จริง** (bg มาจาก Tailwind
>   className `bg-white` แทน) จึงย้ายไป apply ผ่าน inline `style` แทน className เพื่อให้
>   มีผลจริง ไม่ใช่แค่แก้ dead value — **ไม่แตะ** outer app canvas background
>   (`app/(app)/index.tsx` `bg-gray-50`) เพราะไฟล์นี้ไม่อยู่ใน scope ที่แผนระบุ (ระบุแค่
>   `DataChart.tsx` toolbar และโดยนัย `ChatBubble.tsx` ผ่าน B4)
> - B3: เพิ่ม `THAI_FONT_FAMILY` constant ใหม่ใน `constants/theme.ts` แชร์ระหว่าง
>   `chartDataTransform.ts` (แทนที่ inline string เดิมของ L4) กับ `ChatBubble.tsx`
>   markdown body+heading1-3 (ไม่แตะ code/code_block/fence ซึ่งตั้งใจใช้ monospace อยู่แล้ว)
>   — font asset โหลดจริงแล้ว (ดู "รอบสาม" ด้านล่าง — เดิม gap จาก L4/Wave 2) chart title
>   ทุกจุด (7 จุดใน chartDataTransform.ts) เพิ่ม `fontWeight: 600` แล้ว
> - B4: ตรวจลำดับ render ใน `ChatBubble.tsx` แล้ว — **ลำดับถูกอยู่แล้ว ไม่แก้โค้ด order**
>   (Markdown → DataChart → single_value box → DataTable → ...) กราฟ/single_value
>   อยู่ก่อนตารางแล้วตามที่แผนต้องการ — พบบั๊ก duplicate-render คนละประเด็นกับ order
>   (DataChart กับ single_value box render ซ้อนกันได้) **แก้แล้วที่ `buildEChartsOption`
>   ดูหัวข้อ B1 ด้านบน** ไม่ใช่การแก้ order ใน ChatBubble.tsx
> - Verify: `tsc --noEmit` 0 errors | `eslint` ไฟล์ที่แก้ 9 findings ทั้งหมด pre-existing
>   บน main (verify ด้วย git stash) รวมถึง 1 finding ที่ขยับเลขบรรทัดจาก import ใหม่ |
>   `pytest -q` 572 passed/3 skipped (ไม่เปลี่ยน — Wave 3 แตะ frontend ล้วน) | contrast
>   #212121 บน #FFD100 = 11.02:1 (ผ่าน) | colorblind sim ผ่านหลัง reorder (ดูด้านบน) |
>   compile+render จริงผ่าน `tsc`+`echarts` UMD จริงใน browser ทั้ง 8 ชนิดกราฟ x
>   light/dark mode — ยืนยัน palette order, buildLine teal, title bold, dark mode
>   ไม่ flip hex ตรงตาม CHART_THEME.dark ที่มีอยู่เดิม

### B1. เปลี่ยน chart palette เป็น NT จริง

ไฟล์: `frontend/constants/chartColors.ts` — แทน Tailwind palette ด้วย 5 สีทางการ (พอสำหรับ series ส่วนใหญ่ ตามแนว 5–9 สี):

```ts
export const NT_CHART_PALETTE = [
    '#FFD100', // NT Yellow (PANTONE 109C) — สีนำ ใช้กับ bar/area fill
    '#40C1AC', // Teal 7465C
    '#545859', // Dark Grey 425C
    '#E1523E', // Brick Red 7625C
    '#924C2E', // Brown 7587C
];
```

ข้อควรระวังที่ต้องทำตาม ไม่ใช่ทางเลือก:
- **`#FFD100` บนพื้นขาว contrast ~1.4:1** — ใช้ได้กับ "แท่ง/พื้นที่" (มวลสีใหญ่) แต่**ห้ามใช้กับเส้น line 2px หรือตัวหนังสือ** → single-series line ให้ใช้ `#545859` หรือ `#40C1AC` แทน (เพิ่ม logic ใน `buildLine` เลือกสีตามชนิด)
- teal กับ brick red อย่าวางติดกันใน palette (ลำดับข้างบนเว้นด้วย dark grey แล้ว) และรัน colorblind simulator (Deuteranopia/Protanopia) ก่อน merge
- `FINANCIAL_COLORS` เขียว/แดง → เปลี่ยนเป็น `positive: '#40C1AC', negative: '#E1523E', neutral: '#545859'` — ยังสื่อบวก/ลบตามสัญชาตญาณการเงิน แต่อยู่ใน brand และแยกง่ายกว่าใน colorblind

### B2. ใช้หลัก 60-30-10 กับ chat/dashboard UI

- 60% dominant: พื้น canvas/bubble โทน neutral (near-white `#FCFCFD` บน canvas `#EBEBEB` โหมดสว่าง) — ห้ามใช้เหลืองเป็นพื้นหลังส่วน data-heavy
- 30% secondary: สีตัวอักษร + chart palette (B1)
- 10% accent = **NT Yellow `#FFD100`** สงวนให้ interactive เท่านั้น: ปุ่ม toolbar เลือกชนิดกราฟ (active state), tab, filter, selected state — ตอนนี้ toolbar ใน `DataChart.tsx:676-708` ไม่มี accent brand เลย
- ข้อความ: ใช้ `#212121` บนพื้น near-white (เลี่ยง #000 บน #FFF) — dark mode ให้ตั้งค่าแยก ไม่ flip hex

### B3. Typography

ฟอนต์เดียวกับ L4 ทั้ง UI และ chart เพื่อความสม่ำเสมอ; ขนาด axis 11px เดิมโอเค แต่ title chart 14px ควรหนากว่า body (fontWeight 600) เพื่อสร้าง hierarchy

### B4. Hierarchy ของ answer card

ตามหลัก "focal point เดียว": ในคำตอบที่มีทั้งตาราง + กราฟ + คำอธิบาย ให้กราฟ (หรือ single_value ตัวเลขใหญ่) เป็น focal แรกตาม Z-pattern, ตาราง detail อยู่ล่าง (ทบทวนลำดับ render ใน ChatBubble)

---

## Wave 4 — จัดการกราฟที่มีจำนวนกลุ่มข้อมูลมากเกิน palette 5 สี

> **สถานะ: ✅ DONE (2026-07-12)** — งานที่ 1–2 implement ครบ (single-color bar +
> Top-N/"อื่นๆ" bucketing) พร้อม config 3-tier จริง

**บริบท:** ระหว่างพูดคุยเรื่อง Wave 3 palette ผู้ใช้ตั้งข้อสังเกตว่า palette 5 สีอาจไม่พอ
เมื่อกลุ่มข้อมูลมี 15-16 รายการ — วิเคราะห์ร่วมกันแล้วสรุปหลักออกแบบ: (ก) single-series
bar/pie ไม่จำเป็นต้องมีสีต่างกันต่อแท่ง เพราะตำแหน่ง+ป้ายชื่อระบุอยู่แล้ว (สีไม่ได้สื่อ
ข้อมูลอะไรเพิ่ม) และ (ข) multi-series/pie ที่มี legend ควรใช้ Top-N + "อื่นๆ" แทนการเพิ่มสี
เพราะสายตามนุษย์แยกสี categorical ได้จริงไม่เกิน ~8-10 สีอยู่แล้ว ไม่ว่า palette จะใหญ่แค่ไหน

### งานที่ 1 — Single-series bar ใช้สีเดียว

ไฟล์: `frontend/utils/chartDataTransform.ts`
- `buildVerticalBar`/`buildHorizontalBar`: `series.itemStyle.color = NT_CHART_PALETTE[0]`
  (เหลือง) ทั้งชุดแทนการ cycle ทีละแท่ง, `series.data` เป็น plain number array แทน
  object-per-bar (ไม่ต้องมี itemStyle ต่อจุดอีกต่อไป), data label สี `#212121`
- `buildWaterfall`/`FINANCIAL_COLORS` ไม่แตะตามที่สั่ง — ไม่เกี่ยวกับ single-series
  categorical bar

### งานที่ 2 — Top-N + "อื่นๆ" (multi-series + pie)

**Backend** (`app/providers/chart_postprocessor.py`):
- `DEFAULT_MAX_SERIES = 5` (module constant, hardcoded-fallback tier เท่านั้น —
  ไฟล์นี้ไม่มี DB access โดยตั้งใจ ดู deviation ด้านล่าง)
- `resolve_max_series_warning(data, cat_col, ser_col, viz, max_series)` — helper กลาง
  ใช้ร่วมกันระหว่าง `enrich_chart_config` (ค่า default tier) กับ `app/api/v1/chat.py`
  (ค่า 3-tier จริง) เพื่อไม่ให้ wording/threshold สองที่เพี้ยนกัน — pie/donut นับจาก
  distinct category, chart ตระกูล series นับจาก distinct series_column
- `enrich_chart_config` รับ `max_series: Optional[int]` เพิ่ม, เซ็ต
  `chart_config.max_series` เสมอ, **แทนที่ warning เดิม** `n_categories > 10` ของ pie
  ด้วย threshold-based warning ใหม่ (ตามที่สั่ง) — warning "ไม่รองรับ series column"
  ของ pie+series ยังคง priority สูงกว่าเดิม (ไม่ถูกทับ)

**Config 3-tier จริง** (`app/config.py` + `app/services/admin_config_service.py`):
- `Settings.CHART_MAX_SERIES: int = 5` (tier 2/3: .env → hardcoded)
- `AdminConfigService.get_chart_max_series()` — tier 1 (DB) ผ่าน `get_config()` ที่มีอยู่
  แล้ว, validate ค่าต้อง `>= 2` (ต้องมีอย่างน้อย Top-1 + 1 "อื่นๆ")

**Deviation จากคำสั่งเดิม (สำคัญ, อ่านก่อนแก้ต่อ):** คำสั่งเดิมเขียนว่า "อ่านใน
enrich_chart_config" ทำนองอ่าน DB ตรงจุดนั้น — แต่ตรวจโค้ดจริงแล้วพบว่า
`chart_postprocessor.py` **ทั้งไฟล์ไม่มี DB access เลยโดยตั้งใจ** (pure function, wrap
try/except ทุกจุด) และ**ไม่มี call site ไหนใน 5 จุดที่เรียก `enrich_chart_config` ถืออ็อบเจ็กต์
`admin_config` อยู่แล้ว** (3 providers explain_result ไม่มี db session เข้าถึงได้เลยด้วยซ้ำ)
— threading ผ่าน 3 provider files + AIService + QueryEngine ทั้งสายเพื่อให้ DB read เกิด
ขึ้น "ข้างใน" ฟังก์ชันจริงๆ จะเป็นการรื้อสถาปัตยกรรมที่ใหญ่เกินสัดส่วนงานนี้ จึงเลือกวิธี
**resolve ค่าจริงที่ layer ที่มี admin_config อยู่แล้ว (`app/api/v1/chat.py`) แล้ว override
`chart_config.max_series` + `warning` ทับค่า default-tier ของ provider อีกที** — จุดเดียว
(`_format_response`, ใช้ร่วมกันทั้ง `/chat` และ `/chat/stream` ผ่าน `_format_response`ที่ทั้ง
สอง endpoint เรียกร่วมกัน) + `_handle_chart_only` (chart-switch path) ครอบคลุมการใช้งานจริง
เกือบทั้งหมด ยกเว้น `template_answer.py` build_template_answer (fast-path เมื่อ
`template_answers_enabled` feature flag เปิด — default OFF, ไม่ทำ) ซึ่งจะยังใช้
DEFAULT_MAX_SERIES เท่านั้น — บันทึกเป็น known limitation ไม่ใช่ silent gap

**Frontend** (`frontend/utils/chartDataTransform.ts`):
- `OTHER_BUCKET_COLOR = '#9CA3AF'` (module constant, ไม่ใช้ `#545859` เพราะเป็นสี brand
  จริงที่ series อื่นใช้อยู่แล้ว)
- `buildMultiSeries`: จัดอันดับ series ด้วย `|sum ต่อ series|`, เก็บ Top-`(max_series-1)`,
  ยุบที่เหลือเป็น series ชื่อ `"อื่นๆ (รวม N กลุ่ม)"` ท้ายสุดเสมอ (ใช้ชื่อเดียวกันทั้ง legend
  และ tooltip เพื่อความง่าย/สอดคล้อง) ค่าต่อ category ของ "อื่นๆ" คำนวณจาก raw rows ใหม่
  ทุกครั้ง (ไม่ใช่ลบออกจาก total ที่เก็บไว้) — กติกา 4 (การเงิน ต้องไม่เพี้ยน)
- `buildPie`: pattern เดียวกัน จัดอันดับด้วย `|value|`
- **พบเพิ่ม (แก้แล้ว, ไม่ได้อยู่ใน scope คำสั่งเดิม):** `buildArea()` (จาก Wave 3 รอบ 3)
  re-color ทุก series ด้วย index-based `NT_LINE_PALETTE` cycling หลัง `buildMultiSeries`
  คืนมา — ถ้าไม่ดัก จะทับสีเทาของ "อื่นๆ" กลายเป็นสี brand แทนสำหรับ `stacked_area`/`area`
  ที่มี series เกิน max_series — แก้โดยข้ามการ re-color เมื่อ `s.name` ขึ้นต้นด้วย "อื่นๆ"

**Test:**
- Backend: `tests/unit/test_chart_max_series_config.py` (6 tests, 3-tier fallback +
  validation), `tests/unit/test_chart_postprocessor.py` เพิ่ม `TestResolveMaxSeriesWarning`
  (8 tests) + `TestEnrichChartConfigMaxSeries` (5 tests, รวม pie+series priority)
- Reconciliation script (Node, compile TS จริงด้วย `tsc`, เรียก `buildEChartsOption` จริง):
  dataset 16 series x 4 categories (มีค่าติดลบทดสอบ `|sum|` ranking) — ยืนยัน sum ของ
  ทุก series (รวม "อื่นๆ") ต่อ category ตรงกับ raw sum เป๊ะทุกกรณี (`grouped_bar`,
  `stacked_bar`, `multi_line`, `pie`) รวมถึง grand total, และ under-threshold (3 series,
  max 5) ไม่สร้าง "อื่นๆ" เลย — ทดสอบ `area`/`stacked_area` แยกยืนยัน `buildArea` fix ด้วย
- Render จริงผ่าน `tsc` + `echarts` UMD ใน browser: bar 15 แท่งสีเหลืองเดียว, stacked/
  grouped/multi_line 16 series → Top-4 brand colors + เทา "อื่นๆ" ไม่มีสีซ้ำใน legend,
  pie 12 → Top-4 + "อื่นๆ" 47.95%
- `tsc --noEmit`: 0 errors | `eslint` ไฟล์ที่แก้: 1 finding (pre-existing,
  `formatTooltipValue` unused) | `ruff` ไฟล์ backend ที่แก้: 20 findings ทั้งหมด
  pre-existing บน main (นับเท่ากันก่อน/หลัง verify ด้วย git stash) | `pytest -q`:
  591 passed / 3 skipped (+19 จาก 572 เดิม)

### Wave 4 follow-up — Chart container sizing (แก้ "แอปจริงต่างจากเทสต์ลิบลับ")

**อาการ:** ผู้ใช้รายงานว่ากราฟในแอปจริงหน้าตาต่างจากไฟล์ทดสอบ (isolated echarts) มาก

**Root cause (ยืนยันด้วยโค้ดจริง):** `DataChart.tsx` ส่ง `width={Math.min(screenWidth - 48, 800)}`
ให้ `EChartsWrapper` — เป็นค่า pixel ตายตัวคำนวณจาก **window width** ไม่ใช่ความกว้าง
container จริงของ bubble. RN-Web render `<View>` เป็น `div` ที่ `overflow: hidden` โดย
default ดังนั้นเมื่อ bubble แคบกว่าค่านั้น (เปิด sidebar / จอเล็ก / จอ laptop) canvas 800px
**ถูก clip ด้านขวา** (เดือน/legend หายไป) ส่วนไฟล์ทดสอบให้ div กว้างเท่ากราฟพอดีไม่มีอะไร
บีบ จึงดูสวย — chart option เหมือนกันเป๊ะ (`buildEChartsOption` ตัวเดียวกัน) ต่างแค่ container

**Fix:** `EChartsWrapper` web path — inner div เป็น `width: '100%'` เสมอ (ไม่สน numeric
width prop ซึ่งยังส่งต่อให้ native SVG path ที่ auto-size ไม่ได้) + เพิ่ม `ResizeObserver`
เรียก `chart.resize()` ตามความกว้าง container จริง → กราฟ responsive ตาม bubble ไม่ clip
ทุกความกว้าง (รวมตอน toggle sidebar). `DataChart.tsx` ไม่ต้องแก้ (numeric width ยังใช้กับ
mobile ได้เหมือนเดิม)

**Verify:** before/after demo ใน browser จริง (bubble 560px, overflow:hidden แบบ RN-Web) —
BEFORE: กราฟ 800px ถูก clip เดือนที่ 6 + legend หาย | AFTER: responsive เต็ม bubble ครบ
ทั้ง 6 เดือน legend paginate เอง ไม่มีอะไรหาย. `tsc --noEmit` 0 errors, `eslint`
EChartsWrapper.tsx 2 findings pre-existing (native require เท่านั้น)

---

## Wave 5 — Export กราฟ + สีแท่ง + ยกเครื่อง UI สไตล์ Claude

> **สถานะ: ✅ DONE (2026-07-13)** — จากคำขอผู้ใช้: (1) ปุ่ม export กราฟเป็นรูป,
> (2) ทำไมแท่งสีเดียว + แก้, (3) ทำ UI ทั้งหมด (text/table/bubble) สวยแบบ Claude
> — ผู้ใช้เลือก "แก้ของจริงเลย" (ไม่ทำ preview) สำหรับข้อ 3

### W5-A. ปุ่ม Export กราฟเป็น PNG (web)

- `EChartsWrapper.tsx`: เพิ่ม prop `onChartReady?(chart)` — คืน instance ให้ parent
  ผ่าน ref (เก็บใน `onChartReadyRef` ไม่ให้ effect re-run ทุก render)
- `DataChart.tsx`: ปุ่ม download ในหัวการ์ด (web เท่านั้น) เรียก
  `chart.getDataURL({type:'png', pixelRatio:2, backgroundColor})` → trigger download
  ชื่อไฟล์จาก chart title — **ไม่เพิ่ม dependency** (echarts มี getDataURL ในตัว)
- **พบ+จัดการ export gotcha:** getDataURL ตอน animation ยังไม่จบจะได้ภาพแท่งหาย —
  ในแอปจริง user กดหลังกราฟ settle แล้วจึงครบ (verify ด้วย `finished` event ใน demo:
  ภาพเต็มครบแท่ง พื้นขาว retina 2×) mobile export = follow-up

### W5-B. สีแท่ง single-series (ตอบ "ทำไมสีเดียว")

เดิม Wave 4 ทำสีเดียวตามหลัก dashboard — ผู้ใช้อยากได้สีสันกว่านี้ สรุปหลัก:
- `chartDataTransform.ts` `singleSeriesBarColors(values)`:
  - **≤ palette (5) แท่ง** → สี NT ต่างกันต่อแท่ง (สดใส ไม่มีสีซ้ำ)
  - **> 5 แท่ง** → ไล่เฉดเหลืองเดียว (`#FFEA80`→`#B8860B`) keyed ด้วย `|value|`
    (มาก=เข้ม) — ไม่มีสีชนกันแบบ cycle + สื่อขนาดค่า = วิธีที่ถูกต้องสำหรับ
    single-series cardinality สูง (helper `lerpHex`, ไม่เพิ่ม dep)
- verify ด้วย `buildEChartsOption` จริง: 4 แท่ง = [#FFD100,#40C1AC,#924C2E,#545859],
  15 แท่ง = ramp เข้ม→อ่อนเรียงตามค่า + render จริงใน browser

### W5-C. UI สไตล์ Claude — de-blue + Sarabun (แก้ของจริง)

- **`DataTable.tsx`** (ต้นเหตุ "โทนฟ้าเยอะ" ที่สุด): ตัด blue token ทั้งหมด
  (`bg-blue-*`, `border-blue-500`, sort icon ฟ้า, frozen col ฟ้า) → neutral +
  NT accent; hierarchy level 4 สีพาสเทล (ฟ้า/เขียว/เหลือง/ม่วง) → neutral ramp
  (ลึกด้วย indent+น้ำหนักตัวอักษร ไม่ใช่สีฉูดฉาด แบบ Claude); grouped header
  border ฟ้า → NT yellow left accent; emoji 🔢 → NT yellow tick; export button
  เขียว → neutral; ใส่ `THAI_FONT_FAMILY` ที่ container (web inherit) + Text หลัก
- **`ChatBubble.tsx`**: bold ฟ้า→neutral หนัก (`#111827`/`#F9FAFB`); blockquote ฟ้า
  → NT-yellow tint + border `#FFD100`; single_value box ฟ้า → neutral card + NT
  top accent; link/accent ฟ้า → teal อ่านง่าย (`#0F766E`/`#5EEAD4`); pivot toggle
  active ฟ้า → NT yellow/`#212121` (ตรงกับ chart toolbar); info-warning ฟ้า →
  neutral; ใส่ Sarabun ใน Text หลัก **user bubble ยังคงฟ้า** (แบบแผน chat ทั่วไป
  ไม่ใช่ "การ render ที่ผิด brand")

**Verify:** `tsc --noEmit` 0 errors | `eslint` ไฟล์ที่แก้ = findings เดิมทั้งหมด
(Share/isHierarchicalHint/isFlatHint/conditional-useMemo pre-existing) ไม่มีของใหม่ |
grep ยืนยันไม่เหลือ blue token (ยกเว้น user bubble ที่ตั้งใจเก็บ) | render จริง:
สีแท่ง 2 แบบถูกต้อง + mock answer card (Sarabun จริง) โชว์ลุครวม text+table+chart+
single_value สไตล์ Claude — ตาราง de-blue, tick เหลือง NT, zebra, ตัวเลข tabular
ชิดขวา, blockquote เหลืองนุ่ม | ไม่แตะ backend (frontend ล้วน) — pytest คงเดิม

> **หมายเหตุการเห็นผลจริง:** ทั้งหมด hot-reload ได้ผ่าน Metro — **hard-reload
> (Cmd+Shift+R)** ในแอปที่รันอยู่เพื่อเห็น table/text/bubble ที่แก้จริง (mock ข้างบน
> เป็น approximation ของลุค ใช้สี/ฟอนต์ชุดเดียวกับ component จริง)

### Wave 5 follow-up — Pie/Donut แสดงกลุ่มไม่ครบ (5 กลุ่ม เห็นแค่ 3)

**อาการ:** ผู้ใช้รายงาน pie/donut มี 5 กลุ่มธุรกิจ แต่แสดงแค่ 3

**Root cause (reproduce ด้วยโค้ดจริง):** `buildPie` **ไม่ aggregate ตาม category ก่อน
slice** — สมมติว่า data เป็น pre-aggregated (1 แถว/กลุ่ม) แต่ SQL ของ pie มักคืนหลายแถว
ต่อกลุ่ม (เช่น group by business_unit × month → 5 กลุ่ม × 3 เดือน = 15 แถว) แต่ละ**แถว**
กลายเป็น 1 slice แล้ว Top-N bucketing (Wave 4) ก็ยุบ 11 แถวเป็น "อื่นๆ" ทำให้เห็นแค่ 2-3
กลุ่มจริง (reproduce: 15 แถว → `[ดิจิทัล, ดิจิทัล, ดิจิทัล, องค์กร, อื่นๆ]` = 2 กลุ่ม distinct)
— Wave 4 bucketing ทำให้แย่ลง (เดิมไม่ bucket จะเห็นครบแต่รก)

**Fix:** เพิ่ม helper `aggregateByCategory(data, catCol, measureCol)` (sum measure ต่อ
category, no-op ถ้า pre-agg อยู่แล้ว) — เรียกใน `buildPie` ก่อน slice/bucket + เรียกใน
`buildVerticalBar`/`buildHorizontalBar` ด้วย (บั๊ก latent เดียวกัน: multi-row → แท่งซ้ำ)
**ไม่แตะ** buildLine/buildWaterfall (แกน x เป็นเวลา/มี running total — ไม่ควร sum ตาม category)

**Verify:** reproduce จริง — pre-agg 5 แถว → 5 slices, multi-row 15 แถว → **ครบ 5 กลุ่ม
distinct** แต่ละ slice = sum จริงของกลุ่มนั้น + total ตรง raw (48M=48M), >5 กลุ่มจริง
(8 กลุ่ม) → ยัง bucket ถูก top-4+อื่นๆ, bar 15 แถว → 5 แท่ง (ไม่ใช่ 15) | render จริง:
pie 5 กลุ่มครบ 32.5/26.25/20/13.75/7.5% = 100% | `tsc` 0 errors, `eslint` 1 finding
pre-existing (`formatTooltipValue`)

### Wave 5 follow-up 2 — ชื่อแกนวัดค่าซ้ำ+ทับตัวเลข

**อาการ:** ผู้ใช้ส่งภาพกราฟแท่งแนวตั้ง (12 สายงาน) — ชื่อแกน Y "ค่าใช้จ่ายรวม"
(ตัวหนังสือหมุนตั้ง) ทับกับตัวเลข tick แกน และซ้ำกับ chart title
"ค่าใช้จ่ายรวมรายสายงาน ปี 2568" อยู่แล้ว

**Fix:** value-axis `name` = `''` เมื่อมี `config.title` (title + tick ที่มีหน่วย
"พลบ." สื่ออยู่แล้ว → axis name ซ้ำซ้อน) ยังคง name ไว้เมื่อไม่มี title — applied ทั้ง 5
value axis (vertical/horizontal/multi/line/waterfall) declutter + หายทับ

**ไม่ใช่บั๊ก (ตั้งใจ):** หน่วยผสม พลบ./ลบ. ใน data label = แต่ละค่าโชว์หน่วยธรรมชาติ
ที่อ่านง่าย (18.69 พลบ. / 267.54 ลบ.) — ความสูงแท่งทำหน้าที่เปรียบเทียบอยู่แล้ว ไม่ต้อง
บังคับหน่วยเดียว (จะทำให้ค่าเล็กเป็น 0.08 พลบ. เสียความละเอียด)

**แนะนำ:** 12 สายงานชื่อไทยยาว → **horizontal_bar อ่านง่ายกว่ามาก** (ป้ายเต็ม ไม่มี
label ชนกันบนหัวแท่ง) มีให้เลือกใน toolbar อยู่แล้ว | `tsc` 0 errors

### Wave 5 follow-up 3 — ป้าย label ชน/ตัด ที่จอแคบ + stale-bundle diagnosis

**อาการ:** ผู้ใช้ส่งภาพ 2 กราฟ — vertical: data label บนหัวแท่งชนกัน; horizontal:
ป้ายชื่อสายงานถูกตัดเหลือ "ส" + value label ทับชื่อ

**Debug (สร้าง real in-browser bundle ของ `buildEChartsOption` — ไม่ JSON.stringify
เพราะมันทำ formatter หาย):**
- ที่ **720px กว้าง**: ทั้ง 2 กราฟ render ถูกต้องสมบูรณ์ (ป้ายเต็ม ไม่ตัด ไม่ชน)
- ที่ **340px แคบ**: reproduce ได้ 2 จุด → vertical data labels ชนกัน + horizontal
  value label ตัวบนสุดถูกตัดขวา + x-tick ค่าซ้อนกัน
- **สำคัญ:** ป้าย "ส" (ตัดเหลือ 1 ตัวอักษร) **reproduce ไม่ได้** ทั้ง 720/340px —
  signature นั้นเกิดเฉพาะ `containLabel:false`+`left:8` = โค้ดเก่าก่อน Wave 2 L2
  โค้ดปัจจุบัน `containLabel:true` render ป้ายเต็มทุกความกว้าง (พิสูจน์แล้ว) →
  **ที่ผู้ใช้เห็น "ส" = stale Metro bundle** (Fast Refresh ค้าง module เก่าของไฟล์ที่
  แก้บ่อย) ต้อง **restart Metro เต็ม** (`r` ใน terminal หรือ Ctrl+C แล้ว `npm run web`
  ใหม่) + hard-reload — ไม่ใช่แค่ Cmd+Shift+R

**Fix (harden จอแคบ):**
- `buildVerticalBar`: data label แสดงเฉพาะเมื่อ ≤8 แท่ง (เกินนั้นชนกัน — ใช้ horizontal
  หรือ tooltip ดูค่าแทน)
- `buildHorizontalBar`: `grid.right` `'5%'`→`80` (px คงที่ กัน value label แท่งยาวสุด
  ถูกตัด) + value-axis `axisLabel.hideOverlap:true` (กัน x-tick ซ้อนที่จอแคบ)

**Verify:** rebuild bundle → 340px & 720px ทั้งคู่สะอาด (vertical ไม่มี label ชน,
horizontal ป้ายเต็ม+value ครบ+tick ไม่ซ้อน) | `tsc` 0 errors, `eslint` 1 pre-existing

---

## ลำดับการทำและการทดสอบ

1. **Wave 1 (C1–C5)** — กระทบความถูกต้อง ทำก่อน; เพิ่ม unit test: dataset หมวดบัญชี (ไม่มีเวลา) + LLM ตอบ line_chart → ต้องได้ bar/horizontal_bar; dataset รายเดือน → line ต้องผ่าน
2. **Wave 2 (L1–L8)** — ทดสอบด้วยชื่อบัญชีไทยยาวจริง เช่น "ค่าใช้จ่ายผลประโยชน์พนักงานหลังออกจากงาน" บนทั้ง web (Canvas) และ mobile (SVG); ตรวจ tooltip แสดงชื่อเต็ม
3. **Wave 3 (B1–B4)** — screenshot เทียบก่อน/หลัง + colorblind simulation + contrast checker
4. Regression: toolbar สลับชนิดกราฟทุกปุ่มต้องได้กราฟตรงชนิด (จับ L8)

ข้อจำกัดที่คงเดิม: ไม่เพิ่ม dependency ใหม่ (Intl.Segmenter เป็น built-in; ฟอนต์เป็น asset ไม่ใช่ library) — สอดคล้องกติกา deferred-decision ของ PLAN_FIX_MASTER
