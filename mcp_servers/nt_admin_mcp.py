"""
NT Admin MCP Server
====================
Exposes admin tools as MCP tools for Claude Desktop/Claude Code.
Delegates all logic to app/tools/admin/ — same code as Admin Agent.

Usage:
    # Stdio (local):
    python mcp_servers/nt_admin_mcp.py

    # Or via Claude Desktop mcp_config.json:
    { "command": "python", "args": ["mcp_servers/nt_admin_mcp.py"] }
"""

import json
import os
import sys
from typing import Dict, Any, Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    name="NT Admin Server",
    instructions="Admin tools for NT AI Assistant configuration management. "
    "Search and manage semantic mappings, business rules, golden examples, "
    "hierarchy data, and run context onboarding."
)

# ── DB Session Helper ─────────────────────────────────────

_db_session = None


def _get_db():
    """Get a SQLAlchemy session for admin operations (config DB).

    Admin tools query config tables (schema_contexts, mappings, rules, etc.)
    which live in config.db, NOT app.db or business DB.
    """
    global _db_session
    if _db_session is None:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        # Priority: CONFIG_DB_URL > DATABASE_URL > hardcoded fallback
        db_url = os.environ.get("CONFIG_DB_URL", "")
        if not db_url:
            db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_file = os.path.join(project_root, "config.db")
            db_url = f"sqlite:///{db_file}"

        engine = create_engine(db_url)
        _db_session = Session(engine)

    return _db_session


# ── MCP Tool Wrappers ─────────────────────────────────────

@mcp.tool()
async def search_mappings(keyword: str = "", column_name: str = "", keyword_type: str = "", context_name: str = "") -> str:
    """ค้นหา semantic mapping ตาม keyword, column, type, หรือ context"""
    from app.tools.admin.mapping_tools import SearchMappingsTool
    tool = SearchMappingsTool()
    params = {k: v for k, v in {"keyword": keyword, "column_name": column_name, "keyword_type": keyword_type, "context_name": context_name}.items() if v}
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def add_mapping(keyword: str, target_column: str, target_value: str, keyword_type: str = "value_alias", context_name: str = "") -> str:
    """เพิ่ม semantic mapping ใหม่ (keyword → column = value)"""
    from app.tools.admin.mapping_tools import AddMappingTool
    tool = AddMappingTool()
    params = {"keyword": keyword, "target_column": target_column, "target_value": target_value, "keyword_type": keyword_type}
    if context_name:
        params["context_name"] = context_name
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def search_rules(search_text: str = "", severity: str = "", is_active: bool = True) -> str:
    """ค้นหา business rules ตาม code, คำอธิบาย, หรือ severity"""
    from app.tools.admin.rule_tools import SearchRulesTool
    tool = SearchRulesTool()
    params = {k: v for k, v in {"search_text": search_text, "severity": severity, "is_active": is_active}.items() if v != ""}
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def add_rule(rule_code: str, description: str, rule_category: str, severity: str = "warning") -> str:
    """เพิ่ม business rule ใหม่"""
    from app.tools.admin.rule_tools import AddRuleTool
    tool = AddRuleTool()
    result = await tool.execute({"rule_code": rule_code, "description": description, "rule_category": rule_category, "severity": severity}, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def search_examples(search_text: str = "", context_name: str = "") -> str:
    """ค้นหา golden examples ตาม keyword ในคำถามหรือ SQL"""
    from app.tools.admin.example_tools import SearchExamplesTool
    tool = SearchExamplesTool()
    params = {k: v for k, v in {"search_text": search_text, "context_name": context_name}.items() if v}
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def add_example(question: str, sql: str, context_name: str = "") -> str:
    """เพิ่ม golden example ใหม่ (คู่คำถาม-SQL ที่ถูกต้อง)"""
    from app.tools.admin.example_tools import AddExampleTool
    tool = AddExampleTool()
    params = {"question": question, "sql": sql}
    if context_name:
        params["context_name"] = context_name
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def list_contexts() -> str:
    """แสดง data contexts ทั้งหมดที่มี"""
    from app.tools.admin.system_tools import ListContextsTool
    tool = ListContextsTool()
    result = await tool.execute({}, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def refresh_cache() -> str:
    """รีเฟรช cache ทั้งหมด (schema, rules, mappings)"""
    from app.tools.admin.system_tools import RefreshCacheTool
    tool = RefreshCacheTool()
    result = await tool.execute({}, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def search_hierarchy(keyword: str, context_name: str = "") -> str:
    """ค้นหาค่าใน master hierarchy ตาม keyword"""
    from app.tools.admin.system_tools import SearchHierarchyTool
    tool = SearchHierarchyTool()
    params = {"keyword": keyword}
    if context_name:
        params["context_name"] = context_name
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def inspect_view(view_name: str) -> str:
    """ตรวจสอบ view/table: แสดง columns, types, ข้อมูลตัวอย่าง"""
    from app.tools.admin.onboarding_tools import InspectViewTool
    tool = InspectViewTool()
    result = await tool.execute({"view_name": view_name}, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def validate_config(context_name: str) -> str:
    """ตรวจสอบความสมบูรณ์ของ config สำหรับ context"""
    from app.tools.admin.onboarding_tools import ValidateConfigTool
    tool = ValidateConfigTool()
    result = await tool.execute({"context_name": context_name}, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def analyze_query_logs(days: int = 7, context_name: str = "", errors_only: bool = False) -> str:
    """วิเคราะห์ query logs: error rates, ปัญหาที่พบบ่อย"""
    from app.tools.admin.analysis_tools import AnalyzeQueryLogsTool
    tool = AnalyzeQueryLogsTool()
    params = {"days": days, "errors_only": errors_only}
    if context_name:
        params["context_name"] = context_name
    result = await tool.execute(params, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


@mcp.tool()
async def review_feedback(days: int = 7, thumbs_down_only: bool = True, limit: int = 20) -> str:
    """ดู feedback จากผู้ใช้ พร้อมรายละเอียด"""
    from app.tools.admin.analysis_tools import ReviewFeedbackTool
    tool = ReviewFeedbackTool()
    result = await tool.execute({"days": days, "thumbs_down_only": thumbs_down_only, "limit": limit}, _get_db())
    return json.dumps(result, ensure_ascii=False, default=str)


# ── Main ──────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
