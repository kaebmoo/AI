"""
Onboarding Tools — Inspect views, run onboarding, validate config
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool


class InspectViewTool(AdminTool):
    name = "inspect_view"
    description = "Inspect a database view/table: list columns, types, sample data, row count."
    description_th = "ตรวจสอบ view/table: แสดง columns, types, ข้อมูลตัวอย่าง"
    category = "onboarding"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Name of view or table to inspect"
                }
            },
            "required": ["view_name"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        try:
            from app.services.context_onboarding import ContextOnboardingService
            service = ContextOnboardingService(db)
            result = await service.inspect_view(params["view_name"])

            return {
                "success": True,
                "message": f"ตรวจสอบ view '{params['view_name']}' สำเร็จ",
                "data": result,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"ตรวจสอบไม่สำเร็จ: {str(e)}",
                "data": None,
            }


class RunOnboardingTool(AdminTool):
    name = "run_onboarding"
    description = "Run the full Context Onboarding pipeline for a view: inspect → analyze → generate config → apply."
    description_th = "รัน Context Onboarding pipeline เต็มรูปแบบ"
    category = "onboarding"
    requires_confirmation = True

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "view_name": {
                    "type": "string",
                    "description": "Name of view or table to onboard"
                },
                "context_name": {
                    "type": "string",
                    "description": "Context name to create (defaults to view_name)"
                },
                "provider": {
                    "type": "string",
                    "description": "AI provider to use for analysis (gemini/claude/matcha)",
                    "default": "gemini"
                },
                "dry_run": {
                    "type": "boolean",
                    "description": "Preview config without applying to DB",
                    "default": False
                }
            },
            "required": ["view_name"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        try:
            from app.services.context_onboarding import ContextOnboardingService

            service = ContextOnboardingService(db)
            result = await service.onboard(
                view_name=params["view_name"],
                context_name=params.get("context_name", params["view_name"]),
                provider=params.get("provider", "gemini"),
                dry_run=params.get("dry_run", False),
            )

            return {
                "success": True,
                "message": f"Onboarding {'(dry run) ' if params.get('dry_run') else ''}สำเร็จสำหรับ '{params['view_name']}'",
                "data": result,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Onboarding ไม่สำเร็จ: {str(e)}",
                "data": None,
            }


class ValidateConfigTool(AdminTool):
    name = "validate_config"
    description = "Validate configuration for a context: check metadata completeness, rule coverage, example quality."
    description_th = "ตรวจสอบความสมบูรณ์ของ config สำหรับ context"
    category = "onboarding"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "context_name": {
                    "type": "string",
                    "description": "Context name to validate"
                }
            },
            "required": ["context_name"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.schema_models import (
            SchemaContext, SchemaMetadata, SchemaBusinessRule,
            SchemaSemanticMapping
        )
        from app.models.feedback_models import GoldenExample

        context_name = params["context_name"]

        # Check context exists
        context = db.query(SchemaContext).filter(
            SchemaContext.context_name == context_name,
            SchemaContext.is_active == True
        ).first()

        if not context:
            return {
                "success": False,
                "message": f"ไม่พบ context '{context_name}'",
                "data": None
            }

        # Count config items
        metadata_count = db.query(SchemaMetadata).filter(
            SchemaMetadata.table_name == getattr(context, "main_view", context_name)
        ).count()

        rules_count = db.query(SchemaBusinessRule).filter(
            (SchemaBusinessRule.context_name == context_name) |
            (SchemaBusinessRule.context_name == None)
        ).filter(SchemaBusinessRule.is_active == True).count()

        mappings_count = db.query(SchemaSemanticMapping).filter(
            (SchemaSemanticMapping.context_name == context_name) |
            (SchemaSemanticMapping.context_name == None)
        ).filter(SchemaSemanticMapping.is_active == True).count()

        examples_count = db.query(GoldenExample).filter(
            GoldenExample.category == context_name,
            GoldenExample.is_active == True
        ).count()

        # Assess completeness
        issues = []
        if metadata_count == 0:
            issues.append("ไม่มี schema metadata → AI ไม่รู้จัก columns")
        if rules_count < 3:
            issues.append(f"มี rules น้อย ({rules_count}) → อาจขาด business logic")
        if mappings_count < 5:
            issues.append(f"มี mappings น้อย ({mappings_count}) → อาจแปลคำถามผิด")
        if examples_count == 0:
            issues.append("ไม่มี golden examples → AI ไม่มีตัวอย่างอ้างอิง")

        status = "ดี" if not issues else f"มี {len(issues)} ปัญหา"

        return {
            "success": True,
            "message": f"ตรวจสอบ config ของ '{context_name}': {status}",
            "data": {
                "context_name": context_name,
                "metadata_count": metadata_count,
                "rules_count": rules_count,
                "mappings_count": mappings_count,
                "examples_count": examples_count,
                "issues": issues,
                "status": status,
            }
        }
