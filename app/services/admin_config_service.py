"""
NT AI Assistant - Admin Configuration Service
==============================================
Service for managing runtime configuration with fallback mechanism:
1. Database (admin_config table) - First priority
2. Environment variables (.env) - Fallback
3. Hardcoded defaults - Safety net
"""

import os
from typing import Optional, Dict, List, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
import logging
from app.providers.base import clear_model_tier_cache

logger = logging.getLogger(__name__)


class AdminConfigService:
    """
    Manages configuration with database + .env fallback.
    Reads from config DB (admin_config, ai_providers, ai_models tables).
    """

    def __init__(self, db: Session = None):
        """
        Args:
            db: Config DB session. If None, creates one from ConfigSessionLocal.
                After DB separation, admin_config lives in config.db, not app.db.
        """
        if db is not None:
            self.db = db
            self._owns_session = False
        else:
            from app.db.session import ConfigSessionLocal
            self.db = ConfigSessionLocal()
            self._owns_session = True
        self._cache = {}  # Simple in-memory cache

    def close(self):
        """Close owned session if we created it."""
        if self._owns_session and self.db:
            self.db.close()

    # ============================================================
    # Core Config Methods (with fallback)
    # ============================================================

    def get_config(
        self,
        key: str,
        default: Optional[str] = None,
        use_cache: bool = True
    ) -> Optional[str]:
        """
        Get config value with fallback mechanism:
        1. Database (if table exists)
        2. Environment variable
        3. Provided default

        Args:
            key: Config key to retrieve
            default: Default value if not found anywhere
            use_cache: Whether to use cache

        Returns:
            Config value or None
        """
        # Check cache first
        if use_cache and key in self._cache:
            return self._cache[key]

        # 1. Try database first
        try:
            result = self.db.execute(
                text("""
                    SELECT config_value
                    FROM admin_config
                    WHERE config_key = :key
                    AND is_active = 1
                    LIMIT 1
                """),
                {"key": key}
            ).fetchone()

            if result and result[0] is not None:
                value = result[0]
                self._cache[key] = value
                return value

        except Exception as e:
            # Table doesn't exist or DB error - fallback to .env
            logger.debug(f"Database config not available for '{key}': {e}")

        # 2. Fallback to environment variable
        env_key = key.upper()
        env_value = getattr(settings, env_key, None)

        if env_value is not None:
            return str(env_value)

        # 3. Return default
        return default

    def set_config(
        self,
        key: str,
        value: str,
        config_type: str = 'general',
        category: str = 'ai',
        updated_by: Optional[str] = None
    ) -> bool:
        """
        Set config value in database.

        Args:
            key: Config key
            value: Config value
            config_type: Type of config (ai_provider, model, api_key, feature_flag)
            category: Category (ai, database, security, features)
            updated_by: User who made the change

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if exists
            exists = self.db.execute(
                text("SELECT id FROM admin_config WHERE config_key = :key"),
                {"key": key}
            ).fetchone()

            if exists:
                # Update existing
                self.db.execute(
                    text("""
                        UPDATE admin_config
                        SET config_value = :value,
                            updated_by = :updated_by,
                            updated_at = CURRENT_TIMESTAMP
                        WHERE config_key = :key
                    """),
                    {"key": key, "value": value, "updated_by": updated_by}
                )
            else:
                # Insert new
                self.db.execute(
                    text("""
                        INSERT INTO admin_config (
                            config_key, config_value, config_type, category,
                            is_active, updated_by
                        ) VALUES (
                            :key, :value, :type, :category, 1, :updated_by
                        )
                    """),
                    {
                        "key": key,
                        "value": value,
                        "type": config_type,
                        "category": category,
                        "updated_by": updated_by
                    }
                )

            self.db.commit()

            # Invalidate cache
            if key in self._cache:
                del self._cache[key]

            return True

        except Exception as e:
            logger.error(f"Failed to set config '{key}': {e}")
            self.db.rollback()
            return False

    # ============================================================
    # AI Provider Configuration
    # ============================================================

    def get_ai_config(self) -> Dict[str, Any]:
        """
        Get complete AI configuration with fallbacks.
        Dynamically queries ai_providers table for provider list.
        Falls back to hardcoded 3-provider config if DB table unavailable.

        Returns:
            Dict with provider, models, and enabled status
        """
        config: Dict[str, Any] = {
            "default_provider": self.get_config("default_ai_provider", "matcha"),
        }

        # Dynamic: query all active providers from DB
        try:
            providers = self.db.execute(text(
                "SELECT id FROM ai_providers WHERE is_active = 1 ORDER BY priority DESC"
            )).fetchall()
            if providers:
                for row in providers:
                    pid = row[0]
                    config[f"{pid}_enabled"] = self.get_config(f"{pid}_enabled", "true") == "true"
                    # Get default model for this provider
                    model_row = self.db.execute(text(
                        "SELECT model_id FROM ai_models "
                        "WHERE provider_id = :pid AND is_default = 1 AND is_active = 1"
                    ), {"pid": pid}).fetchone()
                    default_model = model_row[0] if model_row else ""
                    config[f"{pid}_model"] = self.get_config(f"{pid}_model", default_model)
            else:
                raise ValueError("No providers in DB")
        except Exception:
            # Fallback: hardcoded 3-provider config (DB table missing or empty)
            config.update({
                "claude_enabled": self.get_config("claude_enabled", "true") == "true",
                "gemini_enabled": self.get_config("gemini_enabled", "true") == "true",
                "matcha_enabled": self.get_config("matcha_enabled", "true") == "true",
                "claude_model": self.get_config("claude_model", settings.CLAUDE_MODEL),
                "gemini_model": self.get_config("gemini_model", settings.GEMINI_MODEL),
                "matcha_model": self.get_config("matcha_model", settings.MATCHA_MODEL),
            })

        # Provider-specific extras from admin_config
        config["matcha_api_url"] = self.get_config("matcha_api_url", settings.MATCHA_API_URL or "")
        config["claude_extended_thinking"] = self.get_config(
            "claude_extended_thinking",
            "true" if settings.CLAUDE_EXTENDED_THINKING else "false"
        ) == "true"
        config["claude_thinking_budget_tokens"] = int(self.get_config(
            "claude_thinking_budget_tokens",
            str(settings.CLAUDE_THINKING_BUDGET_TOKENS)
        ))

        return config

    def update_ai_config(
        self,
        updates: Dict[str, Any],
        updated_by: Optional[str] = None
    ) -> bool:
        """
        Update AI configuration from a generic dict.
        Supports any provider — keys follow pattern: {provider}_{setting}
        or special keys like "default_provider".

        Key mapping:
            "default_provider" → stored as "default_ai_provider"
            "{provider}_enabled" (bool) → stored as "true"/"false"
            "{provider}_model" (str) → stored as-is
            any other key → stored as-is

        Args:
            updates: Dict of config updates (keys as received from API)
            updated_by: User who made changes

        Returns:
            True if all updates successful
        """
        # Normalize keys and convert values to strings
        normalized: Dict[str, Optional[str]] = {}
        for key, value in updates.items():
            if value is None:
                continue
            # Special mapping
            if key == "default_provider":
                normalized["default_ai_provider"] = str(value)
            elif isinstance(value, bool):
                normalized[key] = "true" if value else "false"
            elif isinstance(value, (int, float)):
                normalized[key] = str(value)
            else:
                normalized[key] = str(value)

        success = True
        for key, value in normalized.items():
            if value is not None:
                # Determine type for categorization
                if "enabled" in key or "default" in key:
                    config_type = "ai_provider"
                elif "model" in key:
                    config_type = "model"
                else:
                    config_type = "api_key"

                if not self.set_config(key, value, config_type, "ai", updated_by):
                    success = False

        if success:
            default_provider_id = normalized.get("default_ai_provider")
            if default_provider_id:
                self._sync_provider_default_flags(default_provider_id)

                default_model_key = f"{default_provider_id}_model"
                default_model_id = normalized.get(default_model_key) or self.get_config(default_model_key, "")
                if default_model_id:
                    self._sync_model_default_flags(default_provider_id, default_model_id)

            for key, value in normalized.items():
                if key.endswith("_model") and value:
                    provider_id = key[:-6]
                    self._sync_model_default_flags(provider_id, value)

        return success

    def _sync_provider_default_flags(self, default_provider_id: str) -> None:
        try:
            self.db.execute(
                text(
                    """
                    UPDATE ai_providers
                    SET is_default = CASE WHEN id = :provider_id THEN 1 ELSE 0 END
                    """
                ),
                {"provider_id": default_provider_id},
            )
            self.db.commit()
        except Exception:
            logger.debug("Failed to sync provider default flags", exc_info=True)
            self.db.rollback()

    def _sync_model_default_flags(self, provider_id: str, default_model_id: str) -> None:
        try:
            self.db.execute(
                text(
                    """
                    UPDATE ai_models
                    SET is_default = CASE WHEN provider_id = :provider_id AND model_id = :model_id THEN 1 ELSE 0 END
                    WHERE provider_id = :provider_id
                    """
                ),
                {"provider_id": provider_id, "model_id": default_model_id},
            )
            self.db.commit()
        except Exception:
            logger.debug("Failed to sync model default flags for provider %s", provider_id, exc_info=True)
            self.db.rollback()

    def get_active_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of active AI providers with 3-tier fallback:
        1. Database (ai_providers table) + admin_config enabled status
        2. admin_config table (legacy)
        3. Hardcoded defaults

        Returns:
            List of provider info dicts
        """
        providers = []

        # Priority 1: Try to get from ai_providers table
        # BUT also check admin_config for enabled status and default
        try:
            results = self.db.execute(
                text("""
                    SELECT
                        p.id,
                        p.name,
                        p.display_name,
                        p.icon,
                        m.model_id as default_model
                    FROM ai_providers p
                    LEFT JOIN ai_models m ON p.id = m.provider_id AND m.is_default = 1
                    WHERE p.is_active = 1
                    ORDER BY p.priority DESC, p.name
                """)
            ).fetchall()

            if results:
                # Get default provider from admin_config (priority over ai_providers.is_default)
                default_provider = self.get_config("default_ai_provider", "matcha")

                # Database has providers - but filter by admin_config enabled status
                for row in results:
                    provider_id = row[0]

                    # Check if provider is enabled in admin_config
                    enabled_key = f"{provider_id}_enabled"
                    is_enabled = self.get_config(enabled_key, "true") == "true"
                    configured_model = self.get_config(f"{provider_id}_model", row[4] or "default")

                    if is_enabled:
                        providers.append({
                            "id": provider_id,
                            "name": row[1],
                            "display_name": row[2] or row[1],
                            "icon": row[3] or "bulb",
                            "is_default": provider_id == default_provider,  # Use admin_config value
                            "model": configured_model or row[4] or "default"
                        })

                # Only return if we found enabled providers
                if providers:
                    return providers

        except Exception as e:
            # Table doesn't exist or query failed - fall back
            logger.debug(f"Failed to get providers from ai_providers table: {e}")

        # Priority 2 & 3: Fallback to admin_config + hardcoded
        config = self.get_ai_config()

        if config["claude_enabled"]:
            providers.append({
                "id": "claude",
                "name": "Claude",
                "display_name": "Claude (Anthropic)",
                "model": config["claude_model"],
                "icon": "bulb",
                "is_default": config["default_provider"] == "claude"
            })

        if config["gemini_enabled"]:
            providers.append({
                "id": "gemini",
                "name": "Gemini",
                "display_name": "Gemini (Google)",
                "model": config["gemini_model"],
                "icon": "sparkles",
                "is_default": config["default_provider"] == "gemini"
            })

        if config["matcha_enabled"]:
            providers.append({
                "id": "matcha",
                "name": "Matcha",
                "display_name": "Matcha (NT Gateway)",
                "model": config["matcha_model"],
                "icon": "leaf",
                "is_default": config["default_provider"] == "matcha"
            })

        return providers

    def get_effective_ai_state(self) -> Dict[str, Any]:
        """
        Get the effective runtime AI provider/model state for admin surfaces.

        Returns:
            Dict describing the effective provider/model, source, and alignment
        """
        ai_config = self.get_ai_config()
        feature_flags = self.get_feature_flags()
        provider_records = self.get_all_providers(include_inactive=True)
        active_providers = self.get_active_providers()

        provider_lookup = {provider["id"]: provider for provider in provider_records}
        active_provider_ids = {provider["id"] for provider in active_providers}

        default_provider_id = ai_config.get("default_provider") or ""
        default_provider = provider_lookup.get(default_provider_id)
        if default_provider is None:
            default_provider = next(
                (provider for provider in active_providers if provider["id"] == default_provider_id),
                None,
            )

        config_source = "database" if provider_records and any(
            provider.get("source") == "database" for provider in provider_records
        ) else "fallback"

        provider_table_default = next(
            (provider["id"] for provider in provider_records if provider.get("is_default")),
            None,
        )
        provider_alignment = provider_table_default in (None, default_provider_id)

        default_model_id = ai_config.get(f"{default_provider_id}_model", "") if default_provider_id else ""
        default_model = None
        model_alignment = True
        total_models = 0
        active_models = 0

        if provider_records:
            for provider in provider_records:
                models = self.get_models_by_provider(provider["id"], include_inactive=True)
                total_models += len(models)
                active_models += sum(1 for model in models if model.get("is_active"))
                if provider["id"] == default_provider_id:
                    default_model = next(
                        (model for model in models if model["model_id"] == default_model_id),
                        None,
                    )
                    table_default_model = next(
                        (model for model in models if model.get("is_default")),
                        None,
                    )
                    table_default_model_id = table_default_model["model_id"] if table_default_model else None
                    model_alignment = table_default_model_id in (None, default_model_id)
                    if default_model is None:
                        default_model = table_default_model
        else:
            for provider in active_providers:
                models = self.get_available_models(provider["id"])
                total_models += len(models)
                active_models += len(models)
                if provider["id"] == default_provider_id:
                    default_model = next(
                        (
                            {
                                "model_id": model_id,
                                "display_name": model_id,
                                "is_active": True,
                                "is_default": model_id == default_model_id,
                                "tier": "default",
                            }
                            for model_id in models
                            if model_id == default_model_id
                        ),
                        None,
                    )

        enabled_features = [name for name, enabled in feature_flags.items() if enabled]

        return {
            "default_provider": {
                "id": default_provider_id,
                "name": (default_provider or {}).get("name") or default_provider_id,
                "display_name": (default_provider or {}).get("display_name")
                or (default_provider or {}).get("name")
                or default_provider_id,
                "is_active": default_provider_id in active_provider_ids,
            },
            "default_model": {
                "id": default_model_id,
                "display_name": (default_model or {}).get("display_name") or default_model_id,
                "is_active": (default_model or {}).get("is_active", bool(default_model_id)),
                "tier": (default_model or {}).get("tier", "default"),
            },
            "provider_source": config_source,
            "fallback_in_use": config_source != "database",
            "provider_alignment": provider_alignment,
            "model_alignment": model_alignment,
            "active_provider_count": len(active_providers),
            "total_provider_count": len(provider_records) if provider_records else len(active_providers),
            "active_model_count": active_models,
            "total_model_count": total_models,
            "active_providers": active_providers,
            "enabled_features": enabled_features,
            "feature_flags": feature_flags,
            "last_brain_sync_at": self.get_config("last_brain_sync_at"),
        }

    def _sync_provider_runtime_config(
        self,
        provider_id: str,
        *,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        default_model: Optional[str] = None,
    ) -> None:
        """Keep legacy admin_config keys aligned with provider/model tables."""
        if is_active is not None:
            self.set_config(
                f"{provider_id}_enabled",
                "true" if is_active else "false",
                config_type="ai_provider",
                category="ai",
            )

        if is_default:
            self.set_config(
                "default_ai_provider",
                provider_id,
                config_type="ai_provider",
                category="ai",
            )

        if default_model is not None:
            self.set_config(
                f"{provider_id}_model",
                default_model,
                config_type="model",
                category="ai",
            )

    def get_available_models(self, provider: str) -> List[str]:
        """
        Get available models for a provider with 2-tier fallback:
        1. Database (ai_models table)
        2. Hardcoded defaults

        Args:
            provider: Provider name (claude, gemini, matcha)

        Returns:
            List of model IDs
        """
        # Priority 1: Try to get from ai_models table
        try:
            results = self.db.execute(
                text("""
                    SELECT model_id
                    FROM ai_models
                    WHERE provider_id = :provider
                    AND is_active = 1
                    ORDER BY priority DESC, display_name
                """),
                {"provider": provider}
            ).fetchall()

            if results:
                # Database has models - use them
                return [row[0] for row in results]

        except Exception as e:
            # Table doesn't exist or query failed - fall back
            logger.debug(f"Failed to get models from ai_models table: {e}")

        # Priority 2: Hardcoded defaults
        hardcoded_models = {
            "claude": [
                "claude-sonnet-4-6",
                "claude-opus-4-6",
                "claude-haiku-4-5-20251001"
            ],
            "gemini": [
                "gemini-3-flash-preview",
                "gemini-2.0-flash-exp",
                "gemini-2.0-flash-thinking-exp-1219",
                "gemini-1.5-pro"
            ],
            "matcha": [
                "gpt-4.1",
                "gpt-4o",
                "gpt-4-turbo",
                "gpt-3.5-turbo"
            ]
        }

        return hardcoded_models.get(provider, [])

    # ============================================================
    # Feature Flags
    # ============================================================

    def get_feature_flags(self) -> Dict[str, bool]:
        """
        Get all feature flags.

        Returns:
            Dict of feature name to enabled status
        """
        return {
            "rag_enabled": self.get_config("rag_enabled", "false") == "true",
            "auto_context_detection": self.get_config("auto_context_detection", "true") == "true",
            "debug_mode": self.get_config("debug_mode", "false") == "true",
            "log_queries": self.get_config("log_queries", "true") == "true",
            "collect_feedback": self.get_config("collect_feedback", "true") == "true",
            "two_pass_enabled": self.get_config(
                "two_pass_enabled",
                "true" if settings.TWO_PASS_ENABLED else "false"
            ) == "true",
            "value_lookup_enabled": self.get_config(
                "value_lookup_enabled",
                "true" if settings.VALUE_LOOKUP_ENABLED else "false"
            ) == "true",
            "tier_classification_enabled": self.get_config(
                "tier_classification_enabled",
                "true" if settings.TIER_CLASSIFICATION_ENABLED else "false"
            ) == "true",
            "value_verification_enabled": self.get_config(
                "value_verification_enabled",
                "true" if settings.VALUE_VERIFICATION_ENABLED else "false"
            ) == "true",
            # F9 flags (all default OFF — enabling requires measurements, see plan/RESULT_F9.md)
            "template_answers_enabled": self.get_config("template_answers_enabled", "false") == "true",
            "intent_state_enabled": self.get_config("intent_state_enabled", "false") == "true",
            "escalation_ladder_enabled": self.get_config("escalation_ladder_enabled", "false") == "true",
            "escalation_tool_loop_enabled": self.get_config("escalation_tool_loop_enabled", "false") == "true",
            "query_latency_budget_s": self._get_float_config("query_latency_budget_s", 45.0),
        }

    def _get_float_config(self, key: str, default: float) -> float:
        """Numeric config with validation — bad values fall back to default."""
        raw = self.get_config(key, str(default))
        try:
            value = float(raw)
            return value if value > 0 else default
        except (TypeError, ValueError):
            logger.warning(f"Config {key}={raw!r} is not a valid positive number — using {default}")
            return default

    def toggle_feature(self, feature_name: str, enabled: bool, updated_by: Optional[str] = None) -> bool:
        """
        Toggle a feature flag.

        Args:
            feature_name: Feature to toggle
            enabled: Enable or disable
            updated_by: User who made the change

        Returns:
            True if successful
        """
        return self.set_config(
            feature_name,
            "true" if enabled else "false",
            config_type="feature_flag",
            category="features",
            updated_by=updated_by
        )

    # ============================================================
    # Database Settings
    # ============================================================

    def get_database_config(self) -> Dict[str, Any]:
        """
        Get database configuration.

        Returns:
            Dict with database settings
        """
        return {
            "query_timeout_seconds": int(self.get_config("query_timeout_seconds", "30")),
            "max_result_rows": int(self.get_config("max_result_rows", "10000")),
        }

    # ============================================================
    # Cache Management
    # ============================================================

    def clear_cache(self):
        """Clear the in-memory cache."""
        self._cache.clear()

    def refresh_cache(self):
        """Refresh cache by reloading all active configs."""
        self.clear_cache()
        try:
            results = self.db.execute(
                text("SELECT config_key, config_value FROM admin_config WHERE is_active = 1")
            ).fetchall()

            for row in results:
                self._cache[row[0]] = row[1]

        except Exception as e:
            logger.warning(f"Failed to refresh cache: {e}")

    # ============================================================
    # Validation
    # ============================================================

    def validate_provider(self, provider: str) -> bool:
        """
        Check if provider is valid and enabled.
        Queries ai_providers table first, falls back to admin_config.

        Args:
            provider: Provider name

        Returns:
            True if valid and enabled
        """
        # Tier 1: Check DB
        try:
            row = self.db.execute(text(
                "SELECT 1 FROM ai_providers WHERE id = :id AND is_active = 1"
            ), {"id": provider}).fetchone()
            if row:
                enabled = self.get_config(f"{provider}_enabled", "true")
                return enabled == "true"
            # Provider exists in DB but inactive
            return False
        except Exception:
            pass

        # Tier 2: Fallback — check admin_config (for cases where DB table doesn't exist)
        enabled = self.get_config(f"{provider}_enabled", "false")
        return enabled == "true"

    def get_provider_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for provider with 3-tier resolution:
        1. DB (ai_providers.api_key_env_var → os.environ)
        2. admin_config table
        3. .env via settings object

        Args:
            provider: Provider name

        Returns:
            API key or None
        """
        # Tier 1: Try ai_providers table for env var name
        try:
            row = self.db.execute(text(
                "SELECT api_key_env_var FROM ai_providers WHERE id = :id"
            ), {"id": provider}).fetchone()
            if row and row[0]:
                env_var = row[0]  # e.g. "ANTHROPIC_API_KEY"
                # Try admin_config first (admin may have stored key in DB)
                api_key = self.get_config(env_var.lower(), use_cache=False)
                if not api_key:
                    api_key = os.environ.get(env_var, "")
                if not api_key:
                    api_key = getattr(settings, env_var, "")
                return api_key or None
        except Exception:
            pass

        # Tier 2-3: Hardcoded key_map fallback for built-in providers
        key_map = {
            "claude": ("anthropic_api_key", settings.ANTHROPIC_API_KEY),
            "gemini": ("google_ai_api_key", settings.GOOGLE_AI_API_KEY),
            "matcha": ("matcha_api_key", settings.MATCHA_AI_API_KEY)
        }

        if provider not in key_map:
            return None

        db_key, env_fallback = key_map[provider]
        api_key = self.get_config(db_key, use_cache=False)
        if not api_key:
            api_key = env_fallback

        return api_key

    def get_provider_record(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Get provider metadata from ai_providers.

        Returns:
            Provider metadata dict or None if not found
        """
        try:
            row = self.db.execute(text(
                """
                SELECT id, is_active, api_key_env_var, api_url_env_var, default_api_url
                FROM ai_providers
                WHERE id = :id
                LIMIT 1
                """
            ), {"id": provider}).fetchone()
        except Exception as e:
            logger.debug(f"Failed to load provider record for '{provider}': {e}")
            return None

        if not row:
            return None

        return {
            "id": row[0],
            "is_active": bool(row[1]),
            "api_key_env_var": row[2],
            "api_url_env_var": row[3],
            "default_api_url": row[4],
        }

    # ============================================================
    # Provider Management (NEW)
    # ============================================================

    def get_all_providers(self, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """
        Get all AI providers (including inactive).

        Args:
            include_inactive: Include inactive providers

        Returns:
            List of provider dicts
        """
        try:
            where_clause = "" if include_inactive else "WHERE p.is_active = 1"
            results = self.db.execute(
                text(f"""
                    SELECT
                        p.id,
                        p.name,
                        p.display_name,
                        p.icon,
                        p.is_active,
                        p.is_default,
                        p.api_key_env_var,
                        p.api_url_env_var,
                        p.default_api_url,
                        p.description,
                        p.priority,
                        m.model_id as default_model
                    FROM ai_providers p
                    LEFT JOIN ai_models m ON p.id = m.provider_id AND m.is_default = 1
                    {where_clause}
                    ORDER BY p.priority DESC, p.name
                """)
            ).fetchall()

            return [{
                "id": row[0],
                "name": row[1],
                "display_name": row[2],
                "icon": row[3],
                "is_active": bool(row[4]),
                "is_default": bool(row[5]),
                "api_key_env_var": row[6],
                "api_url_env_var": row[7],
                "default_api_url": row[8],
                "description": row[9],
                "priority": row[10],
                "default_model": row[11],
                "source": "database"
            } for row in results]

        except Exception as e:
            logger.error(f"Failed to get providers: {e}")
            fallback_providers = self.get_active_providers()
            return [{
                "id": provider["id"],
                "name": provider["name"],
                "display_name": provider.get("display_name"),
                "icon": provider.get("icon", "bulb"),
                "is_active": True,
                "is_default": provider.get("is_default", False),
                "api_key_env_var": None,
                "api_url_env_var": None,
                "default_api_url": None,
                "description": "Loaded from fallback configuration",
                "priority": 0,
                "default_model": provider.get("model"),
                "source": "fallback",
            } for provider in fallback_providers]

    def create_provider(
        self,
        provider_id: str,
        name: str,
        display_name: Optional[str] = None,
        icon: str = "bulb",
        api_key_env_var: Optional[str] = None,
        api_url_env_var: Optional[str] = None,
        default_api_url: Optional[str] = None,
        description: Optional[str] = None,
        priority: int = 0
    ) -> bool:
        """Create a new AI provider."""
        try:
            self.db.execute(
                text("""
                    INSERT INTO ai_providers (
                        id, name, display_name, icon, is_active, is_default,
                        api_key_env_var, api_url_env_var, default_api_url,
                        description, priority
                    ) VALUES (
                        :id, :name, :display_name, :icon, 1, 0,
                        :api_key_env_var, :api_url_env_var, :default_api_url,
                        :description, :priority
                    )
                """),
                {
                    "id": provider_id,
                    "name": name,
                    "display_name": display_name or name,
                    "icon": icon,
                    "api_key_env_var": api_key_env_var,
                    "api_url_env_var": api_url_env_var,
                    "default_api_url": default_api_url,
                    "description": description,
                    "priority": priority
                }
            )
            self.db.commit()
            self._sync_provider_runtime_config(provider_id, is_active=True)
            return True

        except Exception as e:
            logger.error(f"Failed to create provider: {e}")
            self.db.rollback()
            return False

    def update_provider(
        self,
        provider_id: str,
        name: Optional[str] = None,
        display_name: Optional[str] = None,
        icon: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        api_key_env_var: Optional[str] = None,
        api_url_env_var: Optional[str] = None,
        default_api_url: Optional[str] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None
    ) -> bool:
        """Update an existing AI provider."""
        try:
            updates = []
            params = {"id": provider_id}

            if name is not None:
                updates.append("name = :name")
                params["name"] = name

            if display_name is not None:
                updates.append("display_name = :display_name")
                params["display_name"] = display_name

            if icon is not None:
                updates.append("icon = :icon")
                params["icon"] = icon

            if is_active is not None:
                updates.append("is_active = :is_active")
                params["is_active"] = 1 if is_active else 0

            if is_default is not None:
                updates.append("is_default = :is_default")
                params["is_default"] = 1 if is_default else 0

                # If setting as default, unset others
                if is_default:
                    self.db.execute(
                        text("UPDATE ai_providers SET is_default = 0 WHERE id != :id"),
                        {"id": provider_id}
                    )

            if description is not None:
                updates.append("description = :description")
                params["description"] = description

            if api_key_env_var is not None:
                updates.append("api_key_env_var = :api_key_env_var")
                params["api_key_env_var"] = api_key_env_var

            if api_url_env_var is not None:
                updates.append("api_url_env_var = :api_url_env_var")
                params["api_url_env_var"] = api_url_env_var

            if default_api_url is not None:
                updates.append("default_api_url = :default_api_url")
                params["default_api_url"] = default_api_url

            if priority is not None:
                updates.append("priority = :priority")
                params["priority"] = priority

            if updates:
                sql = f"UPDATE ai_providers SET {', '.join(updates)} WHERE id = :id"
                self.db.execute(text(sql), params)
                self.db.commit()

            self._sync_provider_runtime_config(
                provider_id,
                is_active=is_active,
                is_default=is_default,
            )

            return True

        except Exception as e:
            logger.error(f"Failed to update provider: {e}")
            self.db.rollback()
            return False

    def delete_provider(self, provider_id: str) -> bool:
        """Delete an AI provider (CASCADE deletes models)."""
        try:
            self.db.execute(
                text("DELETE FROM ai_providers WHERE id = :id"),
                {"id": provider_id}
            )
            self.db.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to delete provider: {e}")
            self.db.rollback()
            return False

    # ============================================================
    # Model Management (NEW)
    # ============================================================

    def get_models_by_provider(self, provider_id: str, include_inactive: bool = False) -> List[Dict[str, Any]]:
        """Get all models for a provider."""
        try:
            where_clause = "AND m.is_active = 1" if not include_inactive else ""
            results = self.db.execute(
                text(f"""
                    SELECT
                        m.id,
                        m.provider_id,
                        m.model_id,
                        m.display_name,
                        m.is_active,
                        m.is_default,
                        m.context_window,
                        m.supports_vision,
                        m.cost_per_1m_tokens,
                        m.description,
                        m.priority,
                        m.tier
                    FROM ai_models m
                    WHERE m.provider_id = :provider
                    {where_clause}
                    ORDER BY m.priority DESC, m.display_name
                """),
                {"provider": provider_id}
            ).fetchall()

            return [{
                "id": row[0],
                "provider_id": row[1],
                "model_id": row[2],
                "display_name": row[3],
                "is_active": bool(row[4]),
                "is_default": bool(row[5]),
                "context_window": row[6],
                "supports_vision": bool(row[7]),
                "cost_per_1m_tokens": row[8],
                "description": row[9],
                "priority": row[10],
                "tier": row[11] or "default"
            } for row in results]

        except Exception as e:
            logger.error(f"Failed to get models: {e}")
            fallback_model_ids = self.get_available_models(provider_id)
            default_model = self.get_config(f"{provider_id}_model", "")
            return [{
                "id": index + 1,
                "provider_id": provider_id,
                "model_id": model_id,
                "display_name": model_id,
                "is_active": True,
                "is_default": model_id == default_model,
                "context_window": None,
                "supports_vision": False,
                "cost_per_1m_tokens": None,
                "description": "Loaded from fallback configuration",
                "priority": 0,
                "tier": "default",
            } for index, model_id in enumerate(fallback_model_ids)]

    def create_model(
        self,
        provider_id: str,
        model_id: str,
        display_name: Optional[str] = None,
        is_default: bool = False,
        context_window: Optional[int] = None,
        supports_vision: bool = False,
        description: Optional[str] = None,
        priority: int = 0,
        tier: Optional[str] = None
    ) -> bool:
        """Create a new AI model."""
        try:
            # If setting as default, unset other defaults for this provider
            if is_default:
                self.db.execute(
                    text("UPDATE ai_models SET is_default = 0 WHERE provider_id = :provider"),
                    {"provider": provider_id}
                )

            self.db.execute(
                text("""
                    INSERT INTO ai_models (
                        provider_id, model_id, display_name, is_active, is_default,
                        context_window, supports_vision, description, priority, tier
                    ) VALUES (
                        :provider, :model_id, :display_name, 1, :is_default,
                        :context_window, :supports_vision, :description, :priority, :tier
                    )
                """),
                {
                    "provider": provider_id,
                    "model_id": model_id,
                    "display_name": display_name or model_id,
                    "is_default": 1 if is_default else 0,
                    "context_window": context_window,
                    "supports_vision": 1 if supports_vision else 0,
                    "description": description,
                    "priority": priority,
                    "tier": tier or "default"
                }
            )
            self.db.commit()
            clear_model_tier_cache()
            if is_default:
                self._sync_provider_runtime_config(provider_id, default_model=model_id)
            return True

        except Exception as e:
            logger.error(f"Failed to create model: {e}")
            self.db.rollback()
            return False

    def update_model(
        self,
        model_pk_id: int,
        display_name: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_default: Optional[bool] = None,
        context_window: Optional[int] = None,
        supports_vision: Optional[bool] = None,
        description: Optional[str] = None,
        priority: Optional[int] = None,
        tier: Optional[str] = None
    ) -> bool:
        """Update an existing AI model."""
        try:
            # Get provider_id first
            result = self.db.execute(
                text("SELECT provider_id FROM ai_models WHERE id = :id"),
                {"id": model_pk_id}
            ).fetchone()

            if not result:
                return False

            provider_id = result[0]

            updates = []
            params = {"id": model_pk_id}

            if display_name is not None:
                updates.append("display_name = :display_name")
                params["display_name"] = display_name

            if is_active is not None:
                updates.append("is_active = :is_active")
                params["is_active"] = 1 if is_active else 0

            if is_default is not None:
                updates.append("is_default = :is_default")
                params["is_default"] = 1 if is_default else 0

                # If setting as default, unset others for this provider
                if is_default:
                    self.db.execute(
                        text("UPDATE ai_models SET is_default = 0 WHERE provider_id = :provider AND id != :id"),
                        {"provider": provider_id, "id": model_pk_id}
                    )

            if context_window is not None:
                updates.append("context_window = :context_window")
                params["context_window"] = context_window

            if supports_vision is not None:
                updates.append("supports_vision = :supports_vision")
                params["supports_vision"] = 1 if supports_vision else 0

            if description is not None:
                updates.append("description = :description")
                params["description"] = description

            if priority is not None:
                updates.append("priority = :priority")
                params["priority"] = priority

            if tier is not None:
                updates.append("tier = :tier")
                params["tier"] = tier

            if updates:
                sql = f"UPDATE ai_models SET {', '.join(updates)} WHERE id = :id"
                self.db.execute(text(sql), params)
                self.db.commit()
                clear_model_tier_cache()

            if is_default:
                default_model_id = self.db.execute(
                    text("SELECT model_id FROM ai_models WHERE id = :id"),
                    {"id": model_pk_id},
                ).fetchone()
                if default_model_id:
                    self._sync_provider_runtime_config(provider_id, default_model=default_model_id[0])

            return True

        except Exception as e:
            logger.error(f"Failed to update model: {e}")
            self.db.rollback()
            return False

    def delete_model(self, model_pk_id: int) -> bool:
        """Delete an AI model."""
        try:
            self.db.execute(
                text("DELETE FROM ai_models WHERE id = :id"),
                {"id": model_pk_id}
            )
            self.db.commit()
            clear_model_tier_cache()
            return True

        except Exception as e:
            logger.error(f"Failed to delete model: {e}")
            self.db.rollback()
            return False
