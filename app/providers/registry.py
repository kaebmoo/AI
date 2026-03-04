"""
NT AI Assistant - Provider Registry
======================================
Auto-discover AI providers from app/providers/ directory.
Supports fallback when preferred provider is unavailable.
"""

import os
import importlib
import inspect
import logging
from typing import Dict, Optional, List

from app.providers.base import AIProvider
from app.config import settings

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """Auto-discover and manage AI providers"""

    def __init__(self):
        self.providers: Dict[str, type] = {}  # name -> class
        self._instances: Dict[str, AIProvider] = {}  # name -> instance (cache)

    def discover(self):
        """Scan app/providers/ directory for classes that inherit AIProvider"""
        providers_dir = os.path.dirname(__file__)
        skip_files = {"__init__", "base", "registry", "retry_config", "chart_postprocessor"}

        for filename in os.listdir(providers_dir):
            if not filename.endswith(".py"):
                continue
            module_name = filename[:-3]
            if module_name in skip_files:
                continue

            try:
                module = importlib.import_module(f"app.providers.{module_name}")
                for attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(attr_value, AIProvider)
                        and attr_value is not AIProvider
                        and hasattr(attr_value, 'name')
                        and attr_value.name
                    ):
                        self.providers[attr_value.name] = attr_value
                        logger.info(f"Discovered provider: {attr_value.name} ({attr_name})")
            except Exception as e:
                logger.warning(f"Failed to load provider from {filename}: {e}")

        logger.info(f"Provider registry: {list(self.providers.keys())}")

    def get_class(self, name: str) -> Optional[type]:
        """Get provider class by name"""
        return self.providers.get(name)

    def get_available(self) -> List[str]:
        """Return list of discovered provider names"""
        return list(self.providers.keys())

    def create_provider(self, name: str, **kwargs) -> Optional[AIProvider]:
        """
        Create a provider instance with the given configuration.
        Returns None if provider not found.
        """
        cls = self.providers.get(name)
        if not cls:
            logger.warning(f"Provider '{name}' not found in registry")
            return None

        try:
            if name == "claude":
                return cls(
                    api_key=kwargs.get("api_key", settings.ANTHROPIC_API_KEY or ""),
                    model=kwargs.get("model", settings.CLAUDE_MODEL),
                    extended_thinking=kwargs.get("extended_thinking", False),
                    thinking_budget_tokens=kwargs.get("thinking_budget_tokens", 8000),
                )
            elif name == "gemini":
                return cls(
                    api_key=kwargs.get("api_key", settings.GOOGLE_AI_API_KEY or ""),
                    model=kwargs.get("model", settings.GEMINI_MODEL),
                )
            elif name == "matcha":
                return cls(
                    api_key=kwargs.get("api_key", settings.MATCHA_AI_API_KEY or ""),
                    api_url=kwargs.get("api_url", settings.MATCHA_API_URL or ""),
                    model=kwargs.get("model", settings.MATCHA_MODEL),
                )
            else:
                # Generic: try to create with whatever kwargs match __init__
                sig = inspect.signature(cls.__init__)
                valid_kwargs = {k: v for k, v in kwargs.items() if k in sig.parameters}
                return cls(**valid_kwargs)
        except Exception as e:
            logger.error(f"Failed to create provider '{name}': {e}")
            return None

    def get_fallback(self, preferred: str, **kwargs) -> Optional[AIProvider]:
        """
        Try preferred provider first. If not available, fallback to first available.
        Returns a configured provider instance or None.
        """
        # Try preferred
        provider = self.create_provider(preferred, **kwargs)
        if provider and provider.is_configured():
            return provider

        # Fallback: try others
        for name in self.providers:
            if name == preferred:
                continue
            provider = self.create_provider(name, **kwargs)
            if provider and provider.is_configured():
                logger.info(f"Provider '{preferred}' not available, falling back to '{name}'")
                return provider

        return None


# Singleton instance
provider_registry = ProviderRegistry()

# Auto-discover on import
provider_registry.discover()
