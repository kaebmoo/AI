import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast

from app.providers.base import ConfidenceResult, QueryResult, RetryStatus
from app.providers.chart_postprocessor import postprocess_chart_result
from app.services.ai.hierarchy_context import get_column_hierarchies
from app.services.ai.trace import new_trace, record_usage

if TYPE_CHECKING:
    from app.services.ai.service import AIService


logger = logging.getLogger(__name__)

RECOVERABLE_FLOW_EXCEPTIONS = (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError)


LIMIT_WARNING_MESSAGE = "\n\n⚠️ **คำเตือน:** ข้อมูลมีจำนวนมากและถูกจำกัดการแสดงผลที่ 1,000 รายการ อาจมีข้อมูลบางส่วนขาดหายไป กรุณาเพิ่มเงื่อนไขการค้นหา (เช่น ระบุเดือน หรือ ฝ่าย) เพื่อให้ได้ข้อมูลที่ครบถ้วนครับ"


def get_provider_model(service: "AIService") -> Optional[str]:
    return cast(Optional[str], getattr(service.provider, "model", None))


def set_provider_model(service: "AIService", model: str) -> None:
    setattr(service.provider, "model", model)


def build_history_context(history: Optional[List[Dict]]) -> str:
    if not history:
        return ""

    recent = history[-4:]
    parts = []
    for message in recent:
        role_label = "User" if message.get("role") == "user" else "Assistant"
        parts.append(f"  {role_label}: {message.get('content', '')[:200]}")

    return "\n\n**ประวัติสนทนาก่อนหน้า (ใช้เพื่อเข้าใจบริบท follow-up):**\n" + "\n".join(parts)


def _context_tables(context_table: str, config_engine=None) -> Dict[str, List[str]]:
    """{table: columns} of the file source behind a main view: the main view itself plus the tables
    its context's instruction names. Empty = legacy context / registry not migrated / config unreachable."""
    try:
        from sqlalchemy import text

        if config_engine is None:
            from app.db.session import config_engine
        with config_engine.connect() as conn:
            names = [row[0] for row in conn.execute(text(
                "SELECT st.table_name FROM schema_contexts sc JOIN source_tables st ON st.source_id = sc.source_id "
                "WHERE sc.main_view = :t AND sc.is_active = 1 AND st.is_active = 1 "
                "AND (st.table_name = :t OR instr(sc.instruction_th, st.table_name) > 0) ORDER BY st.table_name"),
                {"t": context_table})]
            tables: Dict[str, List[str]] = {name: [] for name in names}
            try:  # columns: only the unfilterable rule needs them
                for name, columns in conn.execute(text(
                        "SELECT st.table_name, st.columns FROM schema_contexts sc JOIN source_tables st "
                        "ON st.source_id = sc.source_id WHERE sc.main_view = :t AND sc.is_active = 1"), {"t": context_table}):
                    if name in tables:
                        tables[name] = [c["name"] for c in json.loads(columns or "[]")]
            except Exception:
                pass
            return tables
    except Exception:
        return {}


def table_rule(context_table: str, config_engine=None) -> str:
    """The prompt's table pin. A context is answered from its main view — plus any table of its own
    source that its instruction names (a file source whose main view is a dimensionless totals
    table sends per-division questions to the detail fact). No such table = the pin as it always was.
    """
    extra = [t for t in _context_tables(context_table, config_engine) if t != context_table]
    if not extra:
        return f"ต้องใช้ตาราง {context_table} เท่านั้น"
    return (f"ใช้ตาราง {context_table} เป็นหลัก — ใช้ {', '.join(extra)} แทนได้เฉพาะกรณีที่คำแนะนำของ context "
            f"ระบุให้ใช้ (ห้ามใช้ตารางอื่นนอกจากนี้)")


def unfilterable_columns(intent: Dict, context_table: str, config_engine=None) -> tuple[List[str], List[str]]:
    """(columns, tables): intent filter/dimension columns the main view lacks but another table of
    the context has, and those tables. A name no table has is left alone — Pass 1 often names a
    column loosely (business_unit for bu) and Pass 2 maps it. Legacy contexts: always ([], [])."""
    tables = _context_tables(context_table, config_engine)
    main_columns = {c.lower() for c in tables.get(context_table, [])}
    if not main_columns:
        return [], []
    wanted = {str(f.get("column", "")).lower() for f in intent.get("filters") or [] if isinstance(f, dict)}
    wanted |= {str(d).lower() for d in intent.get("dimensions") or []}
    others = {t: {c.lower() for c in cols} for t, cols in tables.items() if t != context_table}
    missing = sorted(c for c in wanted - main_columns if c and any(c in cols for cols in others.values()))
    return missing, [t for t, cols in others.items() if missing and set(missing) <= cols]


def unfilterable_rule(intent: Dict, context_table: str, config_engine=None) -> str:
    """Pass 2 line for those columns. Without it the model kept the main view and dropped the
    filter: one cost center was answered with the all-division total."""
    missing, fits = unfilterable_columns(intent, context_table, config_engine)
    if not missing:
        return ""
    where = f"ต้องใช้ตาราง {', '.join(fits)} ตามกฎของ context" if fits else "ไม่มีตารางเดียวที่มีครบ"
    return (f"- ⚠️ คอลัมน์ {', '.join(missing)} ไม่มีในตาราง {context_table} → {where} — **ห้ามทิ้ง filter/dimension นี้** "
            f"แล้วตอบด้วยยอดรวมของ {context_table}; ถ้ากฎของ context ไม่บอกวิธีคำนวณ ให้ตอบว่าไม่มีตัวเลขที่รับรอง ห้ามเดา\n")


def dropped_filter_error(sql_query: str, required_columns: Optional[List[str]], context_table: str) -> Optional[str]:
    """The prompt line alone did not hold (the division filter was still dropped and the total
    presented as that division's) — so the SQL is checked: every such column must appear in it."""
    dropped = [c for c in required_columns or [] if c.lower() not in sql_query.lower()]
    if not dropped:
        return None
    return (f"SQL ไม่ได้ใช้คอลัมน์ {', '.join(dropped)} ที่คำถามระบุ — ตาราง {context_table} ไม่มีคอลัมน์นี้ "
            f"ยอดรวมของตารางนี้จึงไม่ใช่คำตอบ; ใช้ตารางของ context ที่มีคอลัมน์นี้และใส่ filter/GROUP BY ให้ครบ")


