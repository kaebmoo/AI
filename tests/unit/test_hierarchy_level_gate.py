"""The level a question names reaches the prompt even when value lookup found nothing.

detect_hierarchy_level sat behind `if value_matches:` — "รายได้ บริการ 10 อันดับแรก" has no value to
look up, so it never learned that "บริการ" is the product level and was ranked per business group or
service group (plan/archive/RESULT_F11.md §7 Q9). With two_pass_enabled on (the live config), pass 1 is
where the dimension is chosen, so the level has to be there too.
"""

import pytest

from app.services.ai import hierarchy_context, hybrid_flow

LEVELS = [  # rows as master_hierarchy holds them (loaded by get_column_hierarchies)
    {"level": 0, "columns": ["bu"], "label_th": "กลุ่มธุรกิจ", "label_en": "Business Group",
     "detection_keywords": ["กลุ่มธุรกิจ", "ธุรกิจ"]},
    {"level": 1, "columns": ["service_group_nt"], "label_th": "กลุ่มบริการ", "label_en": "Service Group",
     "detection_keywords": ["กลุ่มบริการ"]},
    {"level": 2, "columns": ["product_name", "product_key"], "label_th": "บริการ/ผลิตภัณฑ์",
     "label_en": "Product/Service", "detection_keywords": ["บริการ", "รายบริการ", "แต่ละบริการ"]},
]


@pytest.fixture(autouse=True)
def feed_hierarchy(monkeypatch):
    get = lambda: {"feed_revenue": LEVELS}  # noqa: E731
    monkeypatch.setattr(hybrid_flow, "get_column_hierarchies", get)
    monkeypatch.setattr(hierarchy_context, "get_column_hierarchies", get)


class _Provider:
    def __init__(self, intent=None):
        self.prompts, self.intent = [], intent

    async def generate_structured(self, prompt, *a, **k):
        self.prompts.append(prompt)
        return self.intent

    async def generate_content(self, prompt, *a, **k):
        self.prompts.append(prompt)
        return "not json"


class _Service:
    def __init__(self, provider):
        self.provider = provider

    def parse_intent_json(self, text):
        return None

    def format_value_matches(self, *a, **k):
        return ""


async def _first_prompt(question: str, two_pass: bool, provider=None, domain_words=None):
    service = _Service(provider or _Provider())
    prompt, _ = await hybrid_flow.build_first_attempt_prompt(
        service=service, question=question, system_prompt="", history=None, context_name="feed_revenue",
        context_table="feed_revenue_fact_bu_monthly", context_thai="รายได้", two_pass_enabled=two_pass,
        cheap_model=None, detect_hierarchy_level=hierarchy_context.detect_hierarchy_level,
        format_value_matches=hierarchy_context.format_value_matches,
        get_vanna_context_string=lambda q: "", lookup_values_from_question=lambda q, c, t: [],  # nothing found
        on_status=None, attempt=0, max_retries=3, domain_words=domain_words)
    return prompt, service.provider


async def test_the_level_is_named_without_a_value_found():
    prompt, _ = await _first_prompt("รายได้ บริการ 10 อันดับแรก", two_pass=False)
    assert "ระดับชั้นที่คำถามพูดถึง: บริการ/ผลิตภัณฑ์ → คอลัมน์ `product_name`" in prompt
    assert "`product_key`" in prompt  # a code ("บริการ 102020019") has its column too


async def test_pass_one_chooses_the_dimension_with_it():
    provider = _Provider(intent={"intent_type": "ranking", "metrics": ["revenue"], "dimensions": ["product_name"]})
    prompt, provider = await _first_prompt("บริการใดมีการเติบโตมากสุด 10 อันดับแรก", two_pass=True, provider=provider)
    assert provider.prompts and "ระดับชั้นที่คำถามพูดถึง: บริการ/ผลิตภัณฑ์" in provider.prompts[0]
    assert "ระดับชั้นที่คำถามพูดถึง: บริการ/ผลิตภัณฑ์" in prompt  # pass 2


async def test_the_parent_level_wins_when_both_words_are_there():
    # "กลุ่มบริการ" contains "บริการ": the service group level, not the product level
    prompt, _ = await _first_prompt("รายได้ กลุ่มบริการ 10 อันดับแรก", two_pass=False)
    assert "ระดับชั้นที่คำถามพูดถึง: กลุ่มบริการ" in prompt


async def test_no_level_word_no_change():
    prompt, _ = await _first_prompt("รายได้ ปี 69 10 อันดับแรก", two_pass=False)
    assert "ระดับชั้นที่คำถามพูดถึง" not in prompt
    assert prompt == hybrid_flow.build_initial_user_prompt(
        question="รายได้ ปี 69 10 อันดับแรก", context_table="feed_revenue_fact_bu_monthly",
        context_thai="รายได้", rag_context="", value_lookup_text="")


async def test_a_word_the_context_is_routed_by_names_no_level(monkeypatch):
    """Legacy expense has "ค่าใช้จ่าย" as a keyword of its account level — and as the word every expense
    question carries. "ค่าใช้จ่ายรายฝ่าย" was sent to the account level (legacy eval #29, #32)."""
    levels = [{"level": 0, "columns": ["account_group_name"], "label_th": "หมวดค่าใช้จ่าย", "label_en": "Group",
               "detection_keywords": ["หมวด"]},
              {"level": 1, "columns": ["account_name"], "label_th": "รายการค่าใช้จ่าย", "label_en": "Item",
               "detection_keywords": ["ค่าใช้จ่าย", "บัญชี"]}]
    get = lambda: {"feed_revenue": levels}  # noqa: E731
    monkeypatch.setattr(hybrid_flow, "get_column_hierarchies", get)
    monkeypatch.setattr(hierarchy_context, "get_column_hierarchies", get)
    prompt, _ = await _first_prompt("ค่าใช้จ่ายรายฝ่าย ปี 2568", two_pass=False, domain_words=["ค่า", "ค่าใช้จ่าย"])
    assert "ระดับชั้นที่คำถามพูดถึง" not in prompt
    prompt, _ = await _first_prompt("ค่าใช้จ่ายรายบัญชี", two_pass=False, domain_words=["ค่า", "ค่าใช้จ่าย"])
    assert "ระดับชั้นที่คำถามพูดถึง: รายการค่าใช้จ่าย" in prompt  # its other words still name it
