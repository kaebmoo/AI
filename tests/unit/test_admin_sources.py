"""Plan 7 Phase 4c — sources through the admin API.

Exit: registering through the API writes what the CLI writes; a failed gate leaves the registry
untouched; the API reads a new bundle only from a configured root."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.api.v1.admin import sources as api
from app.services import datafeed_knowledge as dk
from app.services import source_registration as registration
from scripts.migrate_data_sources import migrate
from scripts.migrate_workspaces import migrate_config
from tests.unit.test_datafeed_import import CONTRACT
from tests.unit.test_datafeed_import import _write_bundle as _write_importer_bundle

ADMIN = SimpleNamespace(id=1)


def _write_bundle(path, complete=True, **kwargs):
    """The importer's test bundle; its contract lacks what only registration needs."""
    import yaml

    path.mkdir(parents=True, exist_ok=True)
    dist = _write_importer_bundle(path, **kwargs)
    contract = {**CONTRACT, "primary_dataset": "fact_bu", "title": "Rev feed", "period_key": "year_month"}
    if not complete:
        del contract["schema_version"]  # knowledge generation needs it
    (path / "contracts" / "rev.yaml").write_text(yaml.safe_dump(contract, allow_unicode=True))
    return dist


def _config(path):
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE schema_contexts (id INTEGER PRIMARY KEY, name TEXT UNIQUE, display_name TEXT, "
                          "description TEXT, main_view TEXT, is_active BOOLEAN DEFAULT 1, priority INTEGER DEFAULT 0, "
                          "keywords TEXT, instruction_th TEXT, updated_at TIMESTAMP)"))
        conn.execute(text("CREATE TABLE schema_metadata (id INTEGER PRIMARY KEY, table_name TEXT, column_name TEXT, "
                          "description TEXT, data_type TEXT, is_summable BOOLEAN, is_groupable BOOLEAN)"))
        conn.execute(text("CREATE TABLE vanna_documentation (id INTEGER PRIMARY KEY, doc_key TEXT UNIQUE, title TEXT, "
                          "content TEXT, category TEXT, context_name TEXT, is_active INTEGER)"))
    migrate(engine)
    migrate_config(engine)
    return engine


def _registry(engine):
    with engine.connect() as conn:
        return ([tuple(r) for r in conn.execute(text("SELECT name, source_type, manifest_file, is_active FROM data_sources ORDER BY name"))],
                [tuple(r) for r in conn.execute(text("SELECT table_name, file_name, columns, sha256 FROM source_tables ORDER BY table_name"))],
                [tuple(r) for r in conn.execute(text("SELECT name, main_view, is_active, instruction_th FROM schema_contexts ORDER BY name"))])


@pytest.fixture(autouse=True)
def _no_brain_marker():
    with patch.object(dk, "mark_brain_dirty"):
        yield


def _post(engine, **body):
    with patch("app.db.session.config_engine", engine):
        return asyncio.run(api.register_source(api.SourceRegisterRequest(**body), ADMIN))


def test_api_registration_writes_what_the_cli_writes(tmp_path):
    dist = _write_bundle(tmp_path)
    by_cli, by_api = _config(tmp_path / "cli.db"), _config(tmp_path / "api.db")
    registration.register_domain(by_cli, "rev", dist)  # what scripts/datafeed/register_file_source.py calls
    with patch.object(api.settings, "DATA_SOURCE_ALLOWED_ROOTS", str(tmp_path)):
        done = _post(by_api, domain="rev", source_dir=str(dist))
    assert done["status"] == "success" and done["context"] == "feed_rev" and done["views"] == 2
    assert _registry(by_api) == _registry(by_cli)
    # …and re-registering needs no path: it is read from where the domain already is
    assert _post(by_api, domain="rev")["views"] == 2