def build_initial_user_prompt(
    question: str,
    context_table: str,
    context_thai: str,
    rag_context: str,
    value_lookup_text: str,
) -> str:
    return f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

{rag_context}

{value_lookup_text}

---
**ขั้นตอนที่ 1 — วิเคราะห์คำถาม (คิดก่อนเขียน SQL):**
ก่อนสร้าง SQL ให้ตอบสั้นๆ:
- ต้องการข้อมูลอะไร? (metric คืออะไร, dimension/group by คืออะไร, filter อะไร, ช่วงเวลาใด)
- ถ้ามี "Actual Values Found" ข้างต้น → ใช้ column/value จากผลค้นหาจริง
- มี semantic mapping ใดที่ตรงกับ keyword ในคำถาม?

**ขั้นตอนที่ 2 — SQL:**
สำคัญ: {table_rule(context_table)}
ถ้ามี "Actual Values Found" → ใช้ column/value จากนั้น ห้ามเดาเอง

```sql
<SQL ที่สร้างจากการวิเคราะห์ข้างต้น>
```

**ขั้นตอนที่ 3 — คำอธิบาย:**
<คำอธิบายผลลัพธ์ภาษาไทย>"""


def build_retry_user_prompt(question: str, context_table: str, context_thai: str, retry_history: List[Dict]) -> str:
    last_error = retry_history[-1] if retry_history else {}
    return f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

SQL ก่อนหน้ามีปัญหา:
```sql
{last_error.get('sql', '')}
```
Error: {last_error.get('error', '')}

---
**วิเคราะห์ข้อผิดพลาด:**
- Error นี้เกิดจากอะไร?
- ต้องแก้ไขส่วนใดของ SQL?

**SQL ที่แก้ไขแล้ว:**
สำคัญ: {table_rule(context_table)}

```sql
<SQL ที่แก้ไขแล้ว>
```

**คำอธิบาย:** <คำอธิบายภาษาไทย>"""


def resolve_context_info(context_name: str, schema_service=None):
    if schema_service is not None:
        temp_schema = schema_service
    else:
        from app.db.session import business_engine as _biz_eng
        from app.db.session import config_engine
        from app.services.schema_service import SchemaService

        temp_schema = SchemaService(db_engine=config_engine, business_engine=_biz_eng)
    context_info = temp_schema.get_context_info(context_name)
    if not context_info:
        return temp_schema, None, None

    context_table = context_info.get("main_view", context_name)
    context_thai = context_info.get("display_name", context_name)
    return temp_schema, context_table, context_thai


