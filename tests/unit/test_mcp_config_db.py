"""REMAIN-9.8: nt-metadata's tools read config tables → the MCP servers must get the config DB."""

import os


def test_metadata_server_prefers_the_config_db(monkeypatch):
    from mcp_servers.nt_metadata_mcp import DatabaseConfig
    monkeypatch.setenv("METADATA_DB_URL", "sqlite:///business.db")
    monkeypatch.setenv("CONFIG_DB_URL", "sqlite:///config.db")
    assert DatabaseConfig.from_env().connection_string == "sqlite:///config.db"
    monkeypatch.delenv("CONFIG_DB_URL")
    assert DatabaseConfig.from_env().connection_string == "sqlite:///business.db"  # single-DB setups


def test_client_passes_an_absolute_config_db_url(monkeypatch):
    from app.config import settings
    from app.services.mcp_client import MCPClientService
    monkeypatch.delenv("CONFIG_DB_URL", raising=False)
    monkeypatch.setattr(settings, "CONFIG_DB_URL", "sqlite:///./config.db")  # relative, as in a .env — not the dev's
    env = {c.name: c.env for c in MCPClientService()._load_server_configs()}["nt-metadata"]
    assert env["CONFIG_DB_URL"] == f"sqlite:///{os.path.abspath(settings.CONFIG_DB_URL[len('sqlite:///'):])}"
