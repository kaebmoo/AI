"""A contract's org_levels reach pass 1 as the level the question names (PLAN_METRICS_CONVERGENCE §6b, C-0b).

feed_revenue had only its product chain in master_hierarchy, so "กลุ่มไหนมีรายได้สูงสุด" — กลุ่ม is org level 2,
sub_division_name — was answered per business group 12 times in the generated eval (RESULT §C.6). The contract now
declares the org levels; sync writes them as `declared` rows at level 10+i beside the product chain (owner 2026-10-26:
one chain per tens), and the level note names the column.
"""

import json

import pytest
from sqlalchemy import text

from app.services import datafeed_knowledge as dk
from app.services.ai import hierarchy_context, hybrid_flow
from tests.unit import knowledge_db
from tests.unit.test_hierarchy_level_gate import _Provider, _Service

ORG = ["division_name", "division_sname", "sub_division_name", "sub_division_sname", "unit_name", "unit_sname",
       "sub_unit_name", "sub_unit_sname", "cost_center"]
ORG_LEVELS = [  # as revenue 2.5.0 declares them
    {"label_th": "สายงาน", "label_en": "Division", "columns": ["division_name", "division_sname"],
     "keywords": ["สายงาน", "รายสายงาน"]},
    {"label_th": "กลุ่ม", "label_en": "Sub-division", "columns": ["sub_division_name", "sub_division_sname"],
     "keywords": ["กลุ่มไหน", "รายกลุ่ม", "แต่ละกลุ่ม", "ตามกลุ่ม", "ทุกกลุ่ม", "ระดับกลุ่ม", "กลุ่มงาน", "กลุ่มขาย"]},
    {"label_th": "ฝ่าย", "label_en": "Unit", "columns": ["unit_name", "unit_sname"], "keywords": ["ฝ่าย", "รายฝ่าย"]},
    {"label_th": "ส่วน", "label_en": "Sub-unit", "columns": ["sub_unit_name", "sub_unit_sname"],
     "keywords": ["ส่วนไหน", "รายส่วน", "แต่ละส่วน", "ตามส่วน", "ทุกส่วน", "ระดับส่วน", "ส่วนงาน", "ส่วนขาย",
                  "ส่วนบริการ"]},
    {"label_th": "ศูนย์ต้นทุน", "label_en": "Cost center", "columns": ["cost_center"],
     "keywords": ["ศูนย์ต้นทุน", "cost center", "cost_center", "รายศูนย์"]},
]
PRODUCT = [  # the person's product chain of the live config.db (ids 23–25)
    (0, "กลุ่มธุรกิจ", "Business Group", ["bu", "bu_seq"], ["กลุ่มธุรกิจ", "ธุรกิจ", "business group", "business"]),
    (1, "กลุ่มบริการ", "Service Group", ["service_group_nt", "service_group_seq"], ["กลุ่มบริการ", "service group"]),
    (2, "บริการ/ผลิตภัณฑ์", "Product/Service", ["product_name", "product_key"],
     ["ผลิตภัณฑ์", "product", "สินค้า", "บริการ", "แต่ละบริการ", "รายบริการ", "service"]),
]


@pytest.fixture
def contract():
    return {
        "domain": "revenue", "schema_version": "2.5.0", "primary_dataset": "fact_total_monthly",
        "period_key": "year_month", "org_levels": json.loads(json.dumps(ORG_LEVELS)),
        "datasets": [
            {"name": "fact_bu_monthly", "columns": [{"name": c, "dtype": "string"} for c in ("year_month", "bu")]},
            {"name": "fact_org_monthly", "columns": [{"name": c, "dtype": "string"} for c in ["year_month", *ORG]]
             + [{"name": "revenue", "dtype": "double"}]},
        ],
    }


