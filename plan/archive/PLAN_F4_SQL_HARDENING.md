# PLAN F4 — SQL Execution Hardening (Read-only, Row Cap, Validation Consolidation)

**Prerequisite:** PLAN_F2 เสร็จ
**ประมาณเวลา:** 1 วัน
**หลักการ:** ตอนนี้การกัน write/injection พึ่ง regex blacklist ชั้นเดียว — เพิ่ม enforcement ที่ระดับ connection (defense in depth) และแก้ row-limit ที่พังบน MSSQL

## READ FIRST

- `mcp_servers/nt_query_mcp.py` ทั้งไฟล์
- `mcp_servers/nt_metadata_mcp.py` ← **ยังไม่เคย review** อ่านทั้งไฟล์ ดูว่าเปิด connection แบบไหน
- `app/services/database_adapter.py`, `app/services/business_db.py` ← ยังไม่เคย review — หาว่ามีจุดไหนเปิด business DB โดยตรงบ้าง
- `app/services/validation_service.py`
- `app/services/api_key_service.py`, `app/services/cache_service.py` ← cache_service ยังไม่เคย review
- grep ทั้ง repo: `BUSINESS_DB_PATH`, `sqlite3.connect`, `nt_fi_report`

---

## F4.1 — เปิด business DB แบบ read-only ที่ระดับ connection

**SQLite (`nt_query_mcp.QueryDatabaseAdapter._get_connection`):**

```python
if self.engine == "sqlite":
    import sqlite3
    path = self.config.connection_string.replace("sqlite:///", "").replace("sqlite://", "")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn
```

ข้อควรระวัง:
- ถ้าไฟล์ไม่มีอยู่ mode=ro จะ fail ทันที (ต้องการแบบนี้ — fail loud ดีกว่า auto-create ไฟล์เปล่า) — เพิ่ม error message ที่อ่านรู้เรื่องว่า path ไหนหาย
- DB อยู่ใน WAL mode: read-only connection ยังอ่านได้ตราบที่ไฟล์ -wal/-shm อ่านได้ — ทดสอบกับไฟล์จริง
- **ห้ามใส่ `immutable=1`** เพราะข้อมูลถูก ETL อัปเดตระหว่างรัน
- path ที่มี space/อักขระพิเศษ: URI ต้อง escape — ใช้ `pathlib.Path(path).resolve().as_uri()` แล้วต่อ `?mode=ro` แทนการต่อ string เอง แล้วทดสอบ

**apply pattern เดียวกันกับทุกจุดที่อ่าน business DB:**
- `nt_metadata_mcp.py` (อ่านก่อน — ถ้าโครงเหมือนกัน แก้แบบเดียวกัน)
- ฝั่ง app (`database_adapter.py`, `business_db.py`, `db/session.py::business_engine`): จุดที่**อ่านอย่างเดียว**ให้เปิด ro; ถ้าพบจุดที่เขียนลง business DB (ตามหลักโปรเจกต์ไม่ควรมี) → **หยุด จดลง FIX_NOTES แล้วถามเจ้าของโปรเจกต์** ห้ามตัดสินใจเอง
- SQLAlchemy engine แบบ ro: `create_engine("sqlite:///file:...?mode=ro&uri=true", connect_args={"uri": True})` หรือใช้ `creator=` callback — เลือกวิธีที่ทดสอบแล้วเวิร์กกับ SQLAlchemy เวอร์ชันที่ติดตั้ง

**MSSQL (production):** enforcement ทำที่ credential — เพิ่มลง `docs/` (deployment note): login ที่ใช้กับ business DB ต้องมีสิทธิ์ `SELECT` เท่านั้น (db_datareader) และเพิ่ม startup log ใน MCP server: ถ้า engine=mssql ให้ log คำเตือนหนึ่งบรรทัดว่า "ensure read-only login" (ตรวจสิทธิ์จริงทาง SQL ยุ่งเกินจำเป็น — ไม่ทำ)

---

## F4.2 — แก้ row cap: เลิก append `LIMIT` แบบ string, ใช้ fetchmany เป็น guard หลัก

**ปัญหาเดิม (`nt_query_mcp.execute_query`):**
1. append `LIMIT n+1` กับทุก engine — MSSQL ไม่มี LIMIT → syntax error ทันทีที่ย้าย production
2. เช็ค `'LIMIT' not in sql_upper` เป็น substring — subquery ชั้นในมี LIMIT → outer ไม่ถูก cap → `fetchall()` ดึงทั้งหมดเข้า memory ได้

**การแก้:**

1. `QueryDatabaseAdapter.execute_query(sql, params=None, max_rows=None)` — เมื่อ `max_rows` ถูกส่ง ใช้ `cursor.fetchmany(max_rows)` แทน `fetchall()` (ทุก engine)
2. `execute_query` tool: ลบ logic append LIMIT ทั้งก้อน แล้ว:

```python
rows = db.execute_query(sql, max_rows=limit + 1)
truncated = len(rows) > limit
if truncated:
    rows = rows[:limit]
```

3. **PostgreSQL เท่านั้น** เพิ่มชั้นป้องกัน memory ฝั่ง client: psycopg2 default cursor โหลดผลลัพธ์ทั้งหมดเข้า client ตั้งแต่ `execute()` (fetchmany ไม่ช่วย) → wrap ด้วย subquery ก่อนรัน:

