"""
Plan 1B-B: Admin MCP Server Unit Tests
=======================================
Tests the nt_admin_mcp.py MCP wrappers delegate to admin tools.
"""

import pytest
from unittest.mock import patch, AsyncMock, MagicMock


class TestAdminMCPToolsRegistered:
    """Verify admin MCP server has expected tools."""

    def test_admin_mcp_has_search_mappings(self):
        """MCP server exposes search_mappings tool."""
        from mcp_servers.nt_admin_mcp import search_mappings
        assert callable(search_mappings)

    def test_admin_mcp_has_add_mapping(self):
        """MCP server exposes add_mapping tool."""
        from mcp_servers.nt_admin_mcp import add_mapping
        assert callable(add_mapping)

    def test_admin_mcp_has_list_contexts(self):
        """MCP server exposes list_contexts tool."""
        from mcp_servers.nt_admin_mcp import list_contexts
        assert callable(list_contexts)

    def test_admin_mcp_has_refresh_cache(self):
        """MCP server exposes refresh_cache tool."""
        from mcp_servers.nt_admin_mcp import refresh_cache
        assert callable(refresh_cache)


class TestAdminMCPDelegation:
    """MCP tools delegate to admin tool classes."""

    @pytest.fixture(autouse=True)
    def _patch_db(self):
        with patch("mcp_servers.nt_admin_mcp._get_db") as mock_db:
            self.mock_db = MagicMock()
            mock_db.return_value = self.mock_db
            yield

    async def test_search_mappings_delegates(self):
        """search_mappings MCP tool delegates to SearchMappingsTool.execute."""
        with patch("app.tools.admin.mapping_tools.SearchMappingsTool") as MockTool:
            instance = MockTool.return_value
            instance.execute = AsyncMock(return_value={"mappings": [], "count": 0})
            from mcp_servers.nt_admin_mcp import search_mappings

            result = await search_mappings(keyword="datacom")
            instance.execute.assert_called_once()

    async def test_add_mapping_delegates(self):
        """add_mapping MCP tool delegates to AddMappingTool.execute."""
        with patch("app.tools.admin.mapping_tools.AddMappingTool") as MockTool:
            instance = MockTool.return_value
            instance.execute = AsyncMock(return_value={"success": True, "id": 1})
            from mcp_servers.nt_admin_mcp import add_mapping

            result = await add_mapping(
                keyword="datacom",
                target_column="SERVICE_GROUP",
                target_value="Datacom",
            )
            instance.execute.assert_called_once()

    async def test_search_rules_delegates(self):
        """search_rules MCP tool delegates to SearchRulesTool.execute."""
        with patch("app.tools.admin.rule_tools.SearchRulesTool") as MockTool:
            instance = MockTool.return_value
            instance.execute = AsyncMock(return_value={"rules": [], "count": 0})
            from mcp_servers.nt_admin_mcp import search_rules

            result = await search_rules(severity="error")
            instance.execute.assert_called_once()

    async def test_list_contexts_delegates(self):
        """list_contexts MCP tool delegates to ListContextsTool.execute."""
        with patch("app.tools.admin.system_tools.ListContextsTool") as MockTool:
            instance = MockTool.return_value
            instance.execute = AsyncMock(return_value={"contexts": [{"name": "revenue"}]})
            from mcp_servers.nt_admin_mcp import list_contexts

            result = await list_contexts()
            instance.execute.assert_called_once()
