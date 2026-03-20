# Plan 2: Feedback + Query Log Enhancement

**Priority:** 2  
**ประมาณเวลา:** 1-2 วัน  
**Prerequisite:** บางส่วน standalone, เต็มรูปแบบต้อง Plan 1  
**อ้างอิงโดย:** Plan 3 (Self-Learning ใช้ข้อมูลจากที่นี่)

---

## 1. ปัญหาปัจจุบัน

- **Feedback Review** แสดงแค่ question + ai_response แต่ไม่แสดง `generated_sql` → admin ไม่เห็นว่า SQL ผิดตรงไหน
- **Query Logs** ไม่มี filter "เฉพาะที่ fail" หรือ "เฉพาะ thumbs down"
- ไม่มี aggregation: "keyword ไหนที่ทำให้ SQL ผิดบ่อย", "context ไหนที่ error เยอะสุด"

## 2. สิ่งที่ต้องทำ

### 2.1 Backend: Feedback Review แสดง SQL (standalone)

**ไฟล์:** `app/api/v1/admin.py` → endpoint `GET /admin/query-logs`

ตอนนี้ query-logs ดึง ChatHistory แล้ว join user email แต่ไม่ดึง feedback ที่สัมพันธ์กัน

**เพิ่ม:**
- Join `UserFeedback` กับ `ChatHistory` ใน query-logs endpoint
- เพิ่ม filter parameters: `feedback_only=true`, `thumbs_down_only=true`, `has_error=true`
- เพิ่ม field `generated_sql` ในผลลัพธ์ (ตอนนี้มีแต่ truncate 500 chars)

**ไฟล์:** สร้าง `GET /admin/feedback-details/{feedback_id}` endpoint ใหม่
- คืน: feedback + full ChatHistory (question, generated_sql, sql_result_summary, ai_response, context_name, tokens_used)
- ตอนนี้มี `GET /admin/query-logs` แต่ไม่ได้ join feedback

### 2.2 Backend: Query Log Analytics

**ไฟล์:** `app/api/v1/admin.py` → endpoint ใหม่ `GET /admin/query-analytics`

```python
# คืน aggregated stats:
{
    "period": "7d",
    "total_queries": 150,
    "error_rate": 0.12,
    "thumbs_down_rate": 0.08,
    "top_failed_keywords": [
        {"keyword": "datacom", "fail_count": 5, "context": "pl_costtype"},
        {"keyword": "สื่อสารข้อมูล", "fail_count": 3, "context": "pl_costtype"},
    ],
    "error_by_context": [
        {"context": "pl_costtype", "total": 80, "errors": 12},
        {"context": "revenue", "total": 70, "errors": 3},
    ],
    "common_error_patterns": [
        {"pattern": "wrong column selection", "count": 8, "example_question": "..."},
    ]
}
```

### 2.3 Frontend: Feedback Page Enhancement

**ไฟล์:** `frontend-admin/src/pages/Feedback.tsx`

**เพิ่ม:**
- คอลัมน์ `Generated SQL` ในตาราง (collapsible — แสดง SQL เมื่อคลิก)
- คอลัมน์ `Context` 
- Filter: "Thumbs Down Only", "Has SQL Error"
- ปุ่ม "Analyze" ต่อแถว → เปิด modal แสดง full details + ส่งไป Admin Agent (Plan 1) เพื่อวิเคราะห์

### 2.4 Frontend: Query Log Page Enhancement

**ไฟล์:** `frontend-admin/src/pages/QueryLogs.tsx`

**เพิ่ม:**
- Filter: context, date range, feedback rating, error status
- Summary cards ด้านบน: total queries, error rate, thumbs down rate
- ปุ่ม "Analyze Pattern" → ส่งกลุ่ม failed queries ไป Admin Agent (Plan 1)

### 2.5 Admin Agent Tool (ต้องรอ Plan 1)

**ไฟล์:** `app/tools/admin/analysis_tools.py`

Tool `review_feedback` ดึง feedback + ChatHistory ส่งให้ LLM วิเคราะห์:
- SQL ผิดตรงไหน?
- ต้องเพิ่ม mapping/rule/example อะไร?
- แนะนำ fix อัตโนมัติ

---

## Claude Code Instructions

```
## Phase 1 (standalone — ทำได้เลยไม่ต้องรอ Plan 1)

1. อ่าน app/api/v1/admin.py → get_query_logs() endpoint
2. อ่าน app/models/feedback_models.py → UserFeedback fields
3. อ่าน app/models/chat.py → ChatHistory fields (confirm generated_sql มีอยู่)
4. แก้ get_query_logs():
   - เพิ่ม left join UserFeedback
   - เพิ่ม filter params: feedback_rating, has_error
   - เพิ่ม generated_sql ในผลลัพธ์ (ไม่ truncate)
5. สร้าง endpoint GET /admin/feedback-details/{feedback_id}
6. สร้าง endpoint GET /admin/query-analytics

## Phase 2 (frontend)
7. แก้ Feedback.tsx: เพิ่ม SQL column + filters
8. แก้ QueryLogs.tsx: เพิ่ม filters + summary cards

## Phase 3 (ต้องรอ Plan 1)
9. สร้าง analysis_tools.py (review_feedback, analyze_query_logs tools)

## ไฟล์ที่ต้องอ่าน
- app/api/v1/admin.py (get_query_logs function)
- app/models/chat.py (ChatHistory schema)
- app/models/feedback_models.py (UserFeedback schema)
- frontend-admin/src/pages/Feedback.tsx
- frontend-admin/src/pages/QueryLogs.tsx
- frontend-admin/src/services/feedback.ts
```
