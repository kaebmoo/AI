# MCP สำหรับผู้เรียกภายนอก — คู่มือเชื่อมต่อ (Plan 7 Phase 6)

ถามข้อมูลจาก NT AI Assistant ผ่าน MCP client (Claude Code, Gemini CLI, Codex CLI, หรือโปรแกรมของเราเองที่ใช้ MCP SDK)
— ช่องทางเดียวกับ `POST /api/v1/query` ทุกประการเรื่องสิทธิ: workspace / allowlist ของ key, `scope`, audit, cache, คำถามข้าม context

| | |
|---|---|
| URL | `http://<host>:<port>/api/v1/mcp` (ไม่มี `/` ท้าย) |
| Transport | Streamable HTTP แบบ **stateless** — ไม่มี session ฝั่ง server, ไม่มี legacy SSE |
| Auth | header `X-API-Key` **ทุก request** |
| Tools | `ask`, `list_contexts`, `source_status` — เท่านี้ |

> MCP server ภายใน (`mcp_servers/*.py` — `execute_query`, `get_sample_values`, admin tools) **ไม่ได้ถูกเปิดออกมา** และห้ามต่อ client ภายนอกเข้ากับ server เหล่านั้นตรง ๆ: ไม่มี key, ไม่มี allowlist, ไม่มี scope, ไม่มี audit

## 1. เปิดใช้งาน (admin)

ปิดเป็นค่าเริ่มต้น — endpoint ตอบ `404` จนกว่าจะเปิด flag (ไม่ต้อง deploy ใหม่):

```bash
curl -X POST "http://localhost:8000/api/v1/admin/config/features/mcp_external_enabled/toggle?enabled=true" \
  -H "X-Session-Token: <admin session>"
```

ต้องรัน migration ของ Phase 4.5 ก่อน (`scripts/migrate_data_sources.py`) — registry ที่ยังไม่มีคอลัมน์ `llm_data_policy`
ถือว่า**อ่าน policy ไม่ได้** และทุก context ถูกปฏิเสธบนช่องทางนี้ (fail closed)

Deployment ที่ไม่ได้เรียกผ่าน `localhost` / `127.0.0.1` ต้องตั้ง `.env`:

```
MCP_ALLOWED_HOSTS=127.0.0.1:*,localhost:*,ai.example.nt:*,ai.example.nt
MCP_ALLOWED_ORIGINS=            # ว่าง = request ที่มี Origin (browser) ถูกปฏิเสธ 403 ทั้งหมด
MCP_MAX_ROWS=100                # เพดานแถวของ ask(include_data=true)
```

Host ที่ไม่อยู่ในรายการ = `421`; ถ้ามี reverse proxy ต้องส่ง `Host` เดิมมาให้ หรือเพิ่ม host ของ proxy ในรายการ

## 2. ออก key

Key ที่ใช้กับ MCP ต้อง **(1) ผูก workspace หรือ allowlist (2) มี scope `query` หรือ `full` (3) เจ้าของ key ยัง active**
— key แบบเดิมที่ไม่ผูกอะไรเลย (เห็นทุก context) ใช้กับ MCP **ไม่ได้** (401) เพราะ key นี้จะไปอยู่ในเครื่องของผู้ใช้

ดู [manual_api_keys.md](manual_api_keys.md) หัวข้อ "Key ที่ผูก workspace" — เช่น key ของ workspace `nt-report` เห็น `feed_*` ทั้งสี่

⚠️ **สิ่งที่ผู้ถือ key ทำได้:** อ่าน**ทุกแถว**ของทุก context ที่ key เห็น. `scope` ที่ client ส่งมาใช้กรองให้แคบลงได้ (ยังบังคับที่ชั้น SQL)
แต่**ไม่ใช่สิทธิระดับแถว** — ผู้เรียกคือ LLM ที่เลือก argument เอง. ถ้าผู้ใช้ควรเห็นแค่บางหน่วยงาน/บางรายงาน ให้ใช้ REST ผ่าน server
ที่เชื่อถือได้ซึ่งเป็นผู้ใส่ `scope` (แบบ NT-Report portal) ไม่ใช่แจก key ให้ desktop

⚠️ **คำตอบเข้า LLM ของ client:** ตัวเลขและแถวที่คืนไปจะเข้าโมเดลที่เราไม่ได้คุม (`llm_data_policy` / `llm_provider_allowlist`
คุมได้เฉพาะ provider ฝั่งเรา) — context ที่ source มี policy ไม่ใช่ `full` จึง**ไม่มีอยู่**บนช่องทางนี้: ไม่อยู่ใน `list_contexts`, ระบุชื่อ = `policy_refused`

## 3. ต่อ client

เก็บ key ใน environment variable — อย่าพิมพ์ key ลง command line (ค้างใน shell history และ config เป็น plaintext)

**Claude Code** (ทดสอบแล้วกับ 2.1.270):