@pytest.fixture
def engine(tmp_path):
    engine = knowledge_db.make(tmp_path / "config.db")
    with engine.begin() as conn:
        for level, th, en, columns, words in PRODUCT:
            conn.execute(text(
                "INSERT INTO master_hierarchy (context_name, level, level_label_th, level_label_en, level_columns, "
                "detection_keywords, source) VALUES ('feed_revenue', :l, :th, :en, :c, :k, 'manual')"),
                {"l": level, "th": th, "en": en, "c": json.dumps(columns, ensure_ascii=False),
                 "k": json.dumps(words, ensure_ascii=False)})
    yield engine
    engine.dispose()


def sync(engine, contract):
    with engine.begin() as conn:
        dk.sync_knowledge(conn, "revenue", contract)


def rows(engine):
    with engine.connect() as conn:
        return {r["level"]: dict(r) for r in conn.execute(text(
            "SELECT level, level_label_th, level_columns, detection_keywords, source, status FROM master_hierarchy "
            "WHERE context_name = 'feed_revenue'")).mappings()}


def test_org_levels_are_declared_beside_the_product_chain(engine, contract):
    sync(engine, contract)
    stored = rows(engine)
    assert sorted(stored) == [0, 1, 2, 10, 11, 12, 13, 14]
    assert {stored[n]["source"] for n in (0, 1, 2)} == {"manual"}
    assert {stored[n]["source"] for n in range(10, 15)} == {"declared"}
    assert json.loads(stored[11]["level_columns"]) == ["sub_division_name", "sub_division_sname"]
    assert stored[11]["level_label_th"] == "กลุ่ม" and "กลุ่มไหน" in json.loads(stored[11]["detection_keywords"])
    sync(engine, contract)
    assert rows(engine) == stored  # idempotent


def test_a_persons_level_wins_and_withdrawal_takes_only_the_contracts_own(engine, contract):
    sync(engine, contract)
    with engine.begin() as conn:  # a person edits the กลุ่ม level
        conn.execute(text("UPDATE master_hierarchy SET detection_keywords = '[\"กลุ่มงาน\"]', source = 'manual' "
                          "WHERE context_name = 'feed_revenue' AND level = 11"))
    contract["org_levels"][1]["keywords"].append("กลุ่มขายและปฏิบัติการ")
    sync(engine, contract)
    assert json.loads(rows(engine)[11]["detection_keywords"]) == ["กลุ่มงาน"]
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM knowledge_proposals WHERE table_name = 'master_hierarchy'")
                            ).scalar() == 1  # the contract's version waits for the person
    contract["org_levels"][4]["columns"] = ["no_such_column"]  # a level the contract cannot back is not written
    sync(engine, contract)
    assert 14 not in rows(engine)
    del contract["org_levels"]
    sync(engine, contract)
    assert sorted(rows(engine)) == [0, 1, 2, 11]


LEVELS = [{"level": n, "label_th": th, "label_en": en, "columns": c, "detection_keywords": k}
          for n, th, en, c, k in PRODUCT] + [
    {"level": 10 + i, "label_th": level["label_th"], "label_en": level["label_en"], "columns": level["columns"],
     "detection_keywords": level["keywords"]} for i, level in enumerate(ORG_LEVELS)]


@pytest.mark.parametrize("question, named", [
    ("กลุ่มไหนมีรายได้ (ตามรายงานรายได้) เดือนกันยายน 2569สูงสุด 5 อันดับ", ["กลุ่ม"]),
    ("รายได้ (ตามรายงานรายได้)แยกตามกลุ่ม เดือนกันยายน 2569", ["กลุ่ม"]),
    ("ส่วนไหนมีรายได้สะสมปี 2569 สูงสุด 10 อันดับ", ["ส่วน"]),
    ("รายได้แยกตามกลุ่มธุรกิจ", ["กลุ่มธุรกิจ"]),  # "ตามกลุ่ม" runs on into กลุ่มธุรกิจ
    ("รายได้แต่ละกลุ่มบริการ", ["กลุ่มบริการ"]),
    ("สัดส่วนรายได้ตามกลุ่มธุรกิจ", ["กลุ่มธุรกิจ"]),  # no bare "ส่วน"
    ("รายได้กลุ่ม Fixed Line", []),  # bare "กลุ่ม" names no level (owner 2026-10-26): the value found decides
    ("บริการ 10 อันดับแรกของฝ่ายขายภาคใต้", ["บริการ/ผลิตภัณฑ์", "ฝ่าย"]),
])
def test_the_question_names_its_level(question, named):
    assert [level["label_th"] for level in hierarchy_context.named_levels(question, LEVELS)] == named


