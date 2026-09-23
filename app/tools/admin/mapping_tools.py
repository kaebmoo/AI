"""
Mapping Tools — Search & Add semantic mappings
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool
from app.core.time_utils import utcnow
from app.services.provenance import ACTIVE, MANUAL


class SearchMappingsTool(AdminTool):
    name = "search_mappings"
    description = "Search semantic mappings by keyword, column, or type. Use to find existing mappings before adding new ones."
    description_th = "ค้นหา semantic mapping ตาม keyword, column, หรือ type"
    category = "mapping"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Search keyword (partial match)"
                },
                "column_name": {
                    "type": "string",
                    "description": "Filter by target column name"
                },
                "keyword_type": {
                    "type": "string",
                    "description": "Filter by type: value_alias, column_alias, filter_keyword",
                    "enum": ["value_alias", "column_alias", "filter_keyword"]
                },
                "context_name": {
                    "type": "string",
                    "description": "Filter by context name (e.g., 'revenue', 'expense')"
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.schema_models import SchemaSemanticMapping

        query = db.query(SchemaSemanticMapping).filter(  # knowledge in use only (Plan 8.1)
            SchemaSemanticMapping.is_active == True, SchemaSemanticMapping.status == "active"
        )

        keyword = params.get("keyword")
        if keyword:
            query = query.filter(
                SchemaSemanticMapping.keyword.ilike(f"%{keyword}%")
            )

        if params.get("column_name"):
            query = query.filter(
                SchemaSemanticMapping.target_column == params["column_name"]
            )

        if params.get("keyword_type"):
            query = query.filter(
                SchemaSemanticMapping.keyword_type == params["keyword_type"]
            )

        if params.get("context_name"):
            query = query.filter(
                SchemaSemanticMapping.context_name == params["context_name"]
            )

        results = query.order_by(SchemaSemanticMapping.keyword).limit(50).all()

        mappings = [
            {
                "id": m.id,
                "keyword": m.keyword,
                "target_column": m.target_column,
                "target_condition": m.target_condition,
                "keyword_type": m.keyword_type,
                "context_name": m.context_name,
                "is_active": m.is_active,
            }
            for m in results
        ]

        return {
            "success": True,
            "message": f"พบ {len(mappings)} mappings",
            "data": mappings,
            "total": len(mappings),
        }


class AddMappingTool(AdminTool):
    name = "add_mapping"
    description = "Add a new semantic mapping. ALWAYS search first to check for duplicates."
    description_th = "เพิ่ม semantic mapping ใหม่ (ต้อง search ก่อนเสมอ)"
    category = "mapping"
    requires_confirmation = True

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "keyword": {
                    "type": "string",
                    "description": "Thai keyword to map (e.g., 'ดาต้าคอม')"
                },
                "target_column": {
                    "type": "string",
                    "description": "Target column name (e.g., 'SERVICE_GROUP')"
                },
                "target_value": {
                    "type": "string",
                    "description": "Target value to match (e.g., 'Datacom')"
                },
                "keyword_type": {
                    "type": "string",
                    "description": "Type: value_alias, column_alias, or filter_keyword",
                    "enum": ["value_alias", "column_alias", "filter_keyword"],
                    "default": "value_alias"
                },
                "context_name": {
                    "type": "string",
                    "description": "Context name (e.g., 'revenue'). Leave empty for all contexts."
                }
            },
            "required": ["keyword", "target_column", "target_value"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.schema_models import SchemaSemanticMapping
        from datetime import datetime

        # Check for duplicates using DedupEngine (case-insensitive + conflict detection)
        try:
            from app.services.dedup_engine import DedupEngine
            dedup = DedupEngine(db)
            dedup_result = dedup.check_mapping_duplicate(
                keyword=params["keyword"],
                target_column=params["target_column"],
            )
            if dedup_result.has_duplicate:
                return {
                    "success": False,
                    "message": f"พบ duplicate ({dedup_result.duplicate_type}): keyword '{params['keyword']}' → {params['target_column']} (existing id={dedup_result.existing_id})",
                    "data": {
                        "duplicate_type": dedup_result.duplicate_type,
                        "existing_id": dedup_result.existing_id,
                    }
                }
        except Exception:
            # Fallback: basic exact-match check
            existing = db.query(SchemaSemanticMapping).filter(
                SchemaSemanticMapping.keyword == params["keyword"],
                SchemaSemanticMapping.target_column == params["target_column"],
                SchemaSemanticMapping.is_active == True
            ).first()

            if existing:
                return {
                    "success": False,
                    "message": f"มี mapping สำหรับ keyword '{params['keyword']}' → {params['target_column']} อยู่แล้ว (id={existing.id})",
                    "data": {
                        "id": existing.id,
                        "keyword": existing.keyword,
                        "target_column": existing.target_column,
                        "target_condition": existing.target_condition,
                    }
                }

        target_value = params.get("target_value", "")
        mapping = SchemaSemanticMapping(
            keyword=params["keyword"],
            target_column=params["target_column"],
            target_condition=f"= '{target_value}'" if target_value else "",
            description=f"Mapped '{params['keyword']}' → {params['target_column']}",
            keyword_type=params.get("keyword_type", "value_alias"),
            context_name=params.get("context_name"),
            is_active=True,
            source=MANUAL,  # the admin asked for it and confirmed it
            status=ACTIVE,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(mapping)
        db.commit()
        db.refresh(mapping)

        # Invalidate cache
        try:
            from app.services.schema_service import SchemaService
            from app.db.session import config_engine, business_engine
            schema_service = SchemaService(db_engine=config_engine, business_engine=business_engine)
            schema_service.refresh_cache()
        except Exception:
            pass

        # Audit log
        try:
            from app.tools.admin.base import audit_change
            audit_change(
                action="INSERT", table_name="schema_semantic_mapping",
                record_id=mapping.id,
                new_value={"keyword": params["keyword"], "target_column": params["target_column"], "target_value": target_value},
                source="admin_agent",
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": f"เพิ่ม mapping สำเร็จ: '{params['keyword']}' → {params['target_column']}",
            "data": {"id": mapping.id, "keyword": mapping.keyword}
        }