```bash
export NT_AI_API_KEY=ntai_...
claude mcp add --transport http nt-ai http://127.0.0.1:8000/api/v1/mcp --header 'X-API-Key: ${NT_AI_API_KEY}'
```

(`--header` ต้องอยู่**ท้ายสุด** — เป็น option แบบรับหลายค่า; ใช้ single quote เพื่อให้ Claude Code เป็นผู้ขยาย `${...}` ตอนเชื่อมต่อ.
ตัวแปรที่ไม่ได้ตั้งจะถูกส่งเป็นข้อความ `${NT_AI_API_KEY}` ตรง ๆ → 401)

หรือแบบไม่แตะ config ถาวร:

```bash
cat > mcp.json <<'EOF'
{"mcpServers": {"nt-ai": {"type": "http", "url": "http://127.0.0.1:8000/api/v1/mcp",
                          "headers": {"X-API-Key": "${NT_AI_API_KEY}"}}}}
EOF
claude --mcp-config mcp.json --strict-mcp-config
```

**Gemini CLI:** `gemini mcp add --transport http nt-ai http://127.0.0.1:8000/api/v1/mcp --header "X-API-Key: $NT_AI_API_KEY"` (ตาม `--help` ของ 0.58.0 — ยังไม่ได้ทดสอบต่อจริง)

**Codex CLI:** ใส่ใน `~/.codex/config.toml` — `url = "…/api/v1/mcp"` + `env_http_headers = { "X-API-Key" = "NT_AI_API_KEY" }` (ตามเอกสาร — ยังไม่ได้ทดสอบต่อจริง)

**Claude Desktop** — ผ่านตัวแปลง stdio (`scripts/mcp_stdio_bridge.py`):

Desktop ต่อ HTTP เองไม่ได้ (remote connector ของมันออกจาก cloud ของ Anthropic จึงเข้า `localhost` ไม่ได้ และตั้ง header เองไม่ได้)
แต่มันรัน process ในเครื่องแล้วคุยทาง stdio ได้ — bridge คือตัวแปลงระหว่างสองฝั่งนั้น ส่งต่อ tool ตามที่ server ประกาศ
ไม่เพิ่ม tool ของตัวเอง และส่ง tool error ทั้งก้อน. key อยู่ใน `env` ของ config ไม่ได้ถูกเขียนลงที่อื่น

⚠️ คำตอบ (รวมตัวเลข) จะไปถึงโมเดลของ Anthropic เหมือนกับตอนใช้ Claude Code — ใช้ key ของ workspace ที่ยอมรับได้

