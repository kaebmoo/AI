"""
Admin Tools for NT AI Assistant
================================
Tool-calling interface for admin operations via LLM agent.
"""

from app.tools.admin.registry import admin_tool_registry

__all__ = ["admin_tool_registry"]
