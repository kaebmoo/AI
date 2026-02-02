"""
NT AI Assistant MCP Servers

Available servers:
- nt_metadata_mcp: Metadata, schema, mappings, and business rules (14 tools)
- nt_query_mcp: SQL validation, execution, and explanation (5 tools)

Usage:
    # Run metadata server
    python -m mcp_servers.nt_metadata_mcp

    # Run query server
    python -m mcp_servers.nt_query_mcp

Environment Variables:
    METADATA_DB_URL: Database connection string
        - SQLite: sqlite:///path/to/db.sqlite
        - PostgreSQL: postgresql://user:pass@host:port/dbname
        - MSSQL: mssql://user:pass@host:port/dbname
"""

__version__ = "1.0.0"
__all__ = ["nt_metadata_mcp", "nt_query_mcp"]