แก้ `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) แล้ว**ปิด-เปิด Claude Desktop ใหม่**:

```json
{
  "mcpServers": {
    "nt-ai": {
      "command": "/path/to/AI/venv/bin/python",
      "args": ["/path/to/AI/scripts/mcp_stdio_bridge.py"],
      "env": {
        "NT_AI_API_KEY": "ntai_...",
        "NT_AI_BASE_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

(`command` = python ของ venv ที่มี `mcp` ติดตั้งอยู่ — ไม่ต้องลง npm package ใด ๆ; `NT_AI_BASE_URL` ไม่ใส่ = `http://127.0.0.1:8000`.
ไฟล์นี้เป็น plaintext ในเครื่องผู้ใช้ → ใช้ key ที่ revoke ได้และผูก workspace เดียว)

ตรวจก่อนเสียบ Desktop: `NT_AI_API_KEY=ntai_... venv/bin/python scripts/mcp_stdio_bridge.py` แล้วปล่อยค้างไว้ —
ถ้า key ผิด / flag ปิด / server ไม่ขึ้น bridge จะจบทันทีพร้อมเหตุผลบรรทัดเดียว (Desktop แสดงข้อความนี้ใน log ของ server)


**โปรแกรมของเราเอง (Python, MCP SDK):** ดู [`scripts/mcp_client_example.py`](../../scripts/mcp_client_example.py)

```bash
export NT_AI_API_KEY=ntai_...  NT_AI_BASE_URL=http://127.0.0.1:8000
python scripts/mcp_client_example.py list
python scripts/mcp_client_example.py status feed_revenue
python scripts/mcp_client_example.py ask "รายได้รวมของงวดล่าสุดเท่าไหร่" --context feed_revenue --data
python scripts/mcp_client_example.py bench "รายได้รวมของงวดล่าสุดเท่าไหร่" --context feed_revenue --n 12
```

## 4. Tools

### `ask(question, context?, scope?, include_data?=false)`
คำถามเดี่ยว ไม่มีประวัติสนทนา — client เป็นผู้ถือบริบทเอง. ไม่ใส่ `context` = ระบบเลือกเองภายในสิทธิ์ของ key
(และถ้า workspace เปิดคำถามข้าม context ไว้ อาจได้ `parts[]` + `computed` เหมือน REST). คืน: `answer`, `context`, `row_count`,
`execution_time_ms`, `data_as_of` {period, built_at, build_id} และ `data` เมื่อ `include_data=true` (รวมทั้งคำตอบไม่เกิน `MCP_MAX_ROWS` แถว —
คำถามข้าม context แบ่งเพดานต่อ part). คำถามที่ไม่พบข้อมูลได้ข้อความตายตัว "ไม่พบข้อมูลที่ตรงกับเงื่อนไข".
**ไม่มี SQL** ในทุกกรณี

### `list_contexts()`
`name`, `display_name`, `description` ของ context ที่ key นี้ใช้ผ่าน MCP ได้ — ไม่มีชื่อ context นอกสิทธิ์

### `source_status(context)`
`status` (`ok` / `unavailable`), `source_kind` (`file` / `legacy`), `data_as_of`, `schema_version` — ไม่มี path / ชื่อ source / สาเหตุที่ใช้ไม่ได้

## 5. Error

Key ผิด / ถูก revoke / หมดอายุ / เจ้าของถูกปิด / ไม่ได้ผูก workspace = **HTTP 401** ทุก request (รวมกลางการใช้งาน — มีผลทันที
ใน request ถัดไป; MCP client จะเห็นเป็นการเชื่อมต่อล้ม). GET / DELETE = 405. ที่เหลือกลับมาเป็น tool error (`isError=true`)
พร้อม `structuredContent.error = {code, http_status, message, request_id}` — ข้อความตายตัว ไม่มีข้อความ exception / SQL / path:

| code | เทียบ HTTP | ความหมาย |
|---|---|---|
| `rate_limited` | 429 | เกิน rate limit ต่อนาที หรือโควตารายวันของ key (นับรวมกับ REST) |
| `invalid_scope` | 400 | `scope` มี key ที่ context ไม่ได้ประกาศ หรือค่าไม่ถูก — ไม่ตอบแบบไม่มี scope |
| `context_not_allowed` | 403 | context นอกสิทธิ์ของ key **หรือไม่มีอยู่** (คำตอบเดียวกัน) — ไม่ re-route ให้ |
| `policy_refused` | 403 | context อยู่ในสิทธิ์ของ key แต่ source ไม่ใช่ `full` / อ่าน policy ไม่ได้ |
| `invalid_arguments` | 400 | argument ใช้ไม่ได้ เช่น `question` ว่าง (argument ผิดชนิด / ชื่อ tool ที่ไม่มี ถูก MCP SDK ตอบเองก่อนถึง tool — ไม่นับ usage) |
| `duplicate_request` | 409 | คำถามเดียวกันของ user เดียวกันภายใน 5 วินาที |
| `source_unavailable` | 503 | แหล่งข้อมูลยังไม่พร้อม |
| `query_failed` | 422 | pipeline ตอบไม่ได้ (รายละเอียดอยู่ใน log / `query_audit` ฝั่ง server ตาม `request_id`) |
| `internal_error` | 500 | อื่น ๆ |

## 6. โควตาและ audit

- **1 tool call = 1 usage** — ตัวนับเดียวกับ REST (`api_key_usage` รายวัน + Redis รายนาที). `initialize` / `tools/list` ผ่านการตรวจ key
  ทุกครั้งแต่ไม่นับโควตา. Redis ล่ม = limit รายนาทีไม่ทำงาน (พฤติกรรมเดิมของ REST)
- ปิด workspace = context ของ workspace นั้นหายจากช่องทางนี้ทันที (รวม key ที่ผูกด้วย allowlist อย่างเดียว)
- ทุก `ask` ลง `query_audit` ด้วย `channel = mcp:<user-agent ของ client>` (เช่น `mcp:claude-code/2.1.270`) — ชื่อ client เป็นข้อมูลที่ client
  แจ้งเอง ใช้ประกอบการตรวจสอบเท่านั้น; `GET /admin/query-audit?channel=mcp` เจอทุก `mcp:<client>`. REST ส่ง `source` ที่ขึ้นต้นด้วย `mcp` ไม่ได้ (ถูกบันทึกเป็น `api:mcp…`)
- Client ตัดการเชื่อมต่อกลางคำถาม: pipeline ฝั่ง server ทำงานจนจบและลง audit ตามปกติ

## 7. Latency (วัดบนเครื่องพัฒนา, 2026-09-20, DB สำเนา, key เดียวกัน คำถามเดียวกัน)

| | REST `/api/v1/query` | MCP `ask` |
|---|---|---|
| เส้นทาง cache (n=12) P50 / P95 | 12.9 / 17.6 ms | 19.5 / 29.0 ms |
| คำตอบแรก (LLM จริง) | 7.4 s | 8.1 s (คนละคำถาม) |

Overhead ของ transport ≈ +7 ms (P50) / +11 ms (P95). คำถามจริงใช้ 7–10 วินาที (ข้าม context ~8–9 วินาที) — ตั้ง tool timeout
ของ client ≥ 60 วินาที (ค่าเริ่มต้นของ Codex = 60 s)
