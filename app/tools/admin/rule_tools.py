"""
Rule Tools — Search & Add business rules
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool, duplicate
from app.core.time_utils import utcnow
from app.services.provenance import ACTIVE, MANUAL


class SearchRulesTool(AdminTool):
    name = "search_rules"
    description = "Search business rules by code, description, category, or severity."
    description_th = "ค้นหา business rules ตาม code, คำอธิบาย, หมวดหมู่, หรือระดับ"
    category = "rule"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "Search in rule_code or description"
                },
                "rule_category": {
                    "type": "string",
                    "description": "Filter by category (e.g., 'filter', 'aggregation', 'validation')"
                },
                "severity": {
                    "type": "string",
                    "description": "Filter by severity: error, warning, info",
                    "enum": ["error", "warning", "info"]
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.schema_models import SchemaBusinessRule

        # knowledge in use only (Plan 8.1): the result goes to the agent's model — a switched-off rule or a proposal
        # is not knowledge (R2-2); there is no parameter to ask for them
        query = db.query(SchemaBusinessRule).filter(SchemaBusinessRule.is_active == True,
                                                    SchemaBusinessRule.status == "active")

        search_text = params.get("search_text")
        if search_text:
            query = query.filter(
                (SchemaBusinessRule.rule_code.ilike(f"%{search_text}%")) |
                (SchemaBusinessRule.rule_description.ilike(f"%{search_text}%"))
            )

        if params.get("rule_category"):
            query = query.filter(SchemaBusinessRule.rule_category == params["rule_category"])

        if params.get("severity"):
            query = query.filter(SchemaBusinessRule.severity == params["severity"])

        results = query.order_by(SchemaBusinessRule.rule_code).limit(50).all()

        rules = [
            {
                "id": r.id,
                "rule_code": r.rule_code,
                "description": r.rule_description,
                "rule_name": r.rule_name,
                "severity": getattr(r, "severity", None),
                "is_active": r.is_active,
                "table_name": getattr(r, "table_name", None),
            }
            for r in results
        ]

        return {
            "success": True,
            "message": f"พบ {len(rules)} rules",
            "data": rules,
            "total": len(rules),
        }


class AddRuleTool(AdminTool):
    name = "add_rule"
    description = "Add a new business rule. ALWAYS search first to check for duplicate rule_code."
    description_th = "เพิ่ม business rule ใหม่ (ต้อง search ก่อนเสมอ)"
    category = "rule"
    requires_confirmation = True

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "rule_code": {
                    "type": "string",
                    "description": "Unique rule code (e.g., 'FILTER_001')"
                },
                "description": {
                    "type": "string",
                    "description": "Rule description in Thai"
                },
                "rule_category": {
                    "type": "string",
                    "description": "Category: filter, aggregation, validation, format, instruction"
                },
                "inject_mode": {
                    "type": "string",
                    "description": "How to inject: instruction (in prompt) or sql (SQL template)",
                    "enum": ["instruction", "sql"],
                    "default": "instruction"
                },
                "severity": {
                    "type": "string",
                    "description": "Severity: error, warning, info",
                    "enum": ["error", "warning", "info"],
                    "default": "warning"
                },
                "context_name": {
                    "type": "string",
                    "description": "Context name (leave empty for global rule)"
                }
            },
            "required": ["rule_code", "description", "rule_category"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.schema_models import SchemaBusinessRule
        from datetime import datetime

        # Check duplicate using DedupEngine
        try:
            from app.services.dedup_engine import DedupEngine
            dedup = DedupEngine(db)
            dedup_result = dedup.check_rule_duplicate(rule_code=params["rule_code"])
            existing = db.get(SchemaBusinessRule, dedup_result.existing_id) if dedup_result.has_duplicate else None
            if dedup_result.has_duplicate and existing is None:  # gone since the check: say only what was asked
                return {"success": False, "message": f"rule_code '{params['rule_code']}' มีอยู่แล้ว",
                        "data": {"id": dedup_result.existing_id}}
        except Exception:
            # Fallback: direct DB check
            existing = db.query(SchemaBusinessRule).filter(
                SchemaBusinessRule.rule_code == params["rule_code"]
            ).first()

        if existing:
            return duplicate(existing, f"rule_code '{params['rule_code']}'", rule_code=existing.rule_code,
                             description=existing.rule_description)

        rule = SchemaBusinessRule(
            rule_code=params["rule_code"],
            rule_name=params.get("rule_name", params["description"][:200]),
            rule_description=params["description"],
            table_name=params.get("table_name"),
            severity=params.get("severity", "warning"),
            is_active=True,
            source=MANUAL,  # the admin asked for it and confirmed it
            status=ACTIVE,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        db.add(rule)
        db.commit()
        db.refresh(rule)

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
                action="INSERT", table_name="schema_business_rules",
                record_id=rule.id,
                new_value={"rule_code": params["rule_code"], "description": params["description"][:200]},
                source="admin_agent",
            )
        except Exception:
            pass

        return {
            "success": True,
            "message": f"เพิ่ม rule สำเร็จ: {params['rule_code']} — {params['description']}",
            "data": {"id": rule.id, "rule_code": rule.rule_code}
        }
