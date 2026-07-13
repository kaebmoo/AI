
"""
NT AI Assistant - AI Service
==================================
Service for interacting with AI API providers via MCP (Model Context Protocol).

Supports:
- Claude API (Anthropic)
- Google AI / Gemini API
- Matcha AI (OpenAI Compatible)

Usage:
    # New style (recommended): use provider registry
    from app.providers.registry import provider_registry
    provider = provider_registry.create_provider("claude", api_key="...")
    ai_service = AIService(provider=provider, mcp_client=global_mcp_client)

    # Legacy style (still supported): use factory functions
    ai_service = create_claude_service(api_key="...", mcp_client=global_mcp_client)
"""

import json
import re
import logging
from typing import Dict, List, Optional, Callable

import app.services.ai.hybrid_flow as hybrid_flow
import app.services.ai.hierarchy_context as hierarchy_context
import app.services.ai.retry_loop as retry_loop
import app.services.ai.response_utils as response_utils
from app.services.mcp_client import MCPClientService
from app.config import settings

RECOVERABLE_AI_EXCEPTIONS = (AttributeError, ImportError, KeyError, RuntimeError, TypeError, ValueError, json.JSONDecodeError)

# Optional import - VannaService may not be available
try:
    from app.services.vanna_service import VannaService
    HAS_VANNA = True
except RECOVERABLE_AI_EXCEPTIONS:
    # chromadb/pydantic can fail with ConfigError, not just ImportError
    HAS_VANNA = False
    VannaService = None

# ============================================================
# Re-export from providers package for backward compatibility
# ============================================================
from app.providers.base import AIProvider, ConfidenceResult, QueryResult, RetryStatus  # noqa: F401
from app.providers.claude_provider import ClaudeProvider  # noqa: F401
from app.providers.gemini_provider import GeminiProvider  # noqa: F401
from app.providers.matcha_provider import MatchaProvider  # noqa: F401
from app.providers.retry_config import ai_retry, create_retry_decorator  # noqa: F401

logger = logging.getLogger(__name__)

_HIERARCHY_CACHE = hierarchy_context.get_hierarchy_cache()
COLUMN_HIERARCHIES = hierarchy_context.COLUMN_HIERARCHIES
get_column_hierarchies = hierarchy_context.get_column_hierarchies

__all__ = [
    "AIService",
    "AIProvider",
    "ConfidenceResult",
    "QueryResult",
    "RetryStatus",
    "ClaudeProvider",
    "GeminiProvider",
    "MatchaProvider",
    "ai_retry",
    "create_retry_decorator",
    "COLUMN_HIERARCHIES",
    "_HIERARCHY_CACHE",
    "get_column_hierarchies",
]


