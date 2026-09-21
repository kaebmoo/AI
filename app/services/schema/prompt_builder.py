import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from app.services.schema.service import SchemaService


logger = logging.getLogger(__name__)


def build_schema_text(service: "SchemaService", table_name: str) -> str:
    """Build schema information text for AI prompt."""
    metadata = service.get_schema_metadata(table_name)
    if metadata:
        return _build_schema_from_metadata(metadata, table_name)
    return _build_schema_from_pragma(service, table_name)


def _build_schema_from_metadata(metadata: List[Dict], table_name: str) -> str:
    schema_text = f"## Table: {table_name}\n\n"
    schema_text += "| Column | Type | ชื่อไทย | SUM? | GROUP BY? | หมายเหตุ |\n"
    schema_text += "|--------|------|---------|------|-----------|----------|\n"

    for column in metadata:
        can_sum = "✅" if column.get("is_summable") else "❌"
        can_group = "✅" if column.get("is_groupable") else "❌"
        notes = column.get("special_notes") or ""
        if column.get("conversion_sql"):
            notes += f" แปลงด้วย: `{column['conversion_sql']}`"

        schema_text += f"| {column['column_name']} | {column.get('data_type', 'TEXT')} | "
        schema_text += f"{column.get('display_name_th', '')} | {can_sum} | {can_group} | {notes} |\n"

    return schema_text


def _build_schema_from_pragma(service: "SchemaService", table_name: str) -> str:
    columns = service.get_table_info(table_name)

    schema_text = f"## Table: {table_name}\n\n"
    schema_text += "| Column | Type |\n"
    schema_text += "|--------|------|\n"

    for column in columns:
        schema_text += f"| {column['name']} | {column['type']} |\n"

    return schema_text


def build_business_rules_text(service: "SchemaService", table_name: str) -> str:
    rules = service.get_business_rules(table_name, inject_mode="schema_context")
    if not rules:
        return _get_default_business_rules()

    rules_text = "## Business Rules\n\n"
    for rule in rules:
        severity_icon = {"error": "🚫", "warning": "⚠️", "info": "ℹ️"}.get(rule.get("severity", "info"), "ℹ️")
        rules_text += f"### {severity_icon} {rule['rule_name']}\n"
        rules_text += f"{rule['rule_description']}\n\n"

        if rule.get("example_correct"):
            rules_text += f"✅ **Correct:**\n```sql\n{rule['example_correct']}\n```\n\n"
        if rule.get("example_wrong"):
            rules_text += f"❌ **Wrong:**\n```sql\n{rule['example_wrong']}\n```\n\n"

    return rules_text


def _get_default_business_rules() -> str:
    return """## Business Rules

### ⚠️ DATE Column Conversion
DATE เก็บเป็น Unix Timestamp (milliseconds) ต้องแปลงก่อนแสดงผล

### ⚠️ Thai Year Conversion
ปี พ.ศ. = ปี ค.ศ. + 543

### ℹ️ Common Abbreviations (คำย่อหน่วยงาน)
- **นป.** = `กลุ่มขายและปฏิบัติการลูกค้า ภาคเหนือ`
- **บชง.** = `ฝ่ายบัญชีบริหารและกรอบอัตราค่าบริการ`
"""


def build_sample_values_text(service: "SchemaService", table_name: str) -> str:
    samples = service.get_sample_values(table_name)
    sample_text = "## Available Values\n\n"

    if "DATA_RANGE" in samples:
        date_range = samples["DATA_RANGE"]
        sample_text += f"**Data Range:** {date_range.get('min_year')}/{date_range.get('min_month')} - {date_range.get('max_year')}/{date_range.get('max_month')}\n\n"

    for column_name, values in samples.items():
        if column_name == "DATA_RANGE":
            continue
        if values:
            sample_text += f"**{column_name}:**\n"
            for value in values[:10]:
                sample_text += f"- {value}\n"
            if len(values) > 10:
                sample_text += f"- ... และอื่นๆ อีก {len(values) - 10} รายการ\n"
            sample_text += "\n"

    return sample_text