async def validate_sql_attempt(service: "AIService", sql_query: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        validation_result = await service.mcp_client.call_tool("validate_sql", {"sql": sql_query})

        if not validation_result:
            return None, "MCP validation returned empty result"

        validation = json.loads(validation_result) if isinstance(validation_result, str) else validation_result
        if not isinstance(validation, dict):
            return None, "Validation error: invalid validation payload"
        return validation, None
    except json.JSONDecodeError as exc:
        return None, f"Validation parse error: {str(exc)}"
    except RECOVERABLE_FLOW_EXCEPTIONS as exc:
        return None, f"Validation error: {str(exc)}"


async def execute_sql_attempt(service: "AIService", sql_query: str) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        exec_result = await service.mcp_client.call_tool("execute_query", {
            "sql": sql_query,
            "limit": 1000,
            "validate_first": False,
        })

        if not exec_result:
            return None, "MCP execution returned empty result"

        exec_data = json.loads(exec_result) if isinstance(exec_result, str) else exec_result

        # nt_query_mcp returns a dict with a "truncated" flag; legacy payloads may be a bare list
        if isinstance(exec_data, dict) and exec_data.get("truncated"):
            logger.warning("Query result truncated by row limit.")
            service.set_pending_limit_warning(LIMIT_WARNING_MESSAGE)
        elif isinstance(exec_data, list) and len(exec_data) >= 1000:
            logger.warning("Query hit the 1000 row limit.")
            service.set_pending_limit_warning(LIMIT_WARNING_MESSAGE)

        if isinstance(exec_data, list):
            exec_data = {"success": True, "data": exec_data}
        if not isinstance(exec_data, dict):
            return None, "Execution error: invalid execution payload"

        return exec_data, None
    except json.JSONDecodeError as exc:
        return None, f"Execution parse error: {str(exc)}"
    except RECOVERABLE_FLOW_EXCEPTIONS as exc:
        return None, f"Execution error: {str(exc)}"


def load_execution_metadata(temp_schema, context_table: str, context_name: str) -> tuple[Optional[Dict], Optional[List[Dict]], Optional[List[Dict]]]:
    dim_families = None
    try:
        dim_families = temp_schema.get_dimension_families(context_table)
    except RECOVERABLE_FLOW_EXCEPTIONS as df_err:
        logger.warning("Could not load dimension families: %s", df_err)

    schema_metadata = None
    hierarchy_info = None
    try:
        schema_metadata = temp_schema.get_schema_metadata(context_table)
    except RECOVERABLE_FLOW_EXCEPTIONS:
        pass
    try:
        from sqlalchemy import text as sa_text

        with temp_schema.engine.connect() as conn:
            rows = conn.execute(sa_text(
                "SELECT level_label_th, level_columns FROM master_hierarchy "
                "WHERE context_name = :ctx AND is_active = 1 ORDER BY level"
            ), {"ctx": context_name}).fetchall()
            if rows:
                hierarchy_info = [{"level_label_th": row[0], "level_columns": row[1]} for row in rows]
    except RECOVERABLE_FLOW_EXCEPTIONS:
        pass

    return dim_families, schema_metadata, hierarchy_info


async def build_explanation(
    service: "AIService",
    question: str,
    sql_query: str,
    data: List[Dict],
    cheap_model: Optional[str],
    prepare_data_for_explanation: Callable[..., List[Dict]],
    dim_families: Optional[Dict],
    hierarchy_info: Optional[List[Dict]],
    schema_metadata: Optional[List[Dict]],
    trace=None,
) -> Any:
    if not data:
        return f"ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\n{sql_query}\n```\n\nอาจเป็นเพราะ:\n- ไม่มีข้อมูลที่ตรงกับคำค้นหา\n- ชื่อคอลัมน์หรือค่าที่ใช้ค้นหาอาจไม่ถูกต้อง"

    try:
        import time

        t0 = time.perf_counter()
        try:
            explain_data = prepare_data_for_explanation(
                data,
                schema_metadata=schema_metadata,
            )
        except TypeError:
            # Keep compatibility with lightweight test/third-party services
            # that still expose the old one-argument hook.
            explain_data = prepare_data_for_explanation(data)
        simple_system_prompt = "You are a data visualization assistant. Analyze the data and provide a Thai explanation and chart recommendation."

        original_model = None
        provider_model = get_provider_model(service)
        if cheap_model and cheap_model != provider_model:
            original_model = provider_model
            set_provider_model(service, cheap_model)
            logger.info("Hybrid Mode: Explanation using cheap model '%s' (default: '%s')", cheap_model, original_model)

        try:
            explanation = await service.provider.explain_result(
                question,
                sql_query,
                explain_data,
                simple_system_prompt,
                dimension_families=dim_families,
                hierarchy_info=hierarchy_info,
                schema_metadata=schema_metadata,
            )
        except RECOVERABLE_FLOW_EXCEPTIONS as cheap_err:
            if original_model:
                logger.warning("Cheap model '%s' failed for explanation: %s. Retrying with default model '%s'...", cheap_model, cheap_err, original_model)
                set_provider_model(service, original_model)
                original_model = None
                explanation = await service.provider.explain_result(
                    question,
                    sql_query,
                    explain_data,
                    simple_system_prompt,
                    dimension_families=dim_families,
                    hierarchy_info=hierarchy_info,
                    schema_metadata=schema_metadata,
                )
            else:
                raise
        finally:
            if original_model:
                set_provider_model(service, original_model)

        # The LLM may see a reduced payload, but chart structure must always be
        # decided from the query's complete result. This runs for Claude,
        # Gemini, Matcha, and any provider implementing the same interface.
        explanation = postprocess_chart_result(
            explanation,
            data=data,
            dimension_families=dim_families,
            hierarchy_info=hierarchy_info,
            schema_metadata=schema_metadata,
        )

        t_explain = time.perf_counter() - t0
        logger.debug("Hybrid Mode: Explanation Generation took %.4fs", t_explain)
        if trace is not None:
            trace.stages["explain"] = round(t_explain, 4)
            record_usage(trace, "explain", service.provider)
        return explanation
    except RECOVERABLE_FLOW_EXCEPTIONS as explain_error:
        logger.warning("Could not get explanation: %s", explain_error)
        return f"พบข้อมูล {len(data)} รายการ"


async def build_confidence_result(
    service: "AIService",
    sql_query: str,
    question: str,
    context_name: str,
    data: List[Dict],
) -> Optional[ConfidenceResult]:
    try:
        if "nt-validation" not in service.mcp_client.servers:
            return None

        validation_summary = await service.mcp_client.call_tool(
            "get_validation_summary",
            {
                "sql": sql_query,
                "question": question,
                "context_name": context_name,
                "has_similar_example": False,
                "example_similarity": 0.0,
                "execution_success": True,
                "result_row_count": len(data),
            },
        )
        if not validation_summary:
            return None

        summary_data = json.loads(validation_summary) if isinstance(validation_summary, str) else validation_summary
        confidence = summary_data.get("confidence", {})
        return ConfidenceResult(
            score=confidence.get("score", 0),
            level=confidence.get("level", "medium"),
            level_th=confidence.get("level_th", "ปานกลาง"),
            color=confidence.get("color", "yellow"),
            factors=confidence.get("factors", []),
            recommendation=confidence.get("recommendation", ""),
        )
    except RECOVERABLE_FLOW_EXCEPTIONS as conf_error:
        logger.warning("Could not calculate confidence: %s", conf_error)
        return None


async def generate_sql_attempt(
    service: "AIService",
    user_prompt: str,
    system_prompt: str,
    history: Optional[List[Dict]],
    attempt: int,
    trace=None,
) -> tuple[Optional[str], int, Optional[str]]:
    try:
        import time

        t0 = time.perf_counter()
        native_history = history[-6:] if (attempt == 0 and history) else None
        response_text_raw = await service.provider.generate_content(user_prompt, system_prompt, history=native_history)
        response_text = response_text_raw if isinstance(response_text_raw, str) else str(response_text_raw)
        t_gen = time.perf_counter() - t0
        logger.debug("Hybrid Mode: SQL Generation took %.4fs", t_gen)

        # Real token usage from the provider (was hardcoded 500 — B9)
        usage = getattr(service.provider, "last_usage", None)
        tokens_used = usage.total if usage else 0
        if trace is not None:
            trace.stages[f"sql_gen_a{attempt}"] = round(t_gen, 4)
            record_usage(trace, "sql_gen", service.provider, attempt)
        return response_text, tokens_used, None
    except RECOVERABLE_FLOW_EXCEPTIONS as gen_error:
        logger.error("Hybrid Mode: generate_content raised exception: %s: %s", type(gen_error).__name__, gen_error)
        return None, 0, f"generate_content error: {str(gen_error)}"


async def verify_values_if_needed(
    service: "AIService",
    sql_query: str,
    question: str,
    context_name: str,
    context_table: str,
    should_verify: bool,
    log_value_corrections: Callable,
) -> Optional[str]:
    if not should_verify:
        return None

    try:
        from app.services.value_verifier import ValueVerifier

        verifier = ValueVerifier(service.mcp_client, context_table)
        verify_result = await verifier.verify(sql_query, question=question)

        if verify_result.needs_retry:
            logger.info("Value verification: %s corrections found", len(verify_result.corrections))
            for correction in verify_result.corrections:
                logger.info(
                    "  %s='%s' → %s='%s'",
                    correction.original_column,
                    correction.original_value,
                    correction.correct_column,
                    correction.correct_value,
                )

            log_value_corrections(verify_result.corrections, question, context_name)
            return verify_result.hint_text
    except RECOVERABLE_FLOW_EXCEPTIONS as exc:
        logger.warning("Value verification failed (non-blocking): %s", exc)

    return None


async def build_first_attempt_prompt(
    service: "AIService",
    question: str,
    system_prompt: str,
    history: Optional[List[Dict]],
    context_name: str,
    context_table: str,
    context_thai: str,
    two_pass_enabled: bool,
    cheap_model: Optional[str],
    detect_hierarchy_level: Callable[[str, str], Optional[Dict]],
    format_value_matches: Callable[..., str],
    get_vanna_context_string: Callable[[str], str],
    lookup_values_from_question: Callable[[str, str, str], List[Dict]],
    on_status: Optional[Callable[[RetryStatus], None]],
    attempt: int,
    max_retries: int,
    trace=None,
    conversation_id: Optional[str] = None,
    intent_state_enabled: bool = False,
    required_columns: Optional[List[str]] = None,
) -> tuple[str, bool]:
    async def _rag_task() -> str:
        try:
            import time

            t0 = time.perf_counter()
            ctx = await asyncio.to_thread(get_vanna_context_string, question)
            t_rag = time.perf_counter() - t0
            if trace is not None:
                trace.stages["rag"] = round(t_rag, 4)
            if ctx:
                logger.debug("Hybrid Mode: Injected RAG Context (%s chars) took %.4fs", len(ctx), t_rag)
            return ctx
        except RECOVERABLE_FLOW_EXCEPTIONS as exc:
            logger.warning("Failed to get RAG context: %s", exc)
            return ""

    async def _value_lookup_task(table_name: str = context_table) -> List[Dict]:
        try:
            return await asyncio.to_thread(lookup_values_from_question, question, context_name, table_name)
        except RECOVERABLE_FLOW_EXCEPTIONS as exc:
            logger.warning("Value Lookup failed: %s", exc)
            return []

    rag_context, value_matches = await asyncio.gather(_rag_task(), _value_lookup_task())
    rag_context = rag_context or ""

    value_lookup_text = ""
    detected_level = None
    hierarchy = None
    if value_matches:
        hierarchy = get_column_hierarchies().get(context_name)
        detected_level = detect_hierarchy_level(question, context_name)
        if hierarchy and detected_level:
            logger.info("Hierarchy: level %s (%s)", detected_level["level"], detected_level["label_en"])
        value_lookup_text = format_value_matches(value_matches, hierarchy=hierarchy, detected_level=detected_level)

    current_two_pass_enabled = two_pass_enabled
    user_prompt = ""
    if current_two_pass_enabled:
        logger.info("Two-Pass Mode: Starting Pass 1 (Intent Extraction)")
        if on_status:
            on_status(RetryStatus(attempt, max_retries, "analyzing", "Analyzing question (Pass 1)"))

        history_context = build_history_context(history)
        previous_intent = None
        if intent_state_enabled and history:
            from app.services.ai import intent_state
            previous_intent = intent_state.get_intent(conversation_id)
        intent_json = await extract_intent(
            service=service,
            question=question,
            system_prompt=system_prompt,
            context_name=context_name,
            context_table=context_table,
            context_thai=context_thai,
            history_context=history_context,
            rag_context=rag_context,
            cheap_model=cheap_model,
            trace=trace,
            previous_intent=previous_intent,
        )
        if intent_state_enabled and intent_json:
            from app.services.ai import intent_state
            intent_state.set_intent(conversation_id, intent_json)

        if intent_json:
            logger.info("Two-Pass Mode: Pass 1 success. Building Pass 2 prompt.")
            if required_columns is not None:
                required_columns[:] = unfilterable_columns(intent_json, context_table)[0]
            user_prompt = build_pass2_prompt(
                service=service,
                question=question,
                intent=intent_json,
                context_table=context_table,
                context_thai=context_thai,
                value_matches=value_matches if value_lookup_text else None,
                hierarchy=hierarchy,
                detected_level=detected_level,
            )
            if on_status:
                on_status(RetryStatus(attempt, max_retries, "generating", "Generating SQL (Pass 2)"))
        else:
            logger.warning("Two-Pass Mode: Pass 1 failed. Falling back to one-pass CoT prompt.")
            current_two_pass_enabled = False

    if not current_two_pass_enabled:
        user_prompt = build_initial_user_prompt(
            question=question,
            context_table=context_table,
            context_thai=context_thai,
            rag_context=rag_context,
            value_lookup_text=value_lookup_text,
        )

    return user_prompt, current_two_pass_enabled


def log_unmatched_like_patterns(sql_query: str, context_name: str, question: str) -> None:
    try:
        import threading

        extracted_like_patterns = re.findall(r"LIKE\s+'%(.+?)%'", sql_query, re.IGNORECASE)
        if not extracted_like_patterns:
            return

        def _log_unmatched(patterns: List[str]) -> None:
            try:
                from app.services.hierarchy_service import hierarchy_service

                for pattern in patterns:
                    if not hierarchy_service.search_aliases(context_name, pattern, limit=1):
                        hierarchy_service.log_unmatched_keyword(pattern, context_name, question)
            except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
                pass

        threading.Thread(target=_log_unmatched, args=(extracted_like_patterns,), daemon=True).start()
    except (AttributeError, ImportError, RuntimeError, TypeError, ValueError):
        pass


async def run_hybrid_attempt(
    service: "AIService",
    question: str,
    system_prompt: str,
    history: Optional[List[Dict]],
    on_status: Optional[Callable[[RetryStatus], None]],
    context_name: str,
    context_table: str,
    attempt: int,
    max_retries: int,
    value_verification_enabled: bool,
    cheap_model: Optional[str],
    user_prompt: str,
    temp_schema,
    retry_history: List[Dict],
    total_tokens: int,
    extract_sql: Callable[[str], Optional[str]],
    extract_explanation: Callable[[str], str],
    log_value_corrections: Callable,
    prepare_data_for_explanation: Callable[..., List[Dict]],
    start_request: float,
    trace=None,
    template_answers_enabled: bool = False,
    required_columns: Optional[List[str]] = None,
) -> tuple[Optional[QueryResult], int, Optional[str]]:
    logger.info("Hybrid Mode: Generating SQL (attempt %s)", attempt + 1)

    # F9-B: metadata for the explanation stage only depends on context (not on
    # the SQL result) — load it in parallel with generation/validation/execution.
    # Early-return paths leave the task to finish on its own (read-only, no side effects).
    metadata_task = asyncio.create_task(
        asyncio.to_thread(load_execution_metadata, temp_schema, context_table, context_name)
    )
    metadata_task.add_done_callback(lambda t: t.exception())  # never let it warn "never retrieved"

    response_text, tokens_used, generation_error = await generate_sql_attempt(
        service,
        user_prompt,
        system_prompt,
        history,
        attempt,
        trace=trace,
    )
    if generation_error:
        retry_history.append({"sql": "", "error": generation_error})
        return None, total_tokens, None

    response_text = response_text or ""
    logger.info("Hybrid Mode: Got response_text (len=%s)", len(response_text) if response_text else 0)
    total_tokens += tokens_used

    sql_query = extract_sql(response_text)
    _ = extract_explanation(response_text)

    if not sql_query:
        logger.warning("Could not extract SQL from AI response")
        retry_history.append({"sql": "", "error": "Could not extract SQL from response"})
        return None, total_tokens, None

    logger.info("Extracted SQL: %s...", sql_query[:100])
    log_unmatched_like_patterns(sql_query, context_name, question)

    dropped_error = dropped_filter_error(sql_query, required_columns, context_table)
    if dropped_error:
        logger.warning("Hybrid Mode: %s", dropped_error)
        retry_history.append({"sql": sql_query, "error": dropped_error})
        return None, total_tokens, sql_query

    if on_status:
        on_status(RetryStatus(attempt, max_retries, "validating", "Validating SQL"))

    validation, validation_error = await validate_sql_attempt(service, sql_query)
    if validation_error:
        retry_history.append({"sql": sql_query, "error": validation_error})
        return None, total_tokens, sql_query
    if validation is None:
        retry_history.append({"sql": sql_query, "error": "Validation error: invalid validation payload"})
        return None, total_tokens, sql_query

    if not validation.get("valid", False):
        issues = validation.get("issues", [])
        logger.warning("SQL validation failed: %s", issues)
        retry_history.append({"sql": sql_query, "error": f"Validation failed: {issues}"})
        return None, total_tokens, sql_query

    verification_hint = await verify_values_if_needed(
        service,
        sql_query,
        question,
        context_name,
        context_table,
        value_verification_enabled and attempt == 0,
        log_value_corrections,
    )
    if verification_hint:
        retry_history.append({"sql": sql_query, "error": verification_hint})
        return None, total_tokens, sql_query

    if on_status:
        on_status(RetryStatus(attempt, max_retries, "executing", "Executing SQL"))

    logger.info("Hybrid Mode: Executing SQL: %s", sql_query)

    try:
        import time

        t0 = time.perf_counter()
        exec_data, execution_error = await execute_sql_attempt(service, sql_query)
        t_exec = time.perf_counter() - t0
        if trace is not None:
            trace.stages[f"exec_a{attempt}"] = round(t_exec, 4)
        logger.debug("Hybrid Mode: SQL Execution in DB took %.4fs", t_exec)
        if execution_error:
            retry_history.append({"sql": sql_query, "error": execution_error})
            return None, total_tokens, sql_query
        if exec_data is None:
            retry_history.append({"sql": sql_query, "error": "Execution error: invalid execution payload"})
            return None, total_tokens, sql_query
    except RECOVERABLE_FLOW_EXCEPTIONS as exc:
        retry_history.append({"sql": sql_query, "error": f"Execution error: {str(exc)}"})
        return None, total_tokens, sql_query

    if not exec_data.get("success", False):
        error_msg = exec_data.get("error", "Unknown execution error")
        logger.warning("SQL execution failed: %s", error_msg)
        retry_history.append({"sql": sql_query, "error": f"Execution failed: {error_msg}"})
        return None, total_tokens, sql_query

    full_data = exec_data.get("data", [])
    logger.info("Hybrid Mode: Success! Got %s rows", len(full_data))

    dim_families, schema_metadata, hierarchy_info = await metadata_task

    if not full_data:
        explanation = f"ไม่พบข้อมูลที่ตรงกับเงื่อนไข\n\nSQL ที่ใช้:\n```sql\n{sql_query}\n```\n\nอาจเป็นเพราะ:\n- ไม่มีข้อมูลที่ตรงกับคำค้นหา\n- ชื่อคอลัมน์หรือค่าที่ใช้ค้นหาอาจไม่ถูกต้อง"
    else:
        explanation = None
        if template_answers_enabled:
            from app.services.ai.template_answer import build_template_answer
            explanation = build_template_answer(question, sql_query, full_data)
            if explanation is not None:
                logger.info("Hybrid Mode: explanation from template (no LLM call)")
                if trace is not None:
                    trace.stages["explain_mode"] = "template"
        if explanation is None:
            if trace is not None:
                trace.stages["explain_mode"] = "llm"
            explanation = await build_explanation(
                service,
                question,
                sql_query,
                full_data,
                cheap_model,
                prepare_data_for_explanation,
                dim_families,
                hierarchy_info,
                schema_metadata,
                trace=trace,
            )

    # Surface the row-limit warning to the user (hybrid mode reader — mcp mode reads it in retry_loop)
    pending = service.get_pending_limit_warning()
    if pending:
        if isinstance(explanation, dict):
            explanation["explanation"] = (explanation.get("explanation") or "") + pending
        else:
            explanation = (explanation or "") + pending
        service.set_pending_limit_warning("")

    confidence_result = await build_confidence_result(
        service,
        sql_query,
        question,
        context_name,
        full_data,
    )

    import time

    t_total = time.perf_counter() - start_request
    logger.debug("Hybrid Mode: Total Request Time: %.4fs", t_total)

    # Real total across all stages (intent + sql_gen attempts + explain)
    if trace is not None and trace.usage:
        total_tokens = sum(u["input_tokens"] + u["output_tokens"] for u in trace.usage)

    return QueryResult(
        question=question,
        sql_query=sql_query,
        data=full_data,
        explanation=explanation,
        tokens_used=total_tokens,
        provider=service.provider_name,
        retry_count=attempt,
        retry_history=retry_history if retry_history else None,
        confidence=confidence_result,
        usage_breakdown=trace.usage if trace is not None and trace.usage else None,
    ), total_tokens, sql_query


async def query_hybrid(
    service: "AIService",
    question: str,
    system_prompt: str,
    max_retries: int = 2,
    history: Optional[List[Dict]] = None,
    on_status: Optional[Callable[[RetryStatus], None]] = None,
    context_name: str = "revenue",
    two_pass_enabled: bool = False,
    value_lookup_enabled: bool = False,
    value_verification_enabled: bool = True,
    cheap_model: Optional[str] = None,
    schema_service=None,
    trace=None,
    template_answers_enabled: bool = False,
    conversation_id: Optional[str] = None,
    intent_state_enabled: bool = False,
    escalation_ladder_enabled: bool = False,
    escalation_tool_loop_enabled: bool = False,
    latency_budget_s: float = 45.0,
    **kwargs,
) -> QueryResult:
    del value_lookup_enabled, kwargs

    # Trace is normally created by QueryEngine (which also emits it);
    # standalone callers get a local one so stage recording never crashes
    trace = trace or new_trace(question)

    import time

    # Clear stale warning state from instance reuse
    service.set_pending_limit_warning("")

    start_request = time.perf_counter()
    sql_query = None
    total_tokens = 0
    retry_history = []
    required_columns: List[str] = []  # filled by Pass 1: columns the SQL must use (dropped_filter_error)
    get_vanna_context_string = service.get_vanna_context_string
    lookup_values_from_question = service.lookup_values_from_question
    detect_hierarchy_level = service.detect_hierarchy_level
    format_value_matches = service.format_value_matches
    extract_sql = service.extract_sql
    extract_explanation = service.extract_explanation
    log_value_corrections = service.log_value_corrections
    prepare_data_for_explanation = service.prepare_data_for_explanation

    if not service.mcp_client.servers:
        logger.error("Hybrid Mode: MCP client has no connected servers!")
        return QueryResult(
            question=question,
            sql_query="",
            data=[],
            explanation="ระบบ MCP ไม่ได้เชื่อมต่อ กรุณาลองใหม่อีกครั้ง",
            tokens_used=0,
            provider=service.provider_name,
            error="MCP client not connected",
        )

    logger.info("Hybrid Mode: MCP connected to %s", list(service.mcp_client.servers.keys()))

    # Context does not change across retries — resolve once, outside the loop
    try:
        temp_schema, context_table, context_thai = resolve_context_info(context_name, schema_service=schema_service)
        if context_table and context_thai:
            logger.info("Hybrid Mode: Using context '%s' -> table '%s', display '%s'", context_name, context_table, context_thai)
        else:
            logger.error("Hybrid Mode: Context '%s' not found in schema_contexts table", context_name)
            return QueryResult(
                question=question,
                sql_query="",
                data=[],
                explanation=f"ไม่พบการตั้งค่า context '{context_name}' ในระบบ กรุณาตั้งค่าผ่าน Admin UI",
                tokens_used=0,
                provider=service.provider_name,
                error=f"Context '{context_name}' not configured",
            )
    except RECOVERABLE_FLOW_EXCEPTIONS as exc:
        logger.error("Failed to get context info: %s", exc)
        return QueryResult(
            question=question,
            sql_query="",
            data=[],
            explanation=f"เกิดข้อผิดพลาดในการโหลดข้อมูล context: {exc}",
            tokens_used=0,
            provider=service.provider_name,
            error=str(exc),
        )

    budget_exceeded = False
    for attempt in range(max_retries + 1):
        # F9-D: latency budget — don't start another attempt past the budget
        if attempt > 0 and (time.perf_counter() - start_request) > latency_budget_s:
            logger.warning("Hybrid Mode: latency budget %.0fs exceeded — stopping retries", latency_budget_s)
            budget_exceeded = True
            break

        # F9-D: attempt 2+ escalates to the strong tier of the same provider
        if escalation_ladder_enabled and attempt == 1:
            strong_model = service.provider.get_model("strong")
            if strong_model and strong_model != get_provider_model(service):
                logger.info("Hybrid Mode: escalating to strong model '%s'", strong_model)
                set_provider_model(service, strong_model)
                if trace is not None:
                    trace.stages["escalated_to"] = strong_model

        # Don't carry a truncation warning from a failed attempt into the next one
        service.set_pending_limit_warning("")
        if on_status:
            on_status(RetryStatus(attempt, max_retries, "generating", f"Generating SQL (attempt {attempt + 1})"))

        if history:
            logger.info("Hybrid Mode: Using native conversation history (%s messages)", len(history))

        user_prompt = ""

        if attempt == 0:
            user_prompt, two_pass_enabled = await build_first_attempt_prompt(
                service=service,
                question=question,
                system_prompt=system_prompt,
                history=history,
                context_name=context_name,
                context_table=context_table,
                context_thai=context_thai,
                two_pass_enabled=two_pass_enabled,
                cheap_model=cheap_model,
                detect_hierarchy_level=detect_hierarchy_level,
                format_value_matches=format_value_matches,
                get_vanna_context_string=get_vanna_context_string,
                lookup_values_from_question=lookup_values_from_question,
                on_status=on_status,
                attempt=attempt,
                max_retries=max_retries,
                trace=trace,
                conversation_id=conversation_id,
                intent_state_enabled=intent_state_enabled,
                required_columns=required_columns,
            )
        else:
            user_prompt = build_retry_user_prompt(
                question=question,
                context_table=context_table,
                context_thai=context_thai,
                retry_history=retry_history,
            )

        try:
            attempt_result, total_tokens, sql_query = await run_hybrid_attempt(
                service=service,
                question=question,
                system_prompt=system_prompt,
                history=history,
                on_status=on_status,
                context_name=context_name,
                context_table=context_table,
                attempt=attempt,
                max_retries=max_retries,
                value_verification_enabled=value_verification_enabled,
                cheap_model=cheap_model,
                user_prompt=user_prompt,
                temp_schema=temp_schema,
                template_answers_enabled=template_answers_enabled,
                retry_history=retry_history,
                total_tokens=total_tokens,
                extract_sql=extract_sql,
                extract_explanation=extract_explanation,
                log_value_corrections=log_value_corrections,
                prepare_data_for_explanation=prepare_data_for_explanation,
                start_request=start_request,
                trace=trace,
                required_columns=required_columns,
            )
            trace.attempts = attempt + 1
            if attempt_result:
                return attempt_result

        except RECOVERABLE_FLOW_EXCEPTIONS as exc:
            logger.error("Hybrid Mode error: %s", exc)
            retry_history.append({"sql": sql_query or "", "error": str(exc)})

    # F9-D attempt 3: rescue via read-only tool loop (mcp mode) — same tools,
    # same read-only permissions; only when explicitly enabled and within budget
    if (
        escalation_tool_loop_enabled
        and not budget_exceeded
        and (time.perf_counter() - start_request) <= latency_budget_s
    ):
        logger.info("Hybrid Mode: escalating to tool loop (mcp mode rescue)")
        if trace is not None:
            trace.stages["escalated_to"] = "tool_loop"
        try:
            from app.services.ai.retry_loop import query_with_retry
            return await query_with_retry(service, question, history=history, on_status=on_status)
        except RECOVERABLE_FLOW_EXCEPTIONS as exc:
            logger.error("Hybrid Mode: tool loop rescue failed: %s", exc)

    if trace.usage:
        total_tokens = sum(u["input_tokens"] + u["output_tokens"] for u in trace.usage)

    if budget_exceeded:
        error_msg = f"เกินเวลาที่กำหนด ({latency_budget_s:.0f} วินาที) — กรุณาลองใหม่หรือปรับคำถามให้เฉพาะเจาะจงขึ้น"
    else:
        error_msg = f"ไม่สามารถสร้าง SQL ที่ถูกต้องได้หลังจากลอง {max_retries + 1} ครั้ง"

    return QueryResult(
        question=question,
        sql_query=sql_query or "",
        data=[],
        explanation=error_msg,
        tokens_used=total_tokens,
        provider=service.provider_name,
        error="Latency budget exceeded" if budget_exceeded else "Max retries exceeded",
        retry_count=max_retries + 1,
        retry_history=retry_history,
        usage_breakdown=trace.usage or None,
    )


INTENT_SCHEMA = {
    "type": "object",
    "properties": {
        "intent_type": {"type": "string", "enum": ["aggregation", "comparison", "trend", "detail", "ranking", "lookup"]},
        "metrics": {"type": "array", "items": {"type": "string"}},
        "aggregate_function": {"type": "string", "enum": ["SUM", "COUNT", "AVG", "MIN", "MAX"]},
        "dimensions": {"type": "array", "items": {"type": "string"}},
        "filters": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "column": {"type": "string"},
                    "operator": {"type": "string", "enum": ["=", "LIKE", ">", "<", ">=", "<=", "IN", "BETWEEN"]},
                    "value": {},
                },
                "required": ["column", "operator", "value"],
            },
        },
        "time_range": {
            "type": ["object", "null"],
            "properties": {"year": {"type": ["integer", "null"]}, "month": {"type": ["integer", "null"]}},
        },
        "ordering": {
            "type": ["object", "null"],
            "properties": {"column": {"type": "string"}, "direction": {"type": "string", "enum": ["ASC", "DESC"]}},
        },
        "limit": {"type": ["integer", "null"]},
        "matched_mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"keyword": {"type": "string"}, "sql_condition": {"type": "string"}},
                "required": ["keyword", "sql_condition"],
            },
        },
    },
    "required": ["intent_type", "metrics", "filters"],
}