class AIService:
    """Async AI Service integrating MCP"""

    def __init__(
        self,
        provider,  # AIProvider instance OR str (legacy)
        api_key: str = None,
        mcp_client: MCPClientService = None,
        model: Optional[str] = None,
        **kwargs
    ):
        # Support both new and legacy constructors
        if isinstance(provider, str):
            # Legacy: provider is a string name
            self.provider_name = provider
            self.mcp_client = mcp_client if mcp_client is not None else api_key  # legacy compat: api_key might be mcp_client
            self._init_legacy_provider(provider, api_key, model, **kwargs)
        elif isinstance(provider, AIProvider):
            # New style: provider is an AIProvider instance
            self.provider = provider
            self.provider_name = provider.name
            self.mcp_client = mcp_client if mcp_client is not None else api_key
        else:
            raise ValueError(f"provider must be str or AIProvider, got {type(provider)}")

        self._pending_limit_warning = ""

        # Initialize Vanna RAG
        try:
            self.vanna = VannaService(config={
                "path": settings.VANNA_CHROMA_PATH,
                "distance_threshold": settings.VANNA_DISTANCE_THRESHOLD
            })
        except RECOVERABLE_AI_EXCEPTIONS:
            self.vanna = None

    def _init_legacy_provider(self, provider_name: str, api_key: str, model: Optional[str], **kwargs):
        """Legacy constructor: create provider from string name"""
        if provider_name == "claude":
            self.provider = ClaudeProvider(
                api_key,
                model or "claude-sonnet-4-6",
                extended_thinking=kwargs.get("extended_thinking", False),
                thinking_budget_tokens=kwargs.get("thinking_budget_tokens", 8000),
            )
        elif provider_name == "gemini":
            self.provider = GeminiProvider(api_key, model) if model else GeminiProvider(api_key)
        elif provider_name == "matcha":
            self.provider = MatchaProvider(api_key, kwargs.get("api_url"), model) if model else MatchaProvider(api_key, kwargs.get("api_url"))
        else:
            raise ValueError(f"Unknown provider: {provider_name}")

    async def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str, dimension_families: Optional[Dict[str, List[str]]] = None, hierarchy_info: Optional[list] = None, schema_metadata: Optional[list] = None) -> str:
        return await self.provider.explain_result(question, sql, data, system_prompt, dimension_families=dimension_families, hierarchy_info=hierarchy_info, schema_metadata=schema_metadata)

    async def query_with_retry(
        self,
        question: str,
        max_retries: int = 3,
        history: Optional[List[Dict]] = None,
        on_status: Optional[Callable[[RetryStatus], None]] = None,
        explain: bool = True,
        context_name: str = "revenue"
    ) -> QueryResult:
        return await retry_loop.query_with_retry(
            self,
            question=question,
            max_retries=max_retries,
            history=history,
            on_status=on_status,
            explain=explain,
            context_name=context_name,
        )

    async def query_hybrid(
        self,
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
        **kwargs
    ) -> QueryResult:
        return await hybrid_flow.query_hybrid(
            self,
            question=question,
            system_prompt=system_prompt,
            max_retries=max_retries,
            history=history,
            on_status=on_status,
            context_name=context_name,
            two_pass_enabled=two_pass_enabled,
            value_lookup_enabled=value_lookup_enabled,
            value_verification_enabled=value_verification_enabled,
            cheap_model=cheap_model,
            **kwargs,
        )

    @staticmethod
    def _prepare_data_for_explanation(
        data: List[Dict],
        schema_metadata: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        return response_utils.prepare_data_for_explanation(data, schema_metadata=schema_metadata)

    def _extract_sql(self, text: str) -> Optional[str]:
        return response_utils.extract_sql(text)

    def _extract_explanation(self, text: str) -> str:
        return response_utils.extract_explanation(text)

    def _get_vanna_context_string(self, question: str) -> str:
        return hierarchy_context.get_vanna_context_string(self, question)

    def get_vanna_context_string(self, question: str) -> str:
        return self._get_vanna_context_string(question)

    def lookup_values_from_question(self, question: str, context_name: str, table_name: str) -> List[Dict]:
        return self._lookup_values_from_question(question, context_name, table_name)

    def detect_hierarchy_level(self, question: str, context_name: str) -> Optional[Dict]:
        return self._detect_hierarchy_level(question, context_name)

    def format_value_matches(self, value_matches: List[Dict], hierarchy=None, detected_level=None) -> str:
        return self._format_value_matches(value_matches, hierarchy=hierarchy, detected_level=detected_level)

    def extract_sql(self, text: str) -> Optional[str]:
        return self._extract_sql(text)

    def extract_explanation(self, text: str) -> str:
        return self._extract_explanation(text)

    def prepare_data_for_explanation(
        self,
        data: List[Dict],
        schema_metadata: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        return self._prepare_data_for_explanation(data, schema_metadata=schema_metadata)

    def parse_intent_json(self, text: str) -> Optional[Dict]:
        return self._parse_intent_json(text)

    def log_value_corrections(self, corrections, question: str, context_name: str) -> None:
        self._log_value_corrections(corrections, question, context_name)

    def get_pending_limit_warning(self) -> str:
        return getattr(self, "_pending_limit_warning", "")

    def set_pending_limit_warning(self, warning: str) -> None:
        self._pending_limit_warning = warning

    # ============================================================
    # Smart Value Lookup
    # ============================================================

    _THAI_STOP_WORDS = hierarchy_context.THAI_STOP_WORDS

    def _extract_keywords_from_question(self, question: str, context_name: str = None) -> List[str]:
        return hierarchy_context.extract_keywords_from_question(self, question, context_name)

    def _log_value_corrections(self, corrections, question: str, context_name: str):
        """Log value corrections to DB for admin learning (non-blocking)."""
        try:
            from sqlalchemy import create_engine, text

            db_url = settings.DATABASE_URL
            engine = create_engine(db_url)
            with engine.connect() as conn:
                conn.execute(text("""
                    CREATE TABLE IF NOT EXISTS query_correction_log (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        question TEXT,
                        original_column TEXT,
                        original_value TEXT,
                        correct_column TEXT,
                        correct_value TEXT,
                        context_name TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                for correction in corrections:
                    conn.execute(text("""
                        INSERT INTO query_correction_log
                        (question, original_column, original_value, correct_column, correct_value, context_name)
                        VALUES (:q, :oc, :ov, :cc, :cv, :ctx)
                    """), {
                        "q": question[:500],
                        "oc": correction.original_column,
                        "ov": correction.original_value,
                        "cc": correction.correct_column,
                        "cv": correction.correct_value,
                        "ctx": context_name,
                    })
                conn.commit()
        except RECOVERABLE_AI_EXCEPTIONS as exc:
            logger.debug("Failed to log value corrections: %s", exc)

    def _lookup_values_from_question(self, question: str, context_name: str, table_name: str) -> List[Dict]:
        return hierarchy_context.lookup_values_from_question(self, question, context_name, table_name)

    @staticmethod
    def _detect_hierarchy_level(question: str, context_name: str) -> Optional[Dict]:
        from app.services import ai_service as legacy_ai_service

        hierarchy = legacy_ai_service.get_column_hierarchies().get(context_name)
        if not hierarchy:
            return None

        question_lower = question.lower()
        matched_levels: Dict[int, tuple[int, Dict]] = {}
        for level_info in hierarchy:
            for keyword in level_info["detection_keywords"]:
                if keyword.lower() in question_lower:
                    level = level_info["level"]
                    if level not in matched_levels or len(keyword) > matched_levels[level][0]:
                        matched_levels[level] = (len(keyword), level_info)

        if not matched_levels:
            return None
        if len(matched_levels) == 1:
            return list(matched_levels.values())[0][1]

        parent_level = min(matched_levels.keys())
        return matched_levels[parent_level][1]

    @staticmethod
    def _format_value_matches(value_matches: List[Dict], hierarchy=None, detected_level=None) -> str:
        return hierarchy_context.format_value_matches(value_matches, hierarchy=hierarchy, detected_level=detected_level)

    @staticmethod
    def _format_value_matches_flat(value_matches: List[Dict]) -> str:
        return hierarchy_context.format_value_matches_flat(value_matches)

    # ============================================================
    # Two-Pass SQL Generation
    # ============================================================

    def _parse_intent_json(self, text: str) -> Optional[Dict]:
        return response_utils.parse_intent_json(text)

    async def _extract_intent(
        self,
        question: str,
        system_prompt: str,
        context_name: str,
        context_table: str,
        context_thai: str,
        history_context: str,
        rag_context: str,
        cheap_model: Optional[str] = None
    ) -> Optional[Dict]:
        return await hybrid_flow.extract_intent(
            self,
            question=question,
            system_prompt=system_prompt,
            context_name=context_name,
            context_table=context_table,
            context_thai=context_thai,
            history_context=history_context,
            rag_context=rag_context,
            cheap_model=cheap_model,
        )

    def _build_pass2_prompt(
        self,
        question: str,
        intent: Dict,
        context_table: str,
        context_thai: str,
        value_matches: List[Dict] = None,
        hierarchy: List[Dict] = None,
        detected_level: Optional[Dict] = None
    ) -> str:
        return hybrid_flow.build_pass2_prompt(
            self,
            question=question,
            intent=intent,
            context_table=context_table,
            context_thai=context_thai,
            value_matches=value_matches,
            hierarchy=hierarchy,
            detected_level=detected_level,
        )

    def train(self, question: str, sql_query: str) -> bool:
        """Train the RAG system with a verified Q&A pair"""
        try:
            if not self.vanna:
                logger.warning("Vanna service not initialized, skipping training")
                return False

            return self.vanna.train(question=question, sql=sql_query)
        except RECOVERABLE_AI_EXCEPTIONS as exc:
            logger.error("Error in AIService.train: %s", exc)
            return False

    async def suggest_mappings(self, columns: List[Dict], samples: Dict[str, List]) -> List[Dict[str, str]]:
        """Suggest column name mappings (aliases) using AI."""
        try:
            column_info = []
            for col in columns:
                col_name = col['name']
                col_type = col['type']
                sample_vals = samples.get(col_name, [])[:3]
                column_info.append(f"- {col_name} ({col_type}): {sample_vals}")

            column_text = "\n".join(column_info)

            prompt = f"""ต้องการตั้งชื่อ alias (Suggested Alias) ภาษาอังกฤษที่เหมาะสมสำหรับคอลัมน์เหล่านี้ แบบ Snake Case เท่านั้น:

{column_text}

กรุณาแนะนำ alias ที่:
1. สั้น กระชับ ไม่เกิน 3-4 คำ
2. เข้าใจง่าย เหมาะกับการใช้งานทั่วไป
3. เป็นภาษาอังกฤษที่ถูกต้อง

ตอบในรูปแบบ JSON array:
```json
[
  {{"col": "column_name", "alias": "sugestion_name", "reason": "short reason"}},
  ...
]
```"""

            # Structured output first (F8.3) — fallback to text parse below
            suggestions_schema = {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "col": {"type": "string"},
                                "alias": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": ["col", "alias"],
                        },
                    }
                },
                "required": ["suggestions"],
            }
            structured = await self.provider.generate_structured(
                prompt, suggestions_schema,
                system_prompt="คุณเป็น AI ที่ช่วยตั้งชื่อคอลัมน์ภาษาไทยให้เหมาะสม",
                schema_name="suggestions",
            )
            if structured and isinstance(structured.get("suggestions"), list):
                return structured["suggestions"]

            result = await self.provider.generate_content(prompt, system_prompt="คุณเป็น AI ที่ช่วยตั้งชื่อคอลัมน์ภาษาไทยให้เหมาะสม")

            json_match = re.search(r'```json\s*(\[.*?\])\s*```', result, re.DOTALL)
            if json_match:
                suggestions = json.loads(json_match.group(1))
                return suggestions

            try:
                suggestions = json.loads(result)
                if isinstance(suggestions, list):
                    return suggestions
            except json.JSONDecodeError:
                pass

            return [
                {
                    'col': col['name'],
                    'alias': col['name'].lower().replace('_', ' '),
                    'reason': 'ชื่อเดิมโดยแปลง underscore เป็น space'
                }
                for col in columns
            ]

        except RECOVERABLE_AI_EXCEPTIONS as exc:
            logger.error("Error in suggest_mappings: %s", exc)
            return [
                {
                    'col': col['name'],
                    'alias': col['name'],
                    'reason': 'ไม่สามารถสร้างคำแนะนำได้ ใช้ชื่อเดิม'
                }
                for col in columns
            ]
