"""
System Tools — Cache refresh, list contexts, search hierarchy
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool


class RefreshCacheTool(AdminTool):
    name = "refresh_cache"
    description = "Force refresh all cached metadata (schema, rules, mappings, hierarchy). Use after making config changes."
    description_th = "รีเฟรช cache ทั้งหมด (schema, rules, mappings, hierarchy)"
    category = "system"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        refreshed = []

        try:
            from app.services.schema_service import SchemaService
            from app.db.session import config_engine, business_engine
            schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
            schema_service.refresh_cache()
            refreshed.append("schema_service")
        except Exception as e:
            refreshed.append(f"schema_service (error: {e})")

        try:
            from app.services.warning_detector import clear_warnings_cache
            clear_warnings_cache()
            refreshed.append("warnings")
        except Exception:
            pass

        try:
            from app.services.query_classifier import clear_patterns_cache
            clear_patterns_cache()
            refreshed.append("query_patterns")
        except Exception:
            pass

        return {
            "success": True,
            "message": f"รีเฟรช cache สำเร็จ: {', '.join(refreshed)}",
            "data": {"refreshed": refreshed}
        }


class ListContextsTool(AdminTool):
    name = "list_contexts"
    description = "List all data contexts with their main_view, description. Use this when asked about contexts, views, tables, or what data is available."
    description_th = "แสดง data contexts ทั้งหมดพร้อม view/table ที่ใช้"
    category = "system"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from sqlalchemy import text
        from app.db.session import ConfigSessionLocal

        # schema_contexts is in config DB, not app DB
        config_db = ConfigSessionLocal()
        try:
            result = config_db.execute(text("SELECT * FROM schema_contexts WHERE is_active = 1 AND status = 'active' ORDER BY id"))
            rows = result.fetchall()
            columns = result.keys()
        except Exception as e:
            config_db.close()
            return {"success": False, "message": f"ดึง contexts ไม่สำเร็จ: {str(e)}", "data": []}

        context_list = []
        for row in rows:
            row_dict = dict(zip(columns, row))
            context_list.append({
                "id": row_dict.get("id"),
                "name": row_dict.get("context_name") or row_dict.get("name", ""),
                "display_name": row_dict.get("display_name_th", ""),
                "main_view": row_dict.get("main_view"),
                "description": row_dict.get("description"),
                "is_active": row_dict.get("is_active", True),
            })

        return {
            "success": True,
            "message": f"มี {len(context_list)} contexts",
            "data": context_list,
            "total": len(context_list),
        }


class SearchHierarchyTool(AdminTool):
    name = "search_hierarchy"
    description = "Search master hierarchy values by keyword. Finds mapped values across all hierarchy levels."
    description_th = "ค้นหาค่าใน master hierarchy ตาม keyword"
    category = "system"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword (partial match in value or aliases)"
                },
                "context_name": {
                    "type": "string",
                    "description": "Filter by context name"
                },
                "level_name": {
                    "type": "string",
                    "description": "Filter by hierarchy level name"
                }
            },
            "required": ["keyword"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        try:
            from app.services.hierarchy_service import HierarchyService
            service = HierarchyService()
            # No context given = every hierarchy context; search_aliases applies each source's llm_data_policy
            contexts = [params["context_name"]] if params.get("context_name") else [
                c["context_name"] for c in service.list_contexts()]
            results = [r for c in contexts for r in service.search_aliases(c, params["keyword"], limit=30)]
            if params.get("level_name"):
                results = [r for r in results if r.get("level_label_th") == params["level_name"]]

            matches = []
            for r in results[:30]:
                matches.append({
                    "value": r.get("value", ""),
                    "column": r.get("column_name", ""),
                    "matched_alias": r.get("matched_alias", ""),
                    "level": r.get("level_label_th", ""),
                    "context": r.get("context_name", ""),
                    "parent_chain": r.get("parent_chain", []),
                })

            return {
                "success": True,
                "message": f"พบ {len(matches)} รายการที่ตรงกับ '{params['keyword']}'",
                "data": matches,
                "total": len(matches),
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"ค้นหาไม่สำเร็จ: {str(e)}",
                "data": []
            }
