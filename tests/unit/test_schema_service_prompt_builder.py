from types import MethodType

from sqlalchemy import create_engine

from app.services.schema_service import SchemaService


def _create_prompt_service():
    engine = create_engine("sqlite:///:memory:")
    service = SchemaService(db_engine=engine, business_engine=engine)

    service.get_context_info = MethodType(
        lambda self, context_name: {
            "name": context_name,
            "display_name": "Revenue",
            "main_view": "revenue_search",
            "instruction_th": "ห้าม hardcode ชื่อหน่วยงาน",
            "instruction_en": "Do not hardcode organization names",
        },
        service,
    )
    service.get_schema_metadata = MethodType(
        lambda self, table_name: [
            {
                "column_name": "YEAR",
                "data_type": "INTEGER",
                "display_name_th": "ปี",
                "is_summable": False,
                "is_groupable": True,
                "special_notes": "",
                "conversion_sql": None,
            },
            {
                "column_name": "REVENUE_VALUE",
                "data_type": "REAL",
                "display_name_th": "รายได้",
                "is_summable": True,
                "is_groupable": False,
                "special_notes": "หน่วยบาท",
                "conversion_sql": None,
            },
        ],
        service,
    )
    service.get_business_rules = MethodType(
        lambda self, table_name, inject_mode=None: [
            {
                "rule_name": "Use YEAR MONTH",
                "rule_description": "ใช้ YEAR และ MONTH แทน DATE",
                "severity": "warning",
                "example_correct": "SELECT * FROM revenue_search WHERE YEAR = 2025",
                "example_wrong": "SELECT * FROM revenue_search WHERE DATE = '2025-01-01'",
            }
        ] if inject_mode == "schema_context" else [
            {"rule_description": "รักษา context เดิมเมื่อเป็นคำถามต่อเนื่อง"}
        ],
        service,
    )
    service.get_semantic_mappings = MethodType(
        lambda self, context_name=None: [
            {
                "keyword_type": "term",
                "keyword": "บรอดแบนด์",
                "target_column": "SERVICE_GROUP",
                "target_condition": "LIKE '%Broadband%'",
                "description": "บริการบรอดแบนด์",
            },
            {
                "keyword_type": "synonym",
                "keyword": "trunk radio",
                "full_condition": "UPPER(product_name) LIKE '%TRUNK%'",
                "description": "Trunked radio service",
            },
        ],
        service,
    )
    service.get_sample_values = MethodType(
        lambda self, table_name: {
            "DATA_RANGE": {"min_year": 2024, "min_month": 1, "max_year": 2025, "max_month": 12},
            "PRODUCT_NAME": ["Trunk Radio", "Cloud Connect"],
        },
        service,
    )
    service.get_date_format = MethodType(lambda self, table_name="revenue_search": "unix_timestamp_ms", service)
    service.build_hierarchy_rule_text = MethodType(
        lambda self, context_name: "STEP 1.5: HIERARCHY RULE (ห้าม OR ข้ามระดับ)",
        service,
    )
    service.build_instruction_rules_text = MethodType(
        lambda self, main_view: "## กฎการรักษาบริบท (Context Retention Rules)\nคงบริบทเดิมถ้าผู้ใช้ถามต่อ",
        service,
    )
    return service


def test_build_system_prompt_contains_instruction_and_context_sections():
    service = _create_prompt_service()

    prompt = service.build_system_prompt(context_name="revenue", ai_provider="claude", language="thai")

    assert "<system>" in prompt
    assert "บริบทปัจจุบัน: **REVENUE**" in prompt
    assert "# Context: Revenue (revenue)" in prompt
    assert "## Table: revenue_search" in prompt
    assert "## Business Rules" in prompt
    assert "<semantic_mappings>" in prompt
    assert "## Available Values" in prompt
    assert "## Current Date" in prompt


def test_get_schema_context_lite_mode_keeps_data_range_and_drops_detailed_samples():
    service = _create_prompt_service()

    context = service.get_schema_context(context_name="revenue", lite_mode=True)

    assert "**Data Range:** 2024/1 - 2025/12" in context
    assert "Detailed sample values omitted for RAG optimization" in context
    assert "- Trunk Radio" not in context
    assert "<semantic_mappings>" in context


def test_get_default_instruction_supports_english_output():
    service = _create_prompt_service()

    instruction = service.get_default_instruction(language="english", context_name="revenue")

    assert "You are an AI Assistant for analyzing NT data." in instruction
    assert "Current Context: **REVENUE** (Table: `revenue_search`)" in instruction
    assert "Do not hardcode organization names" in instruction
    assert "NO `CONCAT(a, b)` -> Use `a || b` instead" in instruction