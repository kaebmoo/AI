"""
NT AI Assistant - Tool Base Class
====================================
Abstract base class for internal tools.

Pattern from OpenMiniCrew tools/base.py:
- Each tool is a single file in app/tools/
- Auto-discovered by registry on import
- preferred_tier controls LLM cost when tool needs AI
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class BaseTool(ABC):
    """Base class for internal tools"""

    name: str = ""
    description: str = ""
    description_th: str = ""  # For display in Thai UI
    preferred_tier: str = "cheap"  # cheap = Haiku/Flash, mid = Sonnet/Pro

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the tool.

        Returns:
            Dict with at least {"success": bool, ...}
        """
        ...

    def get_tool_spec(self) -> Dict[str, Any]:
        """Return generic tool spec for LLM function calling"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        }

    def __repr__(self) -> str:
        return f"<Tool: {self.name}>"
