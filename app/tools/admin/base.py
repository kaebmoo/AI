"""
Admin Tool Base Class
======================
Abstract base for all admin tools. Each tool wraps an existing admin API
endpoint, providing a structured interface for LLM function calling.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class AdminTool(ABC):
    """Base class for admin tools used by the Admin Agent."""

    # Tool identity
    name: str = ""
    description: str = ""  # English description for LLM
    description_th: str = ""  # Thai description for UI display
    category: str = ""  # grouping: mapping, rule, example, onboarding, analysis, system

    # Safety
    requires_confirmation: bool = False  # If True, agent asks user to confirm before executing

    @property
    @abstractmethod
    def parameters_schema(self) -> Dict[str, Any]:
        """JSON Schema for tool parameters (OpenAI function calling format).

        Returns:
            Dict with 'type', 'properties', 'required' keys.
        """
        ...

    @abstractmethod
    async def execute(self, params: Dict[str, Any], db) -> Dict[str, Any]:
        """Execute the tool with given parameters.

        Args:
            params: Validated parameters matching parameters_schema.
            db: SQLAlchemy session.

        Returns:
            Dict with at least:
                - success: bool
                - message: str (Thai)
                - data: Any (optional result data)
        """
        ...

    def get_spec(self) -> Dict[str, Any]:
        """Get tool specification for LLM function calling."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }
