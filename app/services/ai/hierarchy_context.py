import json
import logging
import re
from typing import Any, Dict, List, Optional
import sqlite3

from app.config import settings


logger = logging.getLogger(__name__)

RECOVERABLE_HIERARCHY_EXCEPTIONS = (AttributeError, ImportError, OSError, RuntimeError, TypeError, ValueError, json.JSONDecodeError, sqlite3.Error)

_HIERARCHY_CACHE: Dict[str, List[Dict]] = {}
_HIERARCHY_CACHE_TS: float = 0.0
_HIERARCHY_CACHE_TTL: float = 3600.0

_HARDCODED_HIERARCHIES: Dict[str, List[Dict]] = {
    "pl_costtype": [
        {"level": 0, "columns": ["business_unit"], "label_th": "กลุ่มธุรกิจ", "label_en": "Business Unit", "detection_keywords": ["กลุ่มธุรกิจ", "business unit", "ธุรกิจ"]},
        {"level": 1, "columns": ["service_group"], "label_th": "กลุ่มบริการ", "label_en": "Service Group", "detection_keywords": ["กลุ่มบริการ", "service group"]},
        {"level": 2, "columns": ["product_name"], "label_th": "ผลิตภัณฑ์/บริการ", "label_en": "Product", "detection_keywords": ["ผลิตภัณฑ์", "product", "สินค้า"]},
    ],
    "revenue": [
        {"level": 0, "columns": ["BUSINESS_GROUP", "BUSINESS"], "label_th": "กลุ่มธุรกิจ", "label_en": "Business Group", "detection_keywords": ["กลุ่มธุรกิจ", "ธุรกิจ", "business group", "business"]},
        {"level": 1, "columns": ["SERVICE_GROUP"], "label_th": "กลุ่มบริการ", "label_en": "Service Group", "detection_keywords": ["กลุ่มบริการ", "service group", "กลุ่ม"]},
        {"level": 2, "columns": ["PRODUCT_NAME", "PRODUCT"], "label_th": "ผลิตภัณฑ์/บริการ", "label_en": "Product/Service", "detection_keywords": ["ผลิตภัณฑ์", "product", "สินค้า", "บริการ", "แต่ละบริการ", "รายบริการ", "service"]},
    ],
}

COLUMN_HIERARCHIES = _HARDCODED_HIERARCHIES

THAI_STOP_WORDS = {
    "รายได้", "ค่าใช้จ่าย", "บริการ",
    "เท่าไหร่", "เท่าไร", "อะไร", "อยากรู้", "ไหน", "ยังไง", "เมื่อไร",
    "ทั้งหมด", "รวม", "แยก", "ตาม", "ราย", "เดือน", "ปี", "ไตรมาส",
    "รายเดือน", "รายไตรมาส", "รายปี",
    "เปรียบเทียบ", "เทียบ", "กับ", "และ", "ของ", "ที่", "ใน", "จาก",
    "มี", "ให้", "ดู", "หา", "แสดง", "สรุป", "วิเคราะห์",
    "มากสุด", "น้อยสุด", "สูงสุด", "ต่ำสุด", "มาก", "น้อย", "สุด",
    "อันดับ", "อันดับแรก", "แรก", "หลัง", "ล่าสุด",
    "หน่วยงาน", "ส่วนงาน",
    "the", "of", "and", "for", "by", "in", "to", "a", "is",
    "total", "sum", "count", "group", "show", "revenue", "expense",
}


def load_hierarchies_from_db() -> Dict[str, List[Dict]]:
    import time as _time

    now = _time.time()
    if _HIERARCHY_CACHE and (now - _HIERARCHY_CACHE_TS) < _HIERARCHY_CACHE_TTL:
        return _HIERARCHY_CACHE

    try:
        config_url = settings.CONFIG_DB_URL or settings.DATABASE_URL
        db_path = config_url.replace("sqlite:///", "").replace("sqlite://", "")
        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT context_name, level, level_label_th, level_label_en, level_columns, detection_keywords "
            "FROM master_hierarchy WHERE is_active = 1 ORDER BY context_name, level"
        ).fetchall()
        conn.close()

        result: Dict[str, List[Dict]] = {}
        for ctx, level, label_th, label_en, columns_json, keywords_json in rows:
            result.setdefault(ctx, []).append({
                "level": level,
                "columns": json.loads(columns_json),
                "label_th": label_th,
                "label_en": label_en,
                "detection_keywords": json.loads(keywords_json),
            })

        if result:
            _HIERARCHY_CACHE.clear()
            _HIERARCHY_CACHE.update(result)
            globals()["_HIERARCHY_CACHE_TS"] = now
            logger.info("Loaded hierarchies from DB: %s", list(result.keys()))
            return _HIERARCHY_CACHE
    except RECOVERABLE_HIERARCHY_EXCEPTIONS as exc:
        logger.warning("Could not load hierarchies from DB: %s, using fallback", exc)

    return _HARDCODED_HIERARCHIES


def get_column_hierarchies() -> Dict[str, List[Dict]]:
    return load_hierarchies_from_db()


