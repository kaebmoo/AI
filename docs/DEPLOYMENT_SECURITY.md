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

## API Key Rate Limiting (F4.4)

- Daily limit: enforced in DB (`api_key_usage`).
- Per-minute limit: Redis fixed-window (`ratelimit:apikey:<id>:<minute>`).
  Requires `REDIS_URL`. When Redis is unavailable the check **fails open**
  (availability first for internal use) and logs a warning once per process.