def test_failed_gate_is_400_and_the_registry_is_untouched(tmp_path):
    good = _write_bundle(tmp_path / "good")
    engine = _config(tmp_path / "config.db")
    registration.register_domain(engine, "rev", good)
    before = _registry(engine)
    bad = _write_bundle(tmp_path / "bad", bad_control=True)
    with patch.object(api.settings, "DATA_SOURCE_ALLOWED_ROOTS", str(tmp_path)), pytest.raises(HTTPException) as exc:
        _post(engine, domain="rev", source_dir=str(bad))
    assert exc.value.status_code == 400 and "control totals" in exc.value.detail
    assert _registry(engine) == before


@pytest.mark.parametrize("roots", ["", "/somewhere/else"])
def test_new_path_outside_the_configured_roots_is_refused_unread(tmp_path, roots):
    dist = _write_bundle(tmp_path)
    engine = _config(tmp_path / "config.db")
    with patch.object(api.settings, "DATA_SOURCE_ALLOWED_ROOTS", roots), \
         patch.object(registration, "load_bundle") as load, pytest.raises(HTTPException) as exc:
        _post(engine, domain="rev", source_dir=str(dist))
    assert exc.value.status_code == 400 and not load.called
    assert _registry(engine)[1] == []


def test_symlink_out_of_the_root_does_not_pass(tmp_path):
    outside = _write_bundle(tmp_path / "outside")
    (tmp_path / "allowed").mkdir()
    (tmp_path / "allowed" / "link").symlink_to(outside)
    with pytest.raises(registration.GateError):
        registration.allowed_dist(str(tmp_path / "allowed" / "link"), [str(tmp_path / "allowed")])
    assert registration.allowed_dist(str(outside), [str(tmp_path / "outside")]) == outside


def test_malformed_contract_is_400_not_500_and_writes_nothing(tmp_path):
    dist = _write_bundle(tmp_path, complete=False)  # no schema_version
    engine = _config(tmp_path / "config.db")
    with patch.object(api.settings, "DATA_SOURCE_ALLOWED_ROOTS", str(tmp_path)), pytest.raises(HTTPException) as exc:
        _post(engine, domain="rev", source_dir=str(dist))
    assert exc.value.status_code == 400 and "schema_version" in exc.value.detail
    assert _registry(engine)[1] == [] and [r[0] for r in _registry(engine)[0]] == ["legacy"]


def test_unregistered_domain_without_a_path_and_bad_domain_names(tmp_path):
    engine = _config(tmp_path / "config.db")
    with pytest.raises(HTTPException) as exc:
        _post(engine, domain="rev")
    assert exc.value.status_code == 400
    with pytest.raises(ValueError):  # pydantic: the name goes into table names and paths
        api.SourceRegisterRequest(domain="../x")
    with pytest.raises(registration.GateError):
        registration.register_domain(engine, "Rev;", tmp_path)


def test_listing_and_status(tmp_path):
    dist = _write_bundle(tmp_path)
    engine = _config(tmp_path / "config.db")
    registration.register_domain(engine, "rev", dist)
    db = sessionmaker(bind=engine)()
    listed = {s["name"]: s for s in api.list_sources(ADMIN, db)}
    assert listed["datafeed_rev"]["tables"] == 2 and listed["legacy"]["source_type"] == "legacy"
    assert listed["datafeed_rev"]["contexts"] == [{"name": "feed_rev", "is_active": True, "main_view": "feed_rev_fact_bu", "workspace": "default"}]

    from app.services.data_sources import SourceResolver
    with patch("app.services.data_sources.source_resolver", SourceResolver(config_engine=engine, cache_dir=str(tmp_path / "cache"))):
        status = api.source_status("datafeed_rev", ADMIN, db)
        assert status["ok"] and status["data_as_of"]["period"] == "202402" and status["views"] == 2
        (dist / "rev" / "latest" / "fact_bu.csv").write_text("year_month,bu,bu_code,revenue\n")  # tampered build
        broken = api.source_status("datafeed_rev", ADMIN, db)
        assert broken["ok"] is False and broken["error"]
    with pytest.raises(HTTPException) as exc:
        api.source_status("nope", ADMIN, db)
    assert exc.value.status_code == 404
    assert json.dumps(listed)  # serialisable