def build_semantic_mapping_text(service: "SchemaService", context_name: Optional[str] = None) -> str:
    mappings = service.get_semantic_mappings(context_name=context_name)
    if not mappings:
        return _get_default_semantic_mappings()

    mapping_text = "<semantic_mappings>\n"
    mapping_text += "## 🔥 SEMANTIC MAPPINGS - REFERENCE GUIDE 🔥\n\n"
    mapping_text += "<rules>\n"
    mapping_text += "1. ตรวจสอบ mappings ด้านล่างก่อนสร้าง SQL ทุกครั้ง\n"
    mapping_text += "2. ถ้าเจอ keyword → ใช้ mapping เป็น **reference** สำหรับหา column ที่ถูกต้อง\n"
    mapping_text += "3. ⚠️ ถ้ามี 'Actual Values Found' section → **ให้เชื่อค่าจาก Actual Values** เพราะมาจาก DB จริง\n"
    mapping_text += "4. สำหรับ text columns: ใช้ LIKE '%keyword%' เสมอ ยกเว้น mapping ระบุ LIKE pattern ไว้แล้ว\n"
    mapping_text += "</rules>\n\n"

    mapping_text += "<examples>\n"
    mapping_text += "✅ CORRECT:\n"
    mapping_text += "User: \"trunk radio\"\n"
    mapping_text += "SQL: WHERE (UPPER(product_name) LIKE '%TRUNK%' OR UPPER(product_name) LIKE '%TRUNKED%' OR product_name LIKE '%วิทยุเฉพาะกิจ%')\n\n"
    mapping_text += "❌ WRONG (DO NOT DO THIS):\n"
    mapping_text += "User: \"trunk radio\"\n"
    mapping_text += "SQL: WHERE UPPER(product_name) LIKE '%TRUNK RADIO%'\n"
    mapping_text += "     OR UPPER(product_name) LIKE '%TRUNKED RADIO%'\n"
    mapping_text += "Reason: ห้ามสร้าง pattern เอง ต้องใช้ mapping ที่มีอยู่\n"
    mapping_text += "</examples>\n\n"

    abbreviations = [mapping for mapping in mappings if mapping.get("keyword_type") == "abbreviation"]
    terms = [mapping for mapping in mappings if mapping.get("keyword_type") == "term"]
    synonyms = [mapping for mapping in mappings if mapping.get("keyword_type") == "synonym"]

    if abbreviations:
        mapping_text += "### คำย่อหน่วยงาน (Abbreviations)\n"
        mapping_text += "| คำย่อ | SQL Condition | ความหมาย |\n"
        mapping_text += "|-------|---------------|----------|\n"
        for mapping in abbreviations:
            condition = mapping.get("full_condition") or f"{mapping['target_column']} {mapping['target_condition']}"
            mapping_text += f"| {mapping['keyword']} | `{condition}` | {mapping.get('description', '')} |\n"
        mapping_text += "\n"

    if terms:
        mapping_text += "### คำศัพท์ธุรกิจ (Business Terms)\n"
        mapping_text += "| คำค้น | SQL Condition | ความหมาย |\n"
        mapping_text += "|-------|---------------|----------|\n"
        for mapping in terms:
            condition = mapping.get("full_condition") or f"{mapping['target_column']} {mapping['target_condition']}"
            mapping_text += f"| {mapping['keyword']} | `{condition}` | {mapping.get('description', '')} |\n"
        mapping_text += "\n"

    if synonyms:
        mapping_text += "### คำพ้องความหมาย (Synonyms) - MUST USE EXACTLY AS SHOWN\n"
        mapping_text += "<synonym_mappings>\n"
        for mapping in synonyms:
            condition = mapping["full_condition"] if mapping.get("full_condition") else f"{mapping['target_column']} {mapping['target_condition']}"
            mapping_text += f"<mapping keyword=\"{mapping['keyword']}\">\n"
            mapping_text += f"  SQL: {condition}\n"
            mapping_text += f"  Note: {mapping.get('description', 'N/A')}\n"
            mapping_text += "</mapping>\n"
        mapping_text += "</synonym_mappings>\n\n"

    mapping_text += "</semantic_mappings>\n\n"
    mapping_text += "<reminder>\n"
    mapping_text += "⚠️ ก่อนสร้าง WHERE clause ทุกครั้ง:\n"
    mapping_text += "1. ถ้ามี 'Actual Values Found' → ใช้ค่าจากนั้นเป็นหลัก (มาจาก DB จริง)\n"
    mapping_text += "2. หา keyword ที่ user ใช้ใน <semantic_mappings> เพื่อหา column ที่ถูกต้อง\n"
    mapping_text += "3. สำหรับ text columns: ใช้ LIKE '%keyword%' เสมอ\n"
    mapping_text += "</reminder>\n"
    return mapping_text