def get_hierarchy_cache() -> Dict[str, List[Dict]]:
    return _HIERARCHY_CACHE


def get_vanna_context_string(service: Any, question: str) -> str:
    try:
        if not service.vanna:
            return ""
        contexts = service.vanna.get_rag_context(question)

        parts = []
        if contexts.get("ddl"):
            parts.append("### Relevant Tables (Schema):")
            parts.extend(contexts["ddl"])
        if contexts.get("doc"):
            parts.append("\n### Relevant Rules & Dictionary:")
            parts.extend(contexts["doc"])
        if contexts.get("sql"):
            parts.append("\n### Similar Examples (Golden SQL):")
            for sql in contexts["sql"]:
                parts.append(f"- {sql}")

        if not parts:
            return ""
        return "\n".join(parts)
    except RECOVERABLE_HIERARCHY_EXCEPTIONS as exc:
        logger.error("Error getting Vanna context: %s", exc)
        return ""


def extract_keywords_from_question(_service: Any, question: str, context_name: str = None) -> List[str]:
    import time

    start_time = time.perf_counter()
    keywords = []
    question_lower = question.lower().strip()

    try:
        from app.db.session import business_engine as _business_engine
        from app.db.session import config_engine
        from app.services.schema_service import SchemaService

        schema_service = SchemaService(db_engine=config_engine, business_engine=_business_engine)
        known_terms = schema_service.get_known_terms(context_name)

        remaining = question_lower
        for term in known_terms:
            term_lower = term.lower()
            if len(term_lower) < 2:
                continue
            if term_lower in remaining and term_lower not in THAI_STOP_WORDS:
                keywords.append(term)
                remaining = remaining.replace(term_lower, " ", 1)
    except RECOVERABLE_HIERARCHY_EXCEPTIONS as exc:
        logger.warning("Dictionary-based extraction failed: %s", exc)

    parts = re.split(r"[\s,;:?!()（）\[\]]+", question.strip())
    for part in parts:
        part = part.strip().strip('"\'')
        if len(part) < 2:
            continue
        if re.match(r"^\d+$", part):
            continue
        if part.lower() in THAI_STOP_WORDS:
            continue
        if len(part) > 20 and not any(char.isascii() and char.isalpha() for char in part):
            continue
        if any(char.isascii() and char.isalpha() for char in part):
            keywords.append(part)

    seen = set()
    unique = []
    for keyword in keywords:
        if keyword.lower() not in seen:
            seen.add(keyword.lower())
            unique.append(keyword)

    elapsed = time.perf_counter() - start_time
    logger.info("Keyword extraction: %s keywords in %.3fs — %s", len(unique), elapsed, [keyword[:30] for keyword in unique[:10]])
    return unique


def lookup_values_from_question(service: Any, question: str, context_name: str, table_name: str) -> List[Dict]:
    from app.db.session import business_engine as _business_engine
    from app.db.session import config_engine
    from app.services.schema_service import SchemaService
    import time

    start_time = time.perf_counter()
    results = []
    keywords = extract_keywords_from_question(service, question, context_name)
    if not keywords:
        return results

    try:
        schema_service = SchemaService(db_engine=config_engine, business_engine=_business_engine)
        try:
            from app.services.hierarchy_service import hierarchy_service

            has_hierarchy = True
        except (AttributeError, ImportError):
            has_hierarchy = False

        for keyword in keywords[:5]:
            matches = schema_service.search_keyword_index(keyword, context_name=context_name, limit=5)
            if matches:
                results.extend(matches)
            elif has_hierarchy:
                hierarchy_matches = hierarchy_service.search_aliases(context_name, keyword, limit=3)
                if hierarchy_matches:
                    for match in hierarchy_matches:
                        results.append({
                            "keyword": keyword,
                            "column_name": match["column_name"],
                            "column_value": match["value"],
                            "source": "hierarchy_alias",
                        })
                else:
                    results.extend(schema_service.search_db_for_keyword(keyword, table_name=table_name, context_name=context_name, limit=5))
            else:
                results.extend(schema_service.search_db_for_keyword(keyword, table_name=table_name, context_name=context_name, limit=5))

        elapsed = time.perf_counter() - start_time
        if results:
            logger.info("Value Lookup: %s keywords → %s matches (%.3fs)", len(keywords), len(results), elapsed)
    except RECOVERABLE_HIERARCHY_EXCEPTIONS as exc:
        logger.warning("Value Lookup failed: %s", exc)

    return results


def detect_hierarchy_level(question: str, context_name: str) -> Optional[Dict]:
    hierarchy = get_column_hierarchies().get(context_name)
    if not hierarchy:
        return None

    question_lower = question.lower()
    matched_levels: Dict[int, tuple] = {}
    for level_info in hierarchy:
        for keyword in level_info["detection_keywords"]:
            if keyword.lower() in question_lower:
                level = level_info["level"]
                if level not in matched_levels or len(keyword) > matched_levels[level][0]:
                    matched_levels[level] = (len(keyword), level_info)

    if not matched_levels:
        return None
    if len(matched_levels) == 1:
        return list(matched_levels.values())[0][1]

    parent_level = min(matched_levels.keys())
    return matched_levels[parent_level][1]


