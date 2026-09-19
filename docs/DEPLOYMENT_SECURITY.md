# Deployment Security Notes

## Business DB — Read-only Enforcement (F4.1, 2026-07-11)

### SQLite (dev / current)

MCP servers (`nt_query_mcp`, `nt_metadata_mcp`) open the business DB with
`mode=ro` at the connection level. Writes fail with
`attempt to write a readonly database` even if regex validation is bypassed.

- The DB file **must exist** before the MCP server starts (fail-loud by design).
- WAL mode is supported as long as the `-wal`/`-shm` files are readable.
- `immutable=1` is intentionally NOT used — ETL updates the file while the app runs.

Note: the app-side SQLAlchemy `business_engine` is NOT read-only because the
admin view-manager feature legitimately creates/drops views in the business DB
(see `app/services/schema/view_manager.py`). See `plan/FIX_NOTES.md`.

### MSSQL (production)

Read-only enforcement happens at the **credential level** — the login used for
the business DB connection string must have `SELECT` only (`db_datareader`
role, no `db_datawriter`/`db_owner`). The query MCP server logs a one-line
reminder at startup when `engine=mssql`.

## Plan 7 — file sources, scope, workspace keys (2026-09-19)

- **Upgrade:** รัน `python scripts/migrate_data_sources.py` และ `python scripts/migrate_workspaces.py` (idempotent) — คอลัมน์ใหม่ของ `api_keys` app เติมเองตอน lookup ครั้งแรก แต่ฝั่ง config DB ต้องรัน script
- **File source (DuckDB):** read-only, `allowed_paths` = ไฟล์ของ build, `enable_external_access=false`, `lock_configuration=true`, SQL จาก LLM ผ่าน query gate (`check_select`) เสมอ — ห้ามผ่อน
- **`DATA_SOURCE_ALLOWED_ROOTS`** (.env, คั่นด้วย `,`; ค่าเริ่มต้นว่าง): directory ที่ `POST /admin/sources/register` อ่าน bundle **ใหม่**ได้ (เทียบด้วย realpath) — ว่าง = API ลงทะเบียนซ้ำได้เฉพาะโดเมนที่ลงไว้แล้ว; CLI ไม่ถูกจำกัด. เป็นค่าใน .env โดยตั้งใจ (ขอบเขตความปลอดภัยของ admin API เอง ไม่ให้แก้ผ่าน UI)
- **Key ที่ผูก workspace/allowlist:** ใช้ได้เฉพาะ `/api/v1/query*`; context นอกสิทธิ์ = 403; context legacy อ่านได้เฉพาะ main view ที่ชั้น SQL — ออก key ของระบบภายนอกแบบนี้เสมอ (`docs/manuals/manual_api_keys.md`)
- **`scope`** ใน `/api/v1/query`: บังคับที่ชั้น SQL; key ที่ context ไม่ประกาศ = 400 (`docs/PORTAL_INTEGRATION.md`)
- **Vanna brain ต่อ workspace:** `<VANNA_CHROMA_PATH>__<workspace>` (default ใช้ path เดิม) — backup/restore ต้องรวม directory เหล่านี้

## Plan 7 Phase 4.5 — Data protection (2026-09-19)

- **Upgrade:** รัน `python scripts/migrate_data_sources.py` + `python scripts/migrate_workspaces.py` อีกครั้ง (idempotent — เพิ่ม `data_sources.llm_data_policy` / `llm_provider_allowlist`, `workspaces.result_retention_days` / `store_result_data`); ตาราง `query_audit` (app DB) ถูกสร้างเองตอนใช้ครั้งแรก. Source เดิมและ source ใหม่ทุกตัว = `full` → พฤติกรรมไม่เปลี่ยนจนกว่า admin จะตั้ง
- **`llm_data_policy` ต่อ source** (`PUT /admin/sources/{name}/policy`):
  | ค่า | provider เห็นอะไร |
  |---|---|
  | `full` | เหมือนก่อน Phase 4.5 (ค่าตัวอย่าง, value lookup, แถวผลลัพธ์, RAG) |
  | `aggregated_only` | เหมือน `schema_only` ยกเว้น: แถวผลลัพธ์ของ SQL ที่รวมยอด (GROUP BY / SUM / COUNT / AVG, ไม่มี window function, ไม่มี `*`) ส่งให้ LLM อธิบายได้ — **เป็นการตรวจจากข้อความ SQL ไม่ใช่ k-anonymity**: GROUP BY บน key ที่ไม่ซ้ำยังผ่าน → ข้อมูลที่ห้ามเห็นรายแถวเด็ดขาดให้ใช้ `schema_only` |
  | `schema_only` | schema + คำถาม + ความรู้ที่คน/contract เขียน (instruction, กฎ, mapping) เท่านั้น — ไม่มีค่าตัวอย่าง, value lookup, RAG/golden, แถวผลลัพธ์, คำตอบเก่าใน history, ค่าใน error/hint; คำอธิบายผล = template ไม่ผ่าน LLM; tool loop (`mode=mcp`) ถูกปฏิเสธ (403) |
  - บังคับที่ **ชั้น provider** (`AIProvider.__init_subclass__` → `app/core/llm_policy.py: guard_call`) — provider ที่เพิ่มภายหลังถูกห่อเอง — และที่ **ต้นทางของค่า** (`get_sample_values`, value lookup, value verifier, RAG, onboarding, keyword index, hierarchy); caller ตรงกลางไม่ต้องรู้จัก policy
  - อ่าน policy ไม่ได้ / ค่าไม่รู้จัก / NULL = `schema_only`; allowlist ที่ parse ไม่ได้ = ไม่มี provider ใดผ่าน
  - ตั้งเข้มขึ้นผ่าน API → ลบ `keyword_value_index` ของ context ใน source นั้นทันที + ล้าง query cache; ค่าที่เคย extract ไว้ใน `master_hierarchy_values` ยังอยู่ใน config DB แต่ไม่ถูกค้น/ส่งอีก
