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

## API Key Rate Limiting (F4.4)

- Daily limit: enforced in DB (`api_key_usage`).
- Per-minute limit: Redis fixed-window (`ratelimit:apikey:<id>:<minute>`).
  Requires `REDIS_URL`. When Redis is unavailable the check **fails open**
  (availability first for internal use) and logs a warning once per process.