def _get_default_semantic_mappings() -> str:
    return """## Semantic Mappings
- **นป.** → `organization_group_abbr = 'นป.'`
- **บชง.** → `department_abbr = 'บชง.'`
- **Broadband** → `SERVICE_GROUP = 'กลุ่มบริการ Internet Retail'`
- **Mobile** → `BUSINESS_GROUP = 'Mobile'`
"""


def get_schema_context(
    service: "SchemaService",
    context_name: str = "revenue",
    include_samples: bool = True,
    include_semantic_mappings: bool = True,
    lite_mode: bool = False,
) -> str:
    context_info = service.get_context_info(context_name)
    if not context_info:
        logger.error("get_schema_context: Context '%s' not found in schema_contexts — returning empty context", context_name)
        return f"# ERROR: Context '{context_name}' not configured in database.\n"

    main_view = context_info["main_view"]
    display_name = context_info.get("display_name", context_name)

    context_text = f"# Context: {display_name} ({context_name})\n"
    context_text += build_schema_text(service, table_name=main_view)
    context_text += "\n\n" + build_business_rules_text(service, table_name=main_view)

    if not lite_mode:
        if include_semantic_mappings:
            context_text += "\n\n" + build_semantic_mapping_text(service, context_name=context_name)
        if include_samples:
            context_text += "\n\n" + build_sample_values_text(service, table_name=main_view)
    else:
        if include_semantic_mappings:
            context_text += "\n\n" + build_semantic_mapping_text(service, context_name=context_name)
        samples = service.get_sample_values(table_name=main_view)
        if "DATA_RANGE" in samples:
            date_range = samples["DATA_RANGE"]
            context_text += f"\n\n## Available Values\n**Data Range:** {date_range.get('min_year')}/{date_range.get('min_month')} - {date_range.get('max_year')}/{date_range.get('max_month')}\n"
        context_text += "\n(Detailed sample values omitted for RAG optimization - relevant items will be injected)"

    context_text += "\n\n" + build_date_instructions(service, main_view, context_info.get("scope_columns"))
    context_text += f"\n\n## Current Date\nวันที่ปัจจุบัน: {datetime.now().strftime('%Y-%m-%d')}\n"
    context_text += f"ปี พ.ศ. ปัจจุบัน: {datetime.now().year + 543}\n"
    return context_text


def build_system_prompt(
    service: "SchemaService",
    ai_provider: str = "claude",
    include_samples: bool = True,
    language: str = "thai",
    context_name: str = "revenue",
    rag_enabled: bool = False,
) -> str:
    import time as _time

    # Date in cache key → prompt rebuilt daily (its Current Date section must not go stale)
    today = datetime.now().strftime('%Y-%m-%d')
    cache_key = f"prompt|{ai_provider}|{context_name}|{language}|{include_samples}|{rag_enabled}|{today}"
    cached = service.get_cached_value(cache_key)
    if cached and (_time.time() - cached.get("_ts", 0)) < 21600:
        logger.debug("System prompt cache HIT: %s", cache_key)
        return cached["value"]

    context_info = service.get_context_info(context_name)
    if not context_info:
        logger.error("Context '%s' not found in schema_contexts — cannot build prompt", context_name)
        return f"ERROR: Context '{context_name}' not configured in database. Please add it via Admin UI."

    main_view = context_info["main_view"]
    if language == "thai":
        instruction = _build_thai_prompt(service, ai_provider, main_view, context_name, context_info)
    else:
        instruction = _build_english_prompt(service, ai_provider, main_view, context_name, context_info)

    context_text = get_schema_context(
        service,
        context_name=context_name,
        include_samples=include_samples,
        lite_mode=rag_enabled,
    )
    result = f"{instruction}\n\n{context_text}"
    service.set_cached_value(cache_key, {"value": result, "_ts": _time.time()})
    logger.debug("System prompt cached: %s (%s chars)", cache_key, len(result))
    return result


