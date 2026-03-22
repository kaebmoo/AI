import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

if TYPE_CHECKING:
    from app.services.schema.service import SchemaService


logger = logging.getLogger(__name__)


def _normalize_context_row(row: Optional[Any]) -> Optional[Dict[str, Any]]:
    if row is None:
        return None

    context_row = dict(row)
    keywords = context_row.get("keywords")
    if keywords and isinstance(keywords, str):
        try:
            context_row["keywords"] = json.loads(keywords)
        except (TypeError, ValueError):
            context_row["keywords"] = []
    return context_row


def get_context_info(service: "SchemaService", context_name: str) -> Optional[Dict]:
    cached_context = service.get_cached_context(context_name)
    if cached_context is not None:
        return cached_context

    config_engine = service.get_config_engine()
    with config_engine.connect() as conn:
        try:
            row = conn.execute(
                text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                {"name": context_name},
            ).mappings().fetchone()

            if not row:
                alt_name = context_name.replace("_", " ")
                if alt_name != context_name:
                    row = conn.execute(
                        text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                        {"name": alt_name},
                    ).mappings().fetchone()

            if not row:
                alt_name = context_name.replace(" ", "_")
                if alt_name != context_name:
                    row = conn.execute(
                        text("SELECT * FROM schema_contexts WHERE name = :name AND is_active = 1"),
                        {"name": alt_name},
                    ).mappings().fetchone()

            context_info = _normalize_context_row(row)
            if context_info is not None:
                service.set_cached_context(context_name, context_info)
                return context_info

            logger.warning("Context '%s' not found in schema_contexts table", context_name)
            return None
        except SQLAlchemyError as exc:
            logger.warning("Failed to query schema_contexts: %s", exc)
            return None


def get_all_contexts(service: "SchemaService") -> List[Dict]:
    config_engine = service.get_config_engine()
    with config_engine.connect() as conn:
        try:
            result = conn.execute(text("SELECT * FROM schema_contexts WHERE is_active = 1 ORDER BY priority DESC"))
            contexts = []
            for row in result.mappings().fetchall():
                context = _normalize_context_row(row)
                if context is not None:
                    contexts.append(context)
            return contexts
        except SQLAlchemyError as exc:
            logger.warning("Failed to query schema_contexts: %s", exc)
            return []


def create_context(service: "SchemaService", data: Dict) -> Dict:
    config_engine = service.get_config_engine()
    with config_engine.begin() as conn:
        columns = ["name", "display_name", "description", "main_view", "is_active", "priority", "keywords", "instruction_th", "instruction_en"]
        placeholders = ", ".join([f":{column}" for column in columns])
        sql = f"INSERT INTO schema_contexts ({', '.join(columns)}) VALUES ({placeholders})"

        params = data.copy()
        if params.get("keywords"):
            params["keywords"] = json.dumps(params["keywords"], ensure_ascii=False)

        cursor = conn.execute(text(sql), params)
        context_id = cursor.lastrowid
        row = _normalize_context_row(
            conn.execute(text("SELECT * FROM schema_contexts WHERE id = :id"), {"id": context_id}).mappings().fetchone()
        )

    refresh_context_cache(service)
    return row or {}


def update_context(service: "SchemaService", context_id: int, data: Dict) -> Optional[Dict]:
    config_engine = service.get_config_engine()
    with config_engine.begin() as conn:
        set_parts = []
        params = data.copy()
        params["id"] = context_id

        for key, value in data.items():
            if key == "keywords":
                params["keywords"] = json.dumps(value, ensure_ascii=False)
            set_parts.append(f"{key} = :{key}")

        params["updated_at"] = datetime.utcnow()
        set_parts.append("updated_at = :updated_at")

        sql = f"UPDATE schema_contexts SET {', '.join(set_parts)} WHERE id = :id"
        cursor = conn.execute(text(sql), params)
        if cursor.rowcount == 0:
            return None

        row = _normalize_context_row(
            conn.execute(text("SELECT * FROM schema_contexts WHERE id = :id"), {"id": context_id}).mappings().fetchone()
        )

    refresh_context_cache(service)
    return row


def delete_context(service: "SchemaService", context_id: int) -> None:
    config_engine = service.get_config_engine()
    with config_engine.begin() as conn:
        conn.execute(text("DELETE FROM schema_contexts WHERE id = :id"), {"id": context_id})
    refresh_context_cache(service)


def refresh_context_cache(service: "SchemaService") -> None:
    service.clear_cached_contexts()