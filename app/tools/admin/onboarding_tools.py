"""
Onboarding Tools — Inspect views, run onboarding, validate config
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool


def _service():
    """Onboarding reads the view from the business DB and writes config to the config DB
    (REMAIN-9.7: the tools passed the agent's SQLAlchemy session as the DB path)."""
    from app.db.session import business_engine
    from app.services.context_onboarding import ContextOnboardingService
    return ContextOnboardingService(business_engine.url.database)


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
            result = _service().inspect(params["view_name"]).to_dict()

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
                "provider": {
                    "type": "string",
                    "description": "AI provider to use for analysis (gemini/claude/matcha; default = admin default)"
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
            # same pipeline as POST /admin/contexts/onboard
            service = _service()
            dry_run = params.get("dry_run", False)
            analysis = await service.analyze(service.inspect(params["view_name"]), provider=params.get("provider"))
            config = service.generate_config(analysis, view_name=params["view_name"])
            result = service.apply(config, dry_run=dry_run)
            if not dry_run:
                from app.api.v1.admin._shared import mark_brain_dirty
                mark_brain_dirty()

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
        # Config tables live in the config DB — the agent's session is the app DB, and the
        # SchemaContext model this used never existed (REMAIN-9.7)
        from sqlalchemy import text
        from app.db.session import config_engine

        context_name = params["context_name"]
        with config_engine.connect() as conn:
            main_view = conn.execute(text(
                "SELECT main_view FROM schema_contexts WHERE name = :c AND is_active = 1"), {"c": context_name}).scalar()
            if main_view is None:
                return {"success": False, "message": f"ไม่พบ context '{context_name}'", "data": None}

            def count(sql):
                return conn.execute(text(sql), {"c": context_name, "v": main_view}).scalar()

            metadata_count = count("SELECT COUNT(*) FROM schema_metadata WHERE table_name = :v")
            rules_count = count("SELECT COUNT(*) FROM schema_business_rules "
                                "WHERE (table_name = :v OR table_name IS NULL) AND is_active = 1")
            mappings_count = count("SELECT COUNT(*) FROM schema_semantic_mapping "
                                   "WHERE (context_name = :c OR context_name IS NULL) AND is_active = 1")
            examples_count = count("SELECT COUNT(*) FROM golden_examples WHERE category = :c AND is_active = 1")

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