def get_default_instruction(
    service: "SchemaService",
    ai_provider: str = "claude",
    language: str = "thai",
    context_name: str = "revenue",
) -> str:
    context_info = service.get_context_info(context_name)
    if not context_info:
        logger.error("get_default_instruction: Context '%s' not found in schema_contexts", context_name)
        return f"ERROR: Context '{context_name}' not configured in database."

    main_view = context_info["main_view"]
    if language == "thai":
        return _build_thai_prompt(service, ai_provider, main_view, context_name, context_info)
    return _build_english_prompt(service, ai_provider, main_view, context_name, context_info)


def _is_duckdb(service: "SchemaService") -> bool:
    """True when the context's data source is a DuckDB file source (Plan 7)."""
    engine = getattr(service, "business_engine", None)
    return getattr(getattr(engine, "dialect", None), "name", None) == "duckdb"


def get_syntax_rules(service: "SchemaService", language: str = "thai") -> str:
    if _is_duckdb(service):
        from app.services.database_adapter import DUCKDB_SYNTAX_RULES
        return DUCKDB_SYNTAX_RULES["thai" if language == "thai" else "english"]
    if service.engine and service.engine.name == "postgresql":
        if language == "thai":
            return """   **. PostgreSQL Syntax:**
       - ใช้ `CONCAT(a, b)` หรือ `a || b` ได้
       - การจัดรูปแบบวันที่ใช้ `to_char(date, 'YYYY-MM')`
       - การแปลงชนิดข้อมูลใช้ `::integer` หรือ `CAST(col AS INTEGER)`"""
        return """   **. PostgreSQL Syntax:**
       - Use `CONCAT(a, b)` or `a || b`
       - Date formatting: `to_char(date, 'YYYY-MM')`
       - Type casting: `::integer` or `CAST(col AS INTEGER)`"""

    if language == "thai":
        return """   **. SQLite Syntax:**
       - ห้ามใช้ `CONCAT(a, b)` -> ให้ใช้ `a || b` แทน
       - ห้ามใช้ `LPAD` -> ให้ใช้ `printf('%02d', CAST(col AS INTEGER))`
       - ห้ามใช้ `DATE_FORMAT` -> ให้ใช้ `strftime`"""
    return """   **. SQLite Syntax:**
       - NO `CONCAT(a, b)` -> Use `a || b` instead
       - NO `LPAD` -> Use `printf('%02d', CAST(col AS INTEGER))`
       - NO `DATE_FORMAT` -> Use `strftime`"""


