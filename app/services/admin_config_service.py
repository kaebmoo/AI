"""
NT AI Assistant - Admin Configuration Service
==============================================
Service for managing runtime configuration with fallback mechanism:
1. Database (admin_config table) - First priority
2. Environment variables (.env) - Fallback
3. Hardcoded defaults - Safety net
"""

from typing import Optional, Dict, List, Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class AdminConfigService:
    """
    Manages configuration with database + .env fallback.
    """

    def __init__(self, db: Session):
        self.db = db
        self._cache = {}  # Simple in-memory cache

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

        Returns:
            Dict with provider, models, and enabled status
        """
        return {
            # Default provider (with fallback)
            "default_provider": self.get_config("default_ai_provider", "matcha"),

            # Provider enabled status
            "claude_enabled": self.get_config("claude_enabled", "true") == "true",
            "gemini_enabled": self.get_config("gemini_enabled", "true") == "true",
            "matcha_enabled": self.get_config("matcha_enabled", "true") == "true",

            # Model names
            "claude_model": self.get_config("claude_model", settings.CLAUDE_MODEL),
            "gemini_model": self.get_config("gemini_model", settings.GEMINI_MODEL),
            "matcha_model": self.get_config("matcha_model", settings.MATCHA_MODEL),

            # API URLs (for display, not secrets)
            "matcha_api_url": self.get_config("matcha_api_url", settings.MATCHA_API_URL or ""),
        }

    def update_ai_config(
        self,
        default_provider: Optional[str] = None,
        claude_enabled: Optional[bool] = None,
        gemini_enabled: Optional[bool] = None,
        matcha_enabled: Optional[bool] = None,
        claude_model: Optional[str] = None,
        gemini_model: Optional[str] = None,
        matcha_model: Optional[str] = None,
        matcha_api_url: Optional[str] = None,
        updated_by: Optional[str] = None
    ) -> bool:
        """
        Update AI configuration.

        Args:
            default_provider: Default provider to use
            *_enabled: Enable/disable providers
            *_model: Model names for each provider
            matcha_api_url: Matcha gateway URL
            updated_by: User who made changes

        Returns:
            True if all updates successful
        """
        updates = {
            "default_ai_provider": default_provider,
            "claude_enabled": "true" if claude_enabled else "false" if claude_enabled is False else None,
            "gemini_enabled": "true" if gemini_enabled else "false" if gemini_enabled is False else None,
            "matcha_enabled": "true" if matcha_enabled else "false" if matcha_enabled is False else None,
            "claude_model": claude_model,
            "gemini_model": gemini_model,
            "matcha_model": matcha_model,
            "matcha_api_url": matcha_api_url,
        }

        success = True
        for key, value in updates.items():
            if value is not None:
                # Determine type
                if "enabled" in key or "default" in key:
                    config_type = "ai_provider"
                elif "model" in key:
                    config_type = "model"
                else:
                    config_type = "api_key"

                if not self.set_config(key, str(value), config_type, "ai", updated_by):
                    success = False

        return success

    def get_active_providers(self) -> List[Dict[str, Any]]:
        """
        Get list of active AI providers.

        Returns:
            List of provider info dicts
        """
        config = self.get_ai_config()
        providers = []

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

    def get_available_models(self, provider: str) -> List[str]:
        """
        Get available models for a provider.

        Args:
            provider: Provider name (claude, gemini, matcha)

        Returns:
            List of model names
        """
        # Hardcoded for now - could be fetched from API in future
        models = {
            "claude": [
                "claude-sonnet-4-5-20250929",
                "claude-sonnet-4-20250514",
                "claude-opus-4-20250514",
                "claude-haiku-3-5-20241022"
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

        return models.get(provider, [])

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
        }

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

        Args:
            provider: Provider name

        Returns:
            True if valid and enabled
        """
        if provider not in ["claude", "gemini", "matcha"]:
            return False

        enabled = self.get_config(f"{provider}_enabled", "false")
        return enabled == "true"

    def get_provider_api_key(self, provider: str) -> Optional[str]:
        """
        Get API key for provider.
        Tries database first, then falls back to settings.

        Args:
            provider: Provider name

        Returns:
            API key or None
        """
        # Map provider to key names
        key_map = {
            "claude": ("anthropic_api_key", settings.ANTHROPIC_API_KEY),
            "gemini": ("google_ai_api_key", settings.GOOGLE_AI_API_KEY),
            "matcha": ("matcha_api_key", settings.MATCHA_AI_API_KEY)
        }

        if provider not in key_map:
            return None

        db_key, env_fallback = key_map[provider]

        # Try database first
        api_key = self.get_config(db_key, use_cache=False)  # Don't cache sensitive data

        # Fallback to environment
        if not api_key:
            api_key = env_fallback

        return api_key