def format_value_matches(value_matches: List[Dict], hierarchy=None, detected_level=None) -> str:
    if not value_matches:
        return ""
    if not hierarchy:
        return format_value_matches_flat(value_matches)

    col_to_level: Dict[str, Dict] = {}
    for level_info in hierarchy:
        for column in level_info["columns"]:
            col_to_level[column.lower()] = level_info

    by_level: Dict[int, List[Dict]] = {}
    for match in value_matches:
        level_info = col_to_level.get(match["column_name"].lower())
        level = level_info["level"] if level_info else 999
        by_level.setdefault(level, []).append(match)

    if not by_level or (len(by_level) == 1 and 999 in by_level):
        return format_value_matches_flat(value_matches)

    intended_level_num = detected_level["level"] if detected_level else None
    lines = ["**Actual Values Found in Database (ค่าจริงจากฐานข้อมูล):**", "ค่าด้านล่างจัดกลุ่มตามลำดับชั้น (Hierarchy) — ใช้เฉพาะระดับที่ตรงกับคำถาม", ""]

    for level_info in sorted(hierarchy, key=lambda level: level["level"]):
        matches = by_level.get(level_info["level"], [])
        if not matches:
            continue
        is_intended = intended_level_num == level_info["level"]
        marker = " ← **ระดับที่ตรงกับคำถาม (USE THIS LEVEL)**" if is_intended else ""
        lines.append(f"### Level {level_info['level']}: {level_info['label_th']} ({level_info['label_en']}){marker}")

        grouped_by_keyword: Dict[str, List[Dict]] = {}
        for match in matches:
            grouped_by_keyword.setdefault(match.get("keyword", "?"), []).append(match)
        for keyword, keyword_matches in grouped_by_keyword.items():
            lines.append(f'  keyword "{keyword}":')
            for match in keyword_matches[:5]:
                column = match["column_name"]
                value = match["column_value"]
                if is_intended:
                    lines.append(f"    - column: `{column}`, value: `{value}`")
                    lines.append(f"      → **USE THIS**: `{column} LIKE '%{keyword}%'`")
                else:
                    lines.append(f"    - column: `{column}`, value: `{value}` (different level — do NOT use)")
            lines.append("")

    lines.extend([
        "⚠️ HIERARCHY RULES (สำคัญมาก!):",
        "1. ถ้ามี **USE THIS LEVEL** → ใช้ column จาก level นั้นเป็น WHERE filter",
        "2. ห้าม OR ข้าม level เด็ดขาด (ทำให้ตัวเลขผิดเพี้ยนหลายสิบเท่า)",
        "3. ถ้าไม่มี USE THIS LEVEL → ใช้ level สูงสุด (parent) ที่มี match",
        "4. ใช้ LIKE '%keyword%' สำหรับ text columns เสมอ",
        "",
        "⚠️ DRILL-DOWN PATTERN (สำคัญ!):",
        "ถ้าคำถามมีรูปแบบ 'แต่ละ X ของ Y' หรือ 'X ใน Y มีอะไรบ้าง':",
        "- Y = parent level → ใช้เป็น WHERE filter",
        "- X = child level → ใช้เป็น GROUP BY / SELECT",
        "ตัวอย่าง: 'แต่ละบริการของกลุ่ม Fixed Line' →",
        "  WHERE SERVICE_GROUP LIKE '%Fixed Line%' GROUP BY PRODUCT_NAME",
    ])
    return "\n".join(lines)


def format_value_matches_flat(value_matches: List[Dict]) -> str:
    if not value_matches:
        return ""

    by_keyword: Dict[str, List[Dict]] = {}
    for match in value_matches:
        by_keyword.setdefault(match.get("keyword", "?"), []).append(match)

    lines = ["**Actual Values Found in Database (ค่าจริงจากฐานข้อมูล):**", "ค่าด้านล่างเป็นค่าจริงจากตารางที่กำลังใช้ — ใช้ LIKE pattern ในการค้นหา", ""]
    for keyword, matches in by_keyword.items():
        lines.append(f'- keyword "{keyword}":')
        for match in matches[:5]:
            column = match["column_name"]
            value = match["column_value"]
            lines.append(f"  - column: `{column}`, actual value: `{value}`")
            lines.append(f"    → recommended: `{column} LIKE '%{keyword}%'`")

    lines.extend([
        "",
        "⚠️ IMPORTANT:",
        "- ใช้ LIKE '%keyword%' สำหรับ text columns (ห้ามใช้ = กับค่าข้อความ)",
        "- ค่า actual value ข้างบนเป็นตัวอย่างจริงจาก DB — ถ้าต้องการ exact match ให้ใช้ค่านี้",
        "- ถ้า Actual Values ขัดกับ Semantic Mapping → ให้เชื่อ Actual Values (เพราะมาจาก DB จริง)",
    ])
    return "\n".join(lines)