def _build_thai_prompt(
    service: "SchemaService",
    _ai_provider: str,
    main_view: str,
    context_name: str,
    context_info: Optional[Dict] = None,
) -> str:
    context_info = context_info or {}
    syntax_rules = get_syntax_rules(service, "thai")
    sql_dialect = "DuckDB" if _is_duckdb(service) else "SQLite"
    context_instructions = context_info.get("instruction_th") or ""
    hierarchy_rule = service.build_hierarchy_rule_text(context_name)
    instruction_rules = service.build_instruction_rules_text(main_view)

    return f"""<system>
คุณเป็น AI Assistant สำหรับวิเคราะห์ข้อมูลของ NT (National Telecom)
บริบทปัจจุบัน: **{context_name.upper()}** (ตาราง: `{main_view}`)

<critical_instructions>
⚠️⚠️⚠️ MUST READ BEFORE GENERATING SQL ⚠️⚠️⚠️

STEP 1: CHECK FOR ACTUAL VALUES FIRST
- ถ้ามี "Actual Values Found" section ใน user message → ใช้ค่าจากนั้น (มาจาก DB จริง)
- ใช้ LIKE '%keyword%' สำหรับ text columns เสมอ

{hierarchy_rule}

STEP 2: CHECK SEMANTIC MAPPINGS
- ถ้าไม่มี Actual Values → ตรวจ <semantic_mappings> section
- ใช้ mapping เป็น reference สำหรับหา column ที่ถูกต้อง
- สำหรับ text columns: แปลง = เป็น LIKE '%keyword%' เสมอ

STEP 3: FALLBACK
- ถ้าไม่มี Actual Values และไม่มี mapping → สร้าง LIKE pattern เอง
- ห้ามใช้ = กับ text columns ยกเว้นมั่นใจ 100% ว่าค่าตรงเป๊ะ
</critical_instructions>

## หน้าที่ของคุณ
1. รับคำถามภาษาไทย/อังกฤษ เกี่ยวกับ `{context_name}`
2. ตรวจสอบ <semantic_mappings> ก่อนเสมอ
3. สร้าง SQL Query โดยใช้ mapping ที่กำหนดไว้
4. อธิบายผลลัพธ์เป็นภาษาไทย

## กฎการสร้าง SQL
1. ใช้ {sql_dialect} syntax เท่านั้น
2. ใช้ query จาก table/view: **{main_view}**
3. Column ทั้งหมดเป็นภาษาอังกฤษ (ดู Schema ด้านล่าง)
4. การค้นหาข้อความ (Text Search):
   - **กฎการค้นหา:** ห้ามใช้ `=` กับชื่อไทย (เช่น account_name, department) ยกเว้นมั่นใจ 100%
   - **ให้ใช้ `LIKE '%keyword%'` เสมอ** สำหรับคำค้นทั่วไป
   - ตัวอย่าง: User หา "ค่าล่วงเวลา" -> `WHERE account_name LIKE '%ค่าล่วงเวลา%'`
5. กรองเวลาด้วยคอลัมน์เวลาของตารางนี้ตามหัวข้อ "Date Handling" ข้างล่างเท่านั้น
   - **กฎเหล็ก:** CAST คอลัมน์เวลาเป็น INTEGER ก่อนเทียบกับตัวเลขเสมอ
5. SELECT query เท่านั้น
   - ถ้ามี ORDER BY + LIMIT + UNION ต้องครอบด้วย Subquery
6. ห้ามใช้ table จริง ให้ใช้ view ที่กำหนดเท่านั้น
7. **ห้าม Format ตัวเลขใน SQL:** (สำคัญมาก!)
   - ห้ามใช้ `PRINTF`, `FORMAT` กับค่าเงิน/ตัวเลขคำนวณ
   - ต้องส่งค่าดิบ (Raw Number) เช่น `1234567.89` เท่านั้น
   - (Frontend จะจัดการใส่ลูกน้ำเอง)

{instruction_rules}

{context_instructions}

{syntax_rules}"""


def build_thai_prompt(
    service: "SchemaService",
    ai_provider: str,
    main_view: str,
    context_name: str,
    context_info: Optional[Dict] = None,
) -> str:
    return _build_thai_prompt(service, ai_provider, main_view, context_name, context_info)


def _build_english_prompt(
    service: "SchemaService",
    _ai_provider: str,
    main_view: str,
    context_name: str,
    context_info: Optional[Dict] = None,
) -> str:
    context_info = context_info or {}
    syntax_rules = get_syntax_rules(service, "english")
    sql_dialect = "DuckDB" if _is_duckdb(service) else "SQLite"
    context_instructions = context_info.get("instruction_en") or ""
    return f"""You are an AI Assistant for analyzing NT data.
Current Context: **{context_name.upper()}** (Table: `{main_view}`)

## Your Role
1. Answer questions about `{context_name}`
2. Generate SQL queries for `{main_view}`
3. Explain results in Thai

## SQL Rules
1. Use {sql_dialect} syntax
2. Query from: **{main_view}**
3. Use English column names (see Schema)
4. Filter time only with this table's time columns, listed under "Date Handling" below
   - Always CAST a time column to INTEGER before comparing it with a number
5. Wrap UNION + ORDER BY/LIMIT in subqueries
6. Do NOT query raw tables directly

{context_instructions}

{syntax_rules}

## Response Format
1. SQL Query
2. Thai Explanation
3. Formatted numbers"""