```python
if self.engine == "postgresql" and max_rows:
    sql = f"SELECT * FROM ({sql.rstrip().rstrip(';')}) AS _lim LIMIT {int(max_rows)}"
```

PG รองรับ CTE (`WITH ...`) ใน subquery ได้ — ปลอดภัย
**ห้ามใช้วิธี wrap นี้กับ MSSQL** (T-SQL ไม่อนุญาต CTE ใน FROM-subquery) — MSSQL พึ่ง fetchmany (pyodbc stream ทีละ batch เพียงพอ ฝั่ง server ยังคำนวณเต็มแต่ client ไม่บวม)
4. อัปเดต docstring ของ tool ให้ตรงพฤติกรรมใหม่ (`truncated` ยังทำงานเหมือนเดิมจากมุม caller — F1.2 พึ่ง flag นี้)

**Test:** `tests/unit/test_query_mcp_limit.py` (sqlite in-memory ผ่าน temp file)
- ตาราง 50 แถว, limit=10 → 10 แถว + truncated=true
- SQL ที่มี `LIMIT 5` ใน subquery ชั้นใน แต่ outer ไม่มี → ยังถูก cap ที่ limit + truncated ถูกต้อง
- SQL มี trailing `;` → ไม่พัง

---

## F4.3 — รวม `validate_sql` เหลือแหล่งเดียว

**ปัญหา:** logic เดียวกัน copy อยู่สองที่ (`validation_service.py` และ `nt_query_mcp.py`) — จะ drift แน่นอน (docstring ของ service เขียนเองว่า "Replaces hardcoded logic from MCP servers" แต่ยังไม่ replace จริง)

**การแก้:**
1. ยืนยันก่อนว่า `app.services.validation_service` import ได้จาก MCP server process โดยไม่ลาก `app.config` มา (จากการ review: top-level import มีแค่ json/logging/re/typing — ปลอดภัย แต่**ต้องยืนยันซ้ำกับไฟล์จริง ณ ตอนแก้**)
2. `nt_query_mcp.validate_sql` tool → delegate:

```python
from app.services.validation_service import ValidationService
_validator = ValidationService(db=None)

@mcp.tool()
def validate_sql(sql: str) -> Dict[str, Any]:
    """(คง docstring เดิม)"""
    return _validator.validate_sql(sql)
```

3. ลบ `DANGEROUS_PATTERNS` / `INJECTION_PATTERNS` / logic ที่ซ้ำออกจาก `nt_query_mcp.py`
4. เช็คว่า MCP server มี test ยิงผ่าน stdio หรือไม่ (grep tests) — ถ้ามี ต้องยังผ่าน; ถ้า import `app.*` ทำให้ startup MCP server ช้าลงมาก (import chain) ให้วัดคร่าว ๆ — ถ้าเกิน 2 วินาที จดไว้และพิจารณา copy คงที่พร้อม comment "single source = validation_service, sync manually" เป็น fallback (ตัดสินใจแล้วบันทึกเหตุผล)

---

## F4.4 — Enforce API key per-minute rate limit

**ปัญหา:** model ประกาศ `rate_limit_per_minute` แต่ service enforce เฉพาะ daily

**การแก้ (Redis-first เพราะมี Redis ใน stack อยู่แล้ว):**
1. อ่าน `cache_service.py` — reuse Redis client accessor ที่มีอยู่
2. ใน `APIKeyService._check_rate_limits` เพิ่ม per-minute check:

```python
# fixed-window ต่อนาที
key = f"ratelimit:apikey:{api_key.id}:{int(time.time() // 60)}"
count = redis.incr(key)
if count == 1:
    redis.expire(key, 120)
if count > api_key.rate_limit_per_minute:
    return False
```

3. ถ้า Redis ไม่ config (`REDIS_URL` ว่าง) หรือ error → **fail-open** (allow) พร้อม `logger.warning` ครั้งแรกครั้งเดียวต่อ process — ระบบ internal ให้ availability มาก่อน แต่ต้อง log ให้รู้ว่า limit ไม่ทำงาน
4. หมายเหตุใน docstring: fixed-window มี burst ที่รอยต่อนาทีได้สูงสุด 2x — ยอมรับได้สำหรับ use case นี้

**Test:** mock redis (fakeredis หรือ MagicMock) — request ที่ 31 ภายในนาทีเดียว limit=30 → validate_key คืน None; Redis down → allow + warning

---

## Acceptance Criteria

- [ ] pytest ทั้ง suite + tests ใหม่ผ่าน
- [ ] Manual: ยิง SQL `INSERT` ผ่าน execute_query โดย set `validate_first=False` ตรง ๆ (จำลอง bypass validation) → ต้อง fail ที่ระดับ connection ("attempt to write a readonly database")
- [ ] Manual: query ใหญ่ไม่มี LIMIT → ได้ 1000 แถว + truncated=true + (จาก F1.2) มีข้อความเตือนใน UI
- [ ] grep `DANGEROUS_PATTERNS` เหลือที่เดียวคือ `validation_service.py`
- [ ] อัปเดต `IMPLEMENTATION_STATUS.md` (Security section)
