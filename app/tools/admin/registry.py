"""
Admin Tool Registry
====================
Auto-discovers and registers admin tools from this package.
"""

import importlib
import inspect
import logging
import pkgutil
from typing import Dict, List, Optional

from app.tools.admin.base import AdminTool

logger = logging.getLogger(__name__)

SKIP_MODULES = {"__init__", "base", "registry"}


class AdminToolRegistry:
    """Registry for admin tools with auto-discovery."""

    def __init__(self):
        self.tools: Dict[str, AdminTool] = {}
        self._discovered = False

    def discover(self):
        """Auto-discover admin tools from app.tools.admin package."""
        if self._discovered:
            return

        import app.tools.admin as package
        package_path = package.__path__

        for importer, module_name, is_pkg in pkgutil.iter_modules(package_path):
            if module_name in SKIP_MODULES or is_pkg:
                continue

            try:
                module = importlib.import_module(f"app.tools.admin.{module_name}")

                for attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(attr_value, AdminTool)
                        and attr_value is not AdminTool
                        and getattr(attr_value, "name", "")
                    ):
                        instance = attr_value()
                        self.tools[instance.name] = instance
                        logger.debug(f"Registered admin tool: {instance.name}")

            except Exception as e:
                logger.warning(f"Failed to load admin tool module {module_name}: {e}")

        self._discovered = True
        logger.info(f"Discovered {len(self.tools)} admin tools")

    def get(self, name: str) -> Optional[AdminTool]:
        """Get a tool by name."""
        self.discover()
        return self.tools.get(name)

    def get_all(self) -> List[AdminTool]:
        """Get all registered tools."""
        self.discover()
        return list(self.tools.values())

    def get_all_specs(self) -> List[Dict]:
        """Get all tool specs for LLM function calling."""
        self.discover()
        return [tool.get_spec() for tool in self.tools.values()]

    def get_tools_by_category(self, category: str) -> List[AdminTool]:
        """Get tools filtered by category."""
        self.discover()
        return [t for t in self.tools.values() if t.category == category]


# Singleton
admin_tool_registry = AdminToolRegistry()
