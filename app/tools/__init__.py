"""
NT AI Assistant - Internal Tools Package
==========================================
Auto-discoverable tools for extending AI capabilities
beyond database queries (e.g., report export, trending analysis).

Usage:
    from app.tools.registry import tool_registry
    tool = tool_registry.get("report_export")
    result = await tool.execute(data=[...], format="xlsx")
"""

from app.tools.registry import tool_registry

__all__ = ["tool_registry"]