def _intent_rules() -> str:
    return """**กฎสำคัญ:**
1. ตรวจสอบ semantic mappings ใน system prompt ก่อน -- ถ้ามี keyword ที่ตรง ให้ใส่ใน matched_mappings พร้อม sql_condition ที่คัดลอกมาจาก mapping
2. ถ้า User ระบุปี พ.ศ. ให้แปลงเป็น ค.ศ. (พ.ศ. - 543) ใส่ใน time_range.year
3. ถ้าไม่แน่ใจค่า filter ให้ใช้ LIKE operator
4. **Follow-up context**: ถ้ามีประวัติสนทนาก่อนหน้า ให้ใช้เป็นบริบท เช่น ถ้าถามก่อนหน้าเรื่อง "ค่าล่วงเวลา" แล้วถาม "ค่าเฉลี่ยเท่าไหร่" → ต้อง inherit filter "ค่าล่วงเวลา" จากคำถามก่อนหน้าด้วย
5. ห้ามสร้าง SQL -- ระบุเฉพาะ intent เท่านั้น"""


async def extract_intent(
    service: "AIService",
    question: str,
    system_prompt: str,
    context_name: str,
    context_table: str,
    context_thai: str,
    history_context: str,
    rag_context: str,
    cheap_model: Optional[str] = None,
    trace=None,
    previous_intent: Optional[Dict] = None,
) -> Optional[Dict]:
    del context_name

    if previous_intent is not None:
        # F9-C: follow-up — update the stored intent instead of re-deriving
        # from raw history (much shorter prompt, deterministic inheritance)
        prompt_header = f"""Intent เดิมของบทสนทนานี้:
{json.dumps(previous_intent, ensure_ascii=False)}

คำถามใหม่ (follow-up): {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

---
**Task:** อัปเดต intent เดิมตามคำถามใหม่ — คงค่า filter/dimension ที่ไม่ถูกกล่าวถึงไว้ตามเดิม (inherit) และเปลี่ยนเฉพาะส่วนที่คำถามใหม่ระบุ

{_intent_rules()}"""
    else:
        prompt_header = f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table}){history_context}