def build_english_prompt(
    service: "SchemaService",
    ai_provider: str,
    main_view: str,
    context_name: str,
    context_info: Optional[Dict] = None,
) -> str:
    return _build_english_prompt(service, ai_provider, main_view, context_name, context_info)


# Baseline detection of a table's time columns, so a view is usable the moment it is registered and
# before anyone writes metadata for it. It is a naming hint, nothing more: what the context DECLARES
# in scope_columns always wins, and when nothing here matches, the section is left out rather than
# naming columns that may not exist.
_TIME_HINTS = ("year", "month", "date", "time", "period", "quarter", "week",
               "ปี", "เดือน", "งวด", "ไตรมาส")


def is_time_column(name: str, is_measure: bool = False) -> bool:
    """A period column by its name — never one that carries an amount, however it is named (`ebt_month`
    is baht for the month). The same rule reads the years of an answer (`ai/thai_year.py`)."""
    return not is_measure and any(hint in name.lower() for hint in _TIME_HINTS)


def _table_columns(service: "SchemaService", table_name: str) -> List[tuple]:
    """[(column, is_measure)] from the table's metadata first and the database itself second — the
    same two steps build_schema_text takes, so it works for a file source and for a legacy view.
    Without metadata nothing is known to be a measure."""
    try:
        metadata = service.get_schema_metadata(table_name)
        if metadata:
            return [(c["column_name"], bool(c.get("is_summable"))) for c in metadata if c.get("column_name")]
    except Exception:
        pass
    try:
        return [(c["name"], False) for c in service.get_table_info(table_name) if c.get("name")]
    except Exception:
        return []


def build_date_instructions(service: "SchemaService", table_name: str, scope_columns=None) -> str:
    """How to filter time in THIS table, in its own column names.

    Every context used to be told "ใช้ YEAR และ MONTH" whatever its columns were — a constant left
    over from the days of one revenue view. feed_ebt has only `time_key`, feed_expense has
    `time_key` / `year_ce` / `month_no`, pl_costtype has `report_year` / `report_month`: none of
    them has a YEAR or a MONTH to use (plan/archive/RESULT_F11.md §8).

    A column the context declares as its period scope counts even if its name says nothing (a
    customer may call it `fiscal_key`); a column that carries an amount never does, however it is
    named — `ebt_month` is baht for the month, not the month.
    """
    declared = []
    if scope_columns:
        try:
            mapping = json.loads(scope_columns) if isinstance(scope_columns, str) else scope_columns
            # the caller's key says what the column means; org_code → cost_center is not a period
            declared = [v for k, v in mapping.items()
                        if isinstance(v, str) and any(hint in str(k).lower() for hint in _TIME_HINTS)]
        except (TypeError, ValueError):
            declared = []

    found = [c for c, is_measure in _table_columns(service, table_name)
             if not is_measure and (c in declared or is_time_column(c))]
    found += [c for c in declared if c not in found]  # declared but absent here: the caller still filters on it

    thai_year = "ถ้าผู้ใช้ถามเป็นปี พ.ศ. ให้แปลงเป็น ค.ศ. ก่อน (พ.ศ. − 543) เว้นแต่คอลัมน์นั้นเก็บ พ.ศ. อยู่แล้ว"
    if not found:
        return f"## Date Handling\n{thai_year}"
    return ("## Date Handling\n"
            f"คอลัมน์เวลาของตาราง {table_name}: {', '.join(found)} — ใช้คอลัมน์เหล่านี้ในการกรอง/จัดกลุ่มเวลาเท่านั้น "
            f"(CAST เป็น INTEGER เมื่อเทียบกับตัวเลข) ห้ามอ้างคอลัมน์เวลาชื่ออื่นที่ไม่ได้อยู่ในรายการนี้\n"
            f"{thai_year}")