- **`llm_provider_allowlist` ต่อ source:** provider นอกรายการถูกปฏิเสธที่ชั้น provider; ผู้เรียกระบุ provider นอกรายการ = 403 (ไม่สลับเงียบ); ไม่ระบุ = ระบบเลือกตัวแรกในรายการที่ตั้งค่าไว้. **D4 (ตัดสิน 2026-09-19): Matcha (NT Gateway) ใช้กับข้อมูลอ่อนไหวได้** → source อ่อนไหวตั้ง `["matcha"]`. ⚠️ allowlist คุม *ชื่อ provider* — gateway ส่งต่อไปที่โมเดลใด/ที่ใดเป็นเรื่องของสัญญากับ gateway ไม่ใช่สิ่งที่ code ตรวจได้
- **นอกขอบเขตของ `llm_data_policy`** (ไม่ใช่ LLM provider หรือไม่มี source ให้ผูก): Telegram (ส่ง 15 แถว + กราฟไป Bot API), ไฟล์ที่ admin upload ให้ schema analyzer, คำถาม/SQL ของผู้ใช้ที่ admin agent สรุป — ดู `plan/archive/RESULT_P7_PHASE45.md`
- **Retention:** `result_retention_days` (admin_config, **default 30**, 0 = ไม่ลบ; `PUT /admin/config/settings/result_retention_days`) — job รายวันล้าง `chat_history.result_data` + `sql_result_summary`, `chat_session_data`, `query_correction_log`, CSV ชั่วคราวของ chat tool; คำถาม / SQL / คำตอบ / `render_meta` อยู่ครบ. ⚠️ **รอบแรกหลัง upgrade จะล้างผลลัพธ์ที่เก่ากว่า 30 วันทั้งหมด** (ประวัติยังเปิดอ่านได้ แต่ไม่มีตาราง/กราฟ) — ต้องการเก็บนานกว่า ให้ตั้งค่าก่อน start. `store_result_data=false` (feature flag) = ไม่เขียนแถวผลลัพธ์ลง history / session data / query cache เลย. Override ต่อ workspace: `PUT /admin/workspaces/{id}/retention`
- **DSR:** `DELETE /admin/users/{id}/data` (`dry_run=true` เป็นค่าเริ่มต้น = นับอย่างเดียว) — ลบ history, session data, conversations, feedback, exports + ไฟล์, admin-agent conversations, query cache; `query_audit` คงแถวไว้แต่ตัด `user_id` + คำถาม; บัญชีและ API key ไม่ถูกแตะ. **ไม่ย้อนกลับได้** — backup app DB ก่อน
- **Audit ของคำถาม:** `query_audit` เขียนที่ `QueryEngine.query` (chat, `/api/v1/query`, telegram) และที่ xlsx export (`channel` = `report_export` ตอนขอ, `report_download` ตอนดาวน์โหลด พร้อมจำนวนแถว): user, api_key, channel, workspace, context, scope, คำถาม, SQL, ชื่อคอลัมน์, จำนวนแถว, provider, policy, cache_hit, error (รวมคำขอที่ถูกปฏิเสธ) — **ไม่มีค่าผลลัพธ์**. ค้น/ export: `GET /admin/query-audit?...&format=csv`. เขียนไม่ได้ = ERROR ใน log แต่คำตอบยังออก (availability ก่อน) — ตั้ง alert ที่ข้อความ `query audit NOT written`
- ⚖️ กรอบ PDPA (§6.6 ข้อ 8 ของแผน) ยังต้องให้ DPO/ฝ่ายกฎหมายทบทวน — มาตรการข้างบนเป็นเครื่องมือทางเทคนิค ไม่ใช่การรับรองความสอดคล้องตามกฎหมาย

## API Key Rate Limiting (F4.4)

- Daily limit: enforced in DB (`api_key_usage`).
- Per-minute limit: Redis fixed-window (`ratelimit:apikey:<id>:<minute>`).
  Requires `REDIS_URL`. When Redis is unavailable the check **fails open**
  (availability first for internal use) and logs a warning once per process.