{rag_context}

---
**Task:** วิเคราะห์คำถามข้างต้นและระบุ intent

{_intent_rules()}"""

    # Text fallback prompt — schema spelled out for parse_intent_json
    intent_prompt = f"""{prompt_header}

ส่งคืน JSON ที่มีโครงสร้างตามนี้เท่านั้น ห้ามมี text อื่นนอก JSON:

```json
{{
  "intent_type": "aggregation | comparison | trend | detail | ranking | lookup",
  "metrics": ["column_name_to_aggregate"],
  "aggregate_function": "SUM | COUNT | AVG | MIN | MAX",
  "dimensions": ["column_for_group_by"],
  "filters": [
    {{"column": "col_name", "operator": "= | LIKE | > | < | >= | <= | IN | BETWEEN", "value": "value_or_pattern"}}
  ],
  "time_range": {{"year": 2025, "month": null}},
  "ordering": {{"column": "col_name_or_alias", "direction": "ASC | DESC"}},
  "limit": null,
  "matched_mappings": [
    {{"keyword": "user_keyword", "sql_condition": "COLUMN operator 'value'"}}
  ]
}}
```
ตอบเป็น JSON เท่านั้น ห้ามมีข้อความอื่น"""

    try:
        import time

        t0 = time.perf_counter()
        original_model = None
        provider_model = get_provider_model(service)
        if cheap_model and cheap_model != provider_model:
            original_model = provider_model
            set_provider_model(service, cheap_model)
            logger.info("Two-Pass: Intent using cheap model '%s' (default: '%s')", cheap_model, original_model)

        async def _extract_once() -> tuple[Optional[Dict], str]:
            # Structured output first — provider enforces the schema
            structured = await service.provider.generate_structured(
                prompt_header, INTENT_SCHEMA, system_prompt, schema_name="intent"
            )
            if structured is not None:
                return structured, "structured"
            # Fallback: text generation + regex/JSON parse (original path)
            response_text = await service.provider.generate_content(intent_prompt, system_prompt)
            return service.parse_intent_json(response_text), "fallback_text"

        try:
            intent_json, intent_source = await _extract_once()
        except RECOVERABLE_FLOW_EXCEPTIONS as cheap_err:
            if original_model:
                logger.warning("Cheap model '%s' failed for intent: %s. Retrying with default model '%s'...", cheap_model, cheap_err, original_model)
                set_provider_model(service, original_model)
                original_model = None
                intent_json, intent_source = await _extract_once()
            else:
                raise
        finally:
            if original_model:
                set_provider_model(service, original_model)

        t_intent = time.perf_counter() - t0
        if trace is not None:
            trace.stages["intent"] = round(t_intent, 4)
            trace.stages["intent_source"] = intent_source
            record_usage(trace, "intent", service.provider)

        if intent_json:
            logger.info("Two-Pass: Pass 1 complete (%.2fs, %s). Intent: %s", t_intent, intent_source, json.dumps(intent_json, ensure_ascii=False)[:500])
            return intent_json

        logger.warning("Two-Pass: Failed to parse intent JSON (%.2fs, %s).", t_intent, intent_source)
        return None

    except RECOVERABLE_FLOW_EXCEPTIONS as exc:
        logger.error("Two-Pass: Intent extraction failed: %s: %s", type(exc).__name__, exc)
        return None


def build_pass2_prompt(
    service: "AIService",
    question: str,
    intent: Dict,
    context_table: str,
    context_thai: str,
    value_matches: Optional[List[Dict]] = None,
    hierarchy: Optional[List[Dict]] = None,
    detected_level: Optional[Dict] = None,
) -> str:
    intent_dimensions = {dimension.lower() for dimension in intent.get("dimensions", [])}

    filters_text = "  ไม่มี filter"
    if intent.get("filters"):
        lines = [f"  - {item['column']} {item['operator']} {item['value']}" for item in intent["filters"]]
        filters_text = "\n".join(lines)

    mappings_text = "  ไม่พบ mapping ที่ตรง"
    if intent.get("matched_mappings"):
        lines = [f"  - keyword '{mapping.get('keyword')}' → {mapping.get('sql_condition')}" for mapping in intent["matched_mappings"]]
        mappings_text = "\n".join(lines)

    dimensions = intent.get("dimensions", [])
    dimensions_text = ", ".join(dimensions) if dimensions else "ไม่มี (ไม่ต้อง GROUP BY)"

    time_text = "ไม่ระบุ"
    time_range = intent.get("time_range")
    if time_range:
        parts = []
        if time_range.get("year"):
            parts.append(f"ปี ค.ศ. {time_range['year']} (พ.ศ. {time_range['year'] + 543})")
        if time_range.get("month"):
            parts.append(f"เดือน {time_range['month']}")
        if parts:
            time_text = ", ".join(parts)

    ordering_text = "ไม่ระบุ"
    if intent.get("ordering"):
        ordering = intent["ordering"]
        ordering_text = f"{ordering.get('column', '?')} {ordering.get('direction', 'DESC')}"

    filtered_value_matches = None
    if value_matches:
        intent_filter_columns = {item["column"].lower() for item in intent.get("filters", [])}
        filtered_value_matches = [
            match for match in value_matches
            if match["column_name"].lower() not in intent_dimensions and match["column_name"].lower() in intent_filter_columns
        ]
        if not filtered_value_matches:
            filtered_value_matches = None

    value_matches_text = ""
    if filtered_value_matches:
        value_matches_text = service.format_value_matches(filtered_value_matches, hierarchy=hierarchy, detected_level=detected_level)

    return f"""คำถาม: {question}

