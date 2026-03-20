"""
Example Tools — Search & Add golden examples
"""

from typing import Any, Dict

from app.tools.admin.base import AdminTool


class SearchExamplesTool(AdminTool):
    name = "search_examples"
    description = "Search golden examples (question-SQL pairs) by keyword in question or SQL."
    description_th = "ค้นหา golden examples ตาม keyword ในคำถามหรือ SQL"
    category = "example"
    requires_confirmation = False

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "search_text": {
                    "type": "string",
                    "description": "Search in question or SQL"
                },
                "context_name": {
                    "type": "string",
                    "description": "Filter by context name"
                }
            },
            "required": []
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.feedback_models import GoldenExample

        query = db.query(GoldenExample).filter(GoldenExample.is_active == True)

        search_text = params.get("search_text")
        if search_text:
            query = query.filter(
                (GoldenExample.question_pattern.ilike(f"%{search_text}%")) |
                (GoldenExample.expected_sql.ilike(f"%{search_text}%"))
            )

        if params.get("context_name"):
            query = query.filter(GoldenExample.category == params["context_name"])

        results = query.limit(50).all()

        examples = [
            {
                "id": e.id,
                "question": e.question_pattern,
                "sql": e.expected_sql,
                "category": e.category,
                "is_active": e.is_active,
            }
            for e in results
        ]

        return {
            "success": True,
            "message": f"พบ {len(examples)} examples",
            "data": examples,
            "total": len(examples),
        }


class AddExampleTool(AdminTool):
    name = "add_example"
    description = "Add a new golden example (correct question-SQL pair for training)."
    description_th = "เพิ่ม golden example ใหม่ (คู่คำถาม-SQL ที่ถูกต้อง)"
    category = "example"
    requires_confirmation = True

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Thai question (e.g., 'รายได้รวมเดือนมกราคม 2568')"
                },
                "sql": {
                    "type": "string",
                    "description": "Correct SQL query"
                },
                "context_name": {
                    "type": "string",
                    "description": "Context name (e.g., 'revenue')"
                }
            },
            "required": ["question", "sql"]
        }

    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        from app.models.feedback_models import GoldenExample
        from datetime import datetime

        example = GoldenExample(
            question_pattern=params["question"],
            expected_sql=params["sql"],
            category=params.get("context_name", ""),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(example)
        db.commit()
        db.refresh(example)

        return {
            "success": True,
            "message": f"เพิ่ม golden example สำเร็จ (id={example.id})",
            "data": {"id": example.id, "question": example.question_pattern}
        }
