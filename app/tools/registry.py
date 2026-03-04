"""
NT AI Assistant - Tool Registry
==================================
Auto-discover tools from app/tools/ directory.
"""

import os
import importlib
import inspect
import logging
from typing import Dict, Optional, List

from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Auto-discover and manage internal tools"""

    def __init__(self):
        self.tools: Dict[str, BaseTool] = {}

    def discover(self):
        """Scan app/tools/ directory for classes that inherit BaseTool"""
        tools_dir = os.path.dirname(__file__)
        skip_files = {"__init__", "base", "registry"}

        for filename in os.listdir(tools_dir):
            if not filename.endswith(".py"):
                continue
            module_name = filename[:-3]
            if module_name in skip_files:
                continue

            try:
                module = importlib.import_module(f"app.tools.{module_name}")
                for attr_name, attr_value in inspect.getmembers(module, inspect.isclass):
                    if (
                        issubclass(attr_value, BaseTool)
                        and attr_value is not BaseTool
                        and hasattr(attr_value, 'name')
                        and attr_value.name
                    ):
                        instance = attr_value()
                        self.tools[instance.name] = instance
                        logger.info(f"Discovered tool: {instance.name} ({attr_name})")
            except Exception as e:
                logger.warning(f"Failed to load tool from {filename}: {e}")

        logger.info(f"Tool registry: {list(self.tools.keys())}")

    def get(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name"""
        return self.tools.get(name)

    def get_all(self) -> List[BaseTool]:
        """Get all registered tools"""
        return list(self.tools.values())

    def get_all_specs(self) -> List[Dict]:
        """Get tool specs for all registered tools (for LLM function calling)"""
        return [tool.get_tool_spec() for tool in self.tools.values()]

    def get_names(self) -> List[str]:
        """Get names of all registered tools"""
        return list(self.tools.keys())


# Singleton
tool_registry = ToolRegistry()

# Auto-discover on import
tool_registry.discover()