**บริบท:** ข้อมูล{context_thai} (ใช้ตาราง {context_table})

---
**Structured Intent (วิเคราะห์จากคำถามแล้ว):**
- Intent Type: {intent.get('intent_type', 'aggregation')}
- Metrics: {intent.get('aggregate_function', 'SUM')}({', '.join(intent.get('metrics', ['REVENUE_VALUE']))})
- Dimensions (GROUP BY): {dimensions_text}
- Filters:
{filters_text}
- Time Range: {time_text}
- Matched Semantic Mappings:
{mappings_text}
- Ordering: {ordering_text}
- Limit: {intent.get('limit') or 'ไม่จำกัด'}

---
{value_matches_text}
**สร้าง SQL จาก Structured Intent ข้างต้น:**
สำคัญ:
- {table_rule(context_table)}
{unfilterable_rule(intent, context_table)}- **ยึดตาม Structured Intent เป็นหลัก** — Dimensions คือ GROUP BY, Filters คือ WHERE
- ห้ามเพิ่ม WHERE filter ที่ไม่อยู่ใน Filters ข้างต้น (ยกเว้น time_range)
- Dimensions (GROUP BY) columns ห้ามใช้เป็น WHERE filter
- ถ้ามี "Actual Values Found" → ใช้เป็นค่าอ้างอิงสำหรับ filter ที่ระบุไว้แล้วเท่านั้น
- ถ้ามี Matched Semantic Mappings ให้ใช้ sql_condition จาก mapping โดยตรง
- ห้าม FORMAT ตัวเลขใน SQL (ส่งค่าดิบ)
- ห้าม OR ข้ามระดับ hierarchy (เช่น service_group OR product_name)

```sql
<SQL ที่สร้างจาก Structured Intent>
```

**คำอธิบาย:**
<คำอธิบายผลลัพธ์ภาษาไทย>"""
