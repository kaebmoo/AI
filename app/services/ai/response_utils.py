import json
import logging
import re
from collections import defaultdict
from typing import Dict, List, Optional


logger = logging.getLogger(__name__)


def prepare_data_for_explanation(data: List[Dict]) -> List[Dict]:
    """Prepare explanation payload by aggregating large result sets."""
    if not data:
        return data

    if len(data) <= 200:
        return data

    sample = data[0]
    text_cols = [key for key, value in sample.items() if isinstance(value, str)]
    all_num_cols = [key for key, value in sample.items() if isinstance(value, (int, float))]

    if not text_cols or not all_num_cols:
        return data[:200]

    dim_keywords = {"year", "month", "quarter", "ปี", "เดือน", "ไตรมาส", "q1", "q2", "q3", "q4"}
    num_dim_cols = []
    measure_cols = []

    for column in all_num_cols:
        distinct_count = len(set(row.get(column, 0) for row in data))
        col_lower = column.lower()
        is_dim_keyword = any(keyword in col_lower for keyword in dim_keywords)
        if is_dim_keyword or distinct_count <= min(20, len(data) * 0.1):
            num_dim_cols.append(column)
        else:
            measure_cols.append(column)

    if num_dim_cols:
        logger.info("explain data: numeric dimensions (not summed): %s, measures (summed): %s", num_dim_cols, measure_cols)

    all_dim_cols = text_cols + num_dim_cols
    if not measure_cols:
        return data[:200]

    cols_by_cardinality = sorted(
        all_dim_cols,
        key=lambda column: len(set(str(row.get(column, "")) for row in data)),
    )
    if len(cols_by_cardinality) >= 3:
        protected = {cols_by_cardinality[0], cols_by_cardinality[-1]}
        droppable = [column for column in cols_by_cardinality if column not in protected]
        cols_by_cardinality = droppable + [cols_by_cardinality[0], cols_by_cardinality[-1]]

    group_cols = list(all_dim_cols)
    for _attempt in range(len(cols_by_cardinality)):
        groups = defaultdict(lambda: {column: 0.0 for column in measure_cols})
        for row in data:
            key = tuple(str(row.get(column, "")) for column in group_cols)
            for column in measure_cols:
                groups[key][column] += (row.get(column, 0) or 0)

        if len(groups) <= 200:
            break

        for drop_col in cols_by_cardinality:
            if drop_col in group_cols and len(group_cols) > 1:
                group_cols.remove(drop_col)
                break

    aggregated_data = []
    for key, sums in groups.items():
        row = {}
        for column, value in zip(group_cols, key):
            if column in num_dim_cols:
                try:
                    row[column] = int(float(value)) if "." not in value else float(value)
                except (ValueError, TypeError):
                    row[column] = value
            else:
                row[column] = value
        row.update(sums)
        aggregated_data.append(row)

    sort_col = measure_cols[0] if measure_cols else None
    if sort_col:
        aggregated_data.sort(key=lambda row: row.get(sort_col, 0), reverse=True)
    result = aggregated_data[:200]

    dropped = set(all_dim_cols) - set(group_cols)
    if dropped:
        logger.info("explain data: %s → %s rows (dropped dimensions: %s)", len(data), len(result), dropped)
    return result


def extract_sql(text: str) -> Optional[str]:
    sql_match = re.search(r"```sql\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if sql_match:
        return sql_match.group(1).strip()

    code_match = re.search(r"```\s*((?:WITH|SELECT).*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if code_match:
        return code_match.group(1).strip()

    select_match = re.search(r"((?:WITH|SELECT)\s+.*?(?:;|$))", text, re.DOTALL | re.IGNORECASE)
    if select_match:
        sql = select_match.group(1).strip()
        if "\n\n" in sql:
            sql = sql.split("\n\n")[0]
        return sql.rstrip(";") + "" if not sql.endswith(";") else sql

    return None


def extract_explanation(text: str) -> str:
    text_without_sql = re.sub(r"```sql.*?```", "", text, flags=re.DOTALL | re.IGNORECASE)
    text_without_sql = re.sub(r"```.*?```", "", text_without_sql, flags=re.DOTALL)

    explanation_match = re.search(r"\*\*คำอธิบาย:?\*\*\s*(.*)", text_without_sql, re.DOTALL)
    if explanation_match:
        return explanation_match.group(1).strip()

    cleaned = text_without_sql.strip()
    if cleaned:
        return cleaned

    return "ดำเนินการสำเร็จ"


def parse_intent_json(text: str) -> Optional[Dict]:
    if not text:
        return None

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    match = re.search(r"(\{.*\})", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    return None