def test_the_note_shows_the_chain_of_the_named_level():
    note = hierarchy_context.format_level_note(LEVELS, hierarchy_context.named_levels("กลุ่มไหนรายได้สูงสุด", LEVELS))
    assert "ระดับชั้นที่คำถามพูดถึง: กลุ่ม → คอลัมน์ `sub_division_name`**" in note
    assert "สายงาน (`division_name`) > กลุ่ม (`sub_division_name`) > ฝ่าย" in note and "`bu`" not in note
    both = hierarchy_context.format_level_note(LEVELS, hierarchy_context.named_levels("บริการ ของฝ่าย X", LEVELS))
    assert "กลุ่มธุรกิจ (`bu`) > กลุ่มบริการ" in both and " · สายงาน (`division_name`) >" in both


def test_the_system_prompt_rule_keeps_the_chains_apart(engine, contract):
    """STEP 1.5 of the system prompt read every level as one chain: กลุ่มธุรกิจ > … > บริการ/ผลิตภัณฑ์ > สายงาน > …"""
    from app.services.schema_service import SchemaService
    sync(engine, contract)
    rule = SchemaService(config_engine=engine, business_engine=engine).build_hierarchy_rule_text("feed_revenue")
    assert ("ข้อมูลมีลำดับชั้น: กลุ่มธุรกิจ > กลุ่มบริการ > บริการ/ผลิตภัณฑ์ · "
            "สายงาน > กลุ่ม > ฝ่าย > ส่วน > ศูนย์ต้นทุน") in rule
    assert "WHERE bu LIKE '%x%' OR service_group_nt LIKE '%x%'" in rule


@pytest.fixture
def hierarchy_from(monkeypatch):
    """load_hierarchies_from_db on a given config DB, its cache empty before and after."""
    def use(path):
        monkeypatch.setattr(hierarchy_context.settings, "CONFIG_DB_URL", f"sqlite:///{path}")
        hierarchy_context.get_hierarchy_cache().clear()
    yield use
    hierarchy_context.get_hierarchy_cache().clear()


async def test_the_synced_level_reaches_pass_one(tmp_path, engine, contract, hierarchy_from):
    """Contract → sync → master_hierarchy → pass 1's prompt: the layer a single-question eval cannot see."""
    sync(engine, contract)
    hierarchy_from(tmp_path / "config.db")
    provider = _Provider(intent={"intent_type": "ranking", "metrics": ["revenue"], "dimensions": ["sub_division_name"]})
    await hybrid_flow.build_first_attempt_prompt(
        service=_Service(provider), question="กลุ่มไหนมีรายได้สูงสุด 5 อันดับ", system_prompt="", history=None,
        context_name="feed_revenue", context_table="feed_revenue_fact_total_monthly", context_thai="รายได้",
        two_pass_enabled=True, cheap_model=None, detect_hierarchy_level=hierarchy_context.detect_hierarchy_level,
        format_value_matches=hierarchy_context.format_value_matches, get_vanna_context_string=lambda q: "",
        lookup_values_from_question=lambda q, c, t: [], on_status=None, attempt=0, max_retries=3,
        domain_words=["รายได้", "revenue", "income"])
    assert provider.prompts, "pass 1 was not asked"
    assert "ระดับชั้นที่คำถามพูดถึง: กลุ่ม → คอลัมน์ `sub_division_name`**" in provider.prompts[0]
