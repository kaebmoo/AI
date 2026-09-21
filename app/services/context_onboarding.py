"""
NT AI Assistant - Context Onboarding Service
==============================================
Auto-analyze new views/tables and generate all necessary config
(business rules, golden examples, semantic mappings, schema metadata,
context instructions, hierarchy, data warnings) using LLM analysis.

Pipeline: Inspect → Analyze (LLM) → Generate Config → Apply → Validate
"""

import json
import logging
import re
import sqlite3
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from app.services.provenance import as_json

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ColumnProfile:
    name: str
    data_type: str
    nullable: bool = True
    distinct_count: int = 0
    null_count: int = 0
    total_count: int = 0
    sample_values: List[Any] = field(default_factory=list)
    all_distinct: Optional[List[Any]] = None  # if distinct < 100
    # Numeric stats
    min_val: Optional[float] = None
    max_val: Optional[float] = None
    mean_val: Optional[float] = None
    sum_val: Optional[float] = None
    has_negatives: bool = False
    # Pattern detection
    has_numeric_prefix: bool = False
    has_case_inconsistency: bool = False
    has_empty_values: bool = False
    is_numeric: bool = False
    is_time_column: bool = False


@dataclass
class CrossColumnAnalysis:
    """How a value column varies by a category column."""
    value_column: str
    category_column: str
    categories: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # categories = { "01.รายได้": {"sum": 500e9, "min": ..., "max": ..., "count": ...} }
    has_mixed_signs: bool = False  # + and - values across categories
    likely_semi_crosstab: bool = False


@dataclass
class QualityIssue:
    column: str
    issue_type: str  # case_inconsistency, prefix_inconsistency, empty_values, etc.
    description: str
    examples: List[str] = field(default_factory=list)


@dataclass
class InspectionResult:
    view_name: str
    columns: List[ColumnProfile]
    row_count: int = 0
    date_range: Optional[Dict[str, Any]] = None
    cross_analyses: List[CrossColumnAnalysis] = field(default_factory=list)
    quality_issues: List[QualityIssue] = field(default_factory=list)
    detected_structure: str = "unknown"  # long_table, semi_crosstab, wide_table
    detected_value_columns: List[str] = field(default_factory=list)
    detected_category_columns: List[str] = field(default_factory=list)
    detected_dimension_columns: List[str] = field(default_factory=list)
    detected_time_columns: List[str] = field(default_factory=list)
    # Phase 4.5: False for a source whose llm_data_policy isn't `full` — to_dict() (the LLM prompt, the
    # admin-agent tool result, the script's JSON) then carries structure only, no value read from the rows
    values_allowed: bool = True

    def to_dict(self) -> Dict:
        """Convert to dict for LLM prompt."""
        if not self.values_allowed:
            return self._to_dict_without_values()
        return {
            "view_name": self.view_name,
            "row_count": self.row_count,
            "detected_structure": self.detected_structure,
            "date_range": self.date_range,
            "columns": [
                {
                    "name": c.name,
                    "type": c.data_type,
                    "distinct_count": c.distinct_count,
                    "null_count": c.null_count,
                    "is_numeric": c.is_numeric,
                    "is_time_column": c.is_time_column,
                    "has_numeric_prefix": c.has_numeric_prefix,
                    "has_case_inconsistency": c.has_case_inconsistency,
                    "has_empty_values": c.has_empty_values,
                    "sample_values": c.sample_values[:10],
                    "all_distinct": c.all_distinct,
                    **({"min": c.min_val, "max": c.max_val, "mean": round(c.mean_val, 2) if c.mean_val else None,
                        "has_negatives": c.has_negatives} if c.is_numeric else {}),
                }
                for c in self.columns
            ],
            "cross_column_analyses": [
                {
                    "value_column": ca.value_column,
                    "category_column": ca.category_column,
                    "has_mixed_signs": ca.has_mixed_signs,
                    "likely_semi_crosstab": ca.likely_semi_crosstab,
                    "categories": {
                        k: {kk: round(vv, 2) if isinstance(vv, float) else vv for kk, vv in v.items()}
                        for k, v in list(ca.categories.items())[:20]
                    },
                }
                for ca in self.cross_analyses
            ],
            "quality_issues": [
                {"column": qi.column, "type": qi.issue_type,
                 "description": qi.description, "examples": qi.examples[:5]}
                for qi in self.quality_issues
            ],
            "detected_value_columns": self.detected_value_columns,
            "detected_category_columns": self.detected_category_columns,
            "detected_dimension_columns": self.detected_dimension_columns,
            "detected_time_columns": self.detected_time_columns,
        }


    def _to_dict_without_values(self) -> Dict:
        return {
            "view_name": self.view_name,
            "row_count": self.row_count,
            "detected_structure": self.detected_structure,
            "values_withheld": "llm_data_policy ของ source นี้ไม่ใช่ full — ไม่มีค่าตัวอย่าง/สถิติจากข้อมูล",
            "columns": [
                {"name": c.name, "type": c.data_type, "distinct_count": c.distinct_count, "null_count": c.null_count,
                 "is_numeric": c.is_numeric, "is_time_column": c.is_time_column,
                 "has_numeric_prefix": c.has_numeric_prefix, "has_case_inconsistency": c.has_case_inconsistency,
                 "has_empty_values": c.has_empty_values}
                for c in self.columns
            ],
            "cross_column_analyses": [
                {"value_column": ca.value_column, "category_column": ca.category_column,
                 "has_mixed_signs": ca.has_mixed_signs, "likely_semi_crosstab": ca.likely_semi_crosstab}
                for ca in self.cross_analyses
            ],
            "quality_issues": [{"column": qi.column, "type": qi.issue_type} for qi in self.quality_issues],
            "detected_value_columns": self.detected_value_columns,
            "detected_category_columns": self.detected_category_columns,
            "detected_dimension_columns": self.detected_dimension_columns,
            "detected_time_columns": self.detected_time_columns,
        }


@dataclass
class ConfigBundle:
    """Generated config ready to apply."""
    context: Optional[Dict] = None  # schema_contexts row
    metadata: List[Dict] = field(default_factory=list)  # schema_metadata rows
    business_rules: List[Dict] = field(default_factory=list)
    golden_examples: List[Dict] = field(default_factory=list)
    semantic_mappings: List[Dict] = field(default_factory=list)
    hierarchy_levels: List[Dict] = field(default_factory=list)
    data_warnings: List[Dict] = field(default_factory=list)
    # SQL statements for direct DB insert
    sql_statements: List[str] = field(default_factory=list)
    # Summary for human review
    summary: str = ""


@dataclass
class ValidationResult:
    passed: bool
    test_results: List[Dict] = field(default_factory=list)
    issues: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase 1: Data Inspection (SQL-only, no LLM)
# ---------------------------------------------------------------------------

def _values_allowed(view_name: str) -> bool:
    from app.core.llm_policy import FULL
    from app.services.data_sources import policy_for_table
    return policy_for_table(view_name) == FULL


class DataInspector:
    """Inspect a view/table and produce a detailed profile."""

    # Heuristic: columns matching these patterns are time-related
    TIME_PATTERNS = re.compile(
        r'(year|month|date|period|quarter|week|day|yr|mth|ปี|เดือน|วันที่)',
        re.IGNORECASE
    )

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def inspect(self, view_name: str) -> InspectionResult:
        """Full inspection of a view. Returns InspectionResult."""
        conn = self._connect()
        try:
            columns = self._get_schema(conn, view_name)
            row_count = self._get_row_count(conn, view_name)

            # Profile each column
            for col in columns:
                self._profile_column(conn, view_name, col, row_count)

            # Classify columns
            value_cols = [c.name for c in columns if c.is_numeric and c.distinct_count > 20]
            time_cols = [c.name for c in columns if c.is_time_column]
            category_cols = [c.name for c in columns
                            if not c.is_numeric and not c.is_time_column
                            and c.distinct_count > 1 and c.distinct_count <= 100]
            dimension_cols = [c.name for c in columns
                             if not c.is_numeric and not c.is_time_column
                             and c.distinct_count > 1]

            # Cross-column analysis: check if value columns vary by category columns
            cross_analyses = []
            for vc in value_cols:
                for cc in category_cols:
                    if cc == vc:
                        continue
                    ca = self._cross_column_analysis(conn, view_name, vc, cc)
                    if ca:
                        cross_analyses.append(ca)

            # Detect quality issues
            quality_issues = self._detect_quality_issues(columns)

            # Detect date range
            date_range = self._detect_date_range(conn, view_name, time_cols)

            # Detect data structure type
            structure = self._detect_structure(columns, cross_analyses, value_cols)

            result = InspectionResult(
                view_name=view_name,
                columns=columns,
                row_count=row_count,
                date_range=date_range,
                cross_analyses=cross_analyses,
                quality_issues=quality_issues,
                detected_structure=structure,
                detected_value_columns=value_cols,
                detected_category_columns=[c.name for c in columns
                                           if not c.is_numeric and not c.is_time_column
                                           and c.distinct_count > 1 and c.distinct_count <= 50],
                detected_dimension_columns=dimension_cols,
                detected_time_columns=time_cols,
                values_allowed=_values_allowed(view_name),
            )
            return result
        finally:
            conn.close()

    def _get_schema(self, conn: sqlite3.Connection, view_name: str) -> List[ColumnProfile]:
        """Get column schema from PRAGMA."""
        cursor = conn.execute(f"PRAGMA table_info('{view_name}')")
        columns = []
        for row in cursor.fetchall():
            col = ColumnProfile(
                name=row['name'],
                data_type=row['type'] or 'TEXT',
                nullable=not row['notnull'],
            )
            # Detect time columns by name
            if self.TIME_PATTERNS.search(col.name):
                col.is_time_column = True
            # Detect numeric by type
            dtype = col.data_type.upper()
            if any(t in dtype for t in ('INT', 'REAL', 'FLOAT', 'NUMERIC', 'DOUBLE', 'DECIMAL')):
                col.is_numeric = True
            columns.append(col)
        return columns

    def _get_row_count(self, conn: sqlite3.Connection, view_name: str) -> int:
        row = conn.execute(f'SELECT COUNT(*) as cnt FROM "{view_name}"').fetchone()
        return row['cnt'] if row else 0

    def _profile_column(self, conn: sqlite3.Connection, view_name: str,
                        col: ColumnProfile, total_rows: int):
        """Profile a single column: distinct count, nulls, samples, stats."""
        col.total_count = total_rows

        # Distinct count + null count
        row = conn.execute(
            f'SELECT COUNT(DISTINCT "{col.name}") as dc, '
            f'SUM(CASE WHEN "{col.name}" IS NULL THEN 1 ELSE 0 END) as nc '
            f'FROM "{view_name}"'
        ).fetchone()
        col.distinct_count = row['dc'] or 0
        col.null_count = row['nc'] or 0

        # Check for empty string values
        try:
            row2 = conn.execute(
                f"SELECT COUNT(*) as ec FROM \"{view_name}\" "
                f"WHERE \"{col.name}\" = ''"
            ).fetchone()
            if row2 and row2['ec'] > 0:
                col.has_empty_values = True
        except Exception:
            pass

        # Sample values (up to 10)
        try:
            samples = conn.execute(
                f'SELECT DISTINCT "{col.name}" FROM "{view_name}" '
                f'WHERE "{col.name}" IS NOT NULL AND "{col.name}" != \'\' '
                f'LIMIT 10'
            ).fetchall()
            col.sample_values = [s[0] for s in samples]
        except Exception:
            pass

        # All distinct values if < 100
        if col.distinct_count < 100:
            try:
                all_vals = conn.execute(
                    f'SELECT DISTINCT "{col.name}" FROM "{view_name}" '
                    f'WHERE "{col.name}" IS NOT NULL AND "{col.name}" != \'\' '
                    f'ORDER BY "{col.name}"'
                ).fetchall()
                col.all_distinct = [v[0] for v in all_vals]
            except Exception:
                pass

        # Numeric stats
        if col.is_numeric:
            try:
                stats = conn.execute(
                    f'SELECT MIN("{col.name}") as mn, MAX("{col.name}") as mx, '
                    f'AVG("{col.name}") as av, SUM("{col.name}") as sm '
                    f'FROM "{view_name}" WHERE "{col.name}" IS NOT NULL'
                ).fetchone()
                col.min_val = stats['mn']
                col.max_val = stats['mx']
                col.mean_val = stats['av']
                col.sum_val = stats['sm']
                if col.min_val is not None and col.min_val < 0:
                    col.has_negatives = True
            except Exception:
                pass

        # Detect numeric prefix pattern (e.g., "01.รายได้", "02.ต้นทุน")
        if not col.is_numeric and col.sample_values:
            prefix_pattern = re.compile(r'^\d{1,3}\.')
            prefix_count = sum(1 for v in col.sample_values if isinstance(v, str) and prefix_pattern.match(v))
            if prefix_count >= len(col.sample_values) * 0.5 and prefix_count >= 2:
                col.has_numeric_prefix = True

        # Detect case inconsistency
        if not col.is_numeric and col.all_distinct:
            str_vals = [str(v) for v in col.all_distinct if v]
            upper_vals = set(v.upper() for v in str_vals)
            if len(upper_vals) < len(str_vals):
                col.has_case_inconsistency = True

    def _cross_column_analysis(self, conn: sqlite3.Connection, view_name: str,
                               value_col: str, category_col: str) -> Optional[CrossColumnAnalysis]:
        """Analyze how a value column varies by a category column."""
        try:
            rows = conn.execute(
                f'SELECT "{category_col}" as cat, '
                f'SUM("{value_col}") as total, '
                f'MIN("{value_col}") as mn, '
                f'MAX("{value_col}") as mx, '
                f'COUNT(*) as cnt '
                f'FROM "{view_name}" '
                f'WHERE "{category_col}" IS NOT NULL AND "{category_col}" != \'\' '
                f'GROUP BY "{category_col}" '
                f'ORDER BY "{category_col}"'
            ).fetchall()

            if len(rows) < 2:
                return None

            ca = CrossColumnAnalysis(
                value_column=value_col,
                category_column=category_col,
            )
            has_positive = False
            has_negative = False

            for row in rows:
                cat_name = str(row['cat'])
                total = row['total'] or 0
                ca.categories[cat_name] = {
                    "sum": total,
                    "min": row['mn'],
                    "max": row['mx'],
                    "count": row['cnt'],
                }
                if total > 0:
                    has_positive = True
                if total < 0:
                    has_negative = True

            ca.has_mixed_signs = has_positive and has_negative

            # Semi-crosstab heuristic: if category column has numeric prefix
            # AND value column has mixed signs across categories → likely semi-crosstab
            # This catches P&L-like structures
            cat_col_profile = None
            for c in []:  # will be set from outside
                pass
            # Simple heuristic based on mixed signs + ordered categories
            if ca.has_mixed_signs and len(ca.categories) >= 3:
                ca.likely_semi_crosstab = True

            return ca
        except Exception as e:
            logger.debug(f"Cross-column analysis failed for {value_col}/{category_col}: {e}")
            return None

    def _detect_quality_issues(self, columns: List[ColumnProfile]) -> List[QualityIssue]:
        """Detect data quality issues from column profiles."""
        issues = []
        for col in columns:
            if col.has_case_inconsistency:
                # Find examples of case differences
                examples = []
                if col.all_distinct:
                    seen_upper = {}
                    for v in col.all_distinct:
                        upper = str(v).upper()
                        if upper in seen_upper and str(v) != seen_upper[upper]:
                            examples.append(f'"{seen_upper[upper]}" vs "{v}"')
                        seen_upper[upper] = str(v)
                issues.append(QualityIssue(
                    column=col.name,
                    issue_type="case_inconsistency",
                    description=f"Column '{col.name}' has case-inconsistent values across records",
                    examples=examples[:5],
                ))

            if col.has_numeric_prefix and col.all_distinct:
                # Check if prefix numbers are inconsistent for same base text
                base_texts = {}
                for v in col.all_distinct:
                    v_str = str(v)
                    match = re.match(r'^(\d+)\.(.*)', v_str)
                    if match:
                        base = match.group(2).strip()
                        prefix = match.group(1)
                        if base in base_texts and base_texts[base] != prefix:
                            issues.append(QualityIssue(
                                column=col.name,
                                issue_type="prefix_inconsistency",
                                description=f"Column '{col.name}' has inconsistent numeric prefixes for same text",
                                examples=[f'"{base_texts[base]}.{base}" vs "{prefix}.{base}"'],
                            ))
                            break
                        base_texts[base] = prefix

            if col.has_empty_values:
                issues.append(QualityIssue(
                    column=col.name,
                    issue_type="empty_values",
                    description=f"Column '{col.name}' contains empty string values that should be filtered",
                ))

        return issues

    def _detect_date_range(self, conn: sqlite3.Connection, view_name: str,
                           time_cols: List[str]) -> Optional[Dict]:
        """Detect date range from time columns."""
        result = {}
        for tc in time_cols:
            try:
                row = conn.execute(
                    f'SELECT MIN("{tc}") as mn, MAX("{tc}") as mx '
                    f'FROM "{view_name}" WHERE "{tc}" IS NOT NULL'
                ).fetchone()
                if row:
                    result[tc] = {"min": row['mn'], "max": row['mx']}
            except Exception:
                pass
        return result if result else None

    def _detect_structure(self, columns: List[ColumnProfile],
                          cross_analyses: List[CrossColumnAnalysis],
                          value_cols: List[str]) -> str:
        """Detect if view is long_table, semi_crosstab, or wide_table."""
        # Multiple value columns → wide_table
        if len(value_cols) > 2:
            return "wide_table"

        # Check cross-column analyses for semi-crosstab signals
        for ca in cross_analyses:
            if ca.likely_semi_crosstab:
                return "semi_crosstab"

        # Single value column, no mixed signs → long_table
        if len(value_cols) == 1:
            return "long_table"

        return "long_table"


# ---------------------------------------------------------------------------
# Phase 2: LLM Analysis (Multi-Provider)
# ---------------------------------------------------------------------------

ANALYSIS_PROMPT_TEMPLATE = """# Data Context Analyzer for NL-to-SQL System

You are analyzing a database view to configure an NL-to-SQL system for NT (National Telecom).
The system converts Thai natural language questions into SQL queries.

## Input: Data Inspection Results
```json
{inspection_json}
```

## Existing System Contexts (for reference)
{existing_contexts}

## Your Analysis Tasks

### 1. Data Structure Confirmation
The automated inspection detected this as: **{detected_structure}**
Confirm or correct this classification:
- **long_table**: One value column, all rows have same semantic meaning (SUM is safe)
- **semi_crosstab**: One value column, but meaning depends on a category column (SUM without category = WRONG)
- **wide_table**: Multiple value columns, already pivoted

For semi_crosstab, explain which column changes the value meaning and why blind SUM is dangerous.

### 2. Context Definition
Define the context for this view:
- name (English, snake_case)
- display_name_th (Thai display name)
- display_name_en (English display name)
- detection_keywords (Thai + English keywords that route user questions to this context)
- instruction_th (Thai context instruction — detailed, with critical rules, data structure explanation, example queries)
- instruction_en (English version)

### 3. Schema Metadata
For each column, provide:
- display_name_th (Thai friendly name)
- description (what this column contains)
- is_summable (can this column be meaningfully SUMmed?)
- is_groupable (can this column be used in GROUP BY?)
- special_notes (any important note for SQL generation)

### 4. Business Rules
Generate 5-10 rules that prevent common SQL mistakes. For each rule:
- rule_code (unique identifier like "PL_MUST_FILTER_MAINGROUP")
- rule_name (Thai name)
- rule_description (detailed Thai description)
- severity: "critical" (prevents wrong results), "warning" (best practice), "info"
- example_correct (correct SQL)
- example_wrong (wrong SQL + explanation why wrong)
- inject_mode: "schema_context" (in schema section) or "instruction" (in instruction section)

Consider: unit conversion, year conversion (พ.ศ.→ค.ศ.), case normalization, subtotal handling, semi-crosstab rules, empty value filtering.

### 5. Golden Examples
Generate 5-8 Thai question → SQL pairs covering:
- Basic aggregation with correct filters
- Monthly/yearly time analysis
- Year-over-year comparison
- Drill-down by hierarchy
- Best/worst performance
- The MOST COMMON mistake (show correct way)

### 6. Semantic Mappings
Map Thai/English terms users might say → SQL conditions:
- keyword (Thai or English term)
- keyword_type: "term", "abbreviation", or "synonym"
- target_column (which column to filter)
- target_condition (SQL condition to use)

### 7. Hierarchy
Identify dimension hierarchies (top → bottom):
- level (0 = top)
- level_label_th (Thai name for this level)
- level_columns (which column(s))
- detection_keywords (Thai keywords that indicate this level)

### 8. Data Warnings
Flag data quality issues users should know about:
- code (short warning code)
- message (Thai description)
- severity (info, warning, error)

## Output Format
Return EXACTLY this JSON structure (no markdown, no explanation — JSON only):
```json
{{
  "data_structure": {{
    "type": "long_table|semi_crosstab|wide_table",
    "explanation": "why this classification",
    "value_columns": ["col1"],
    "category_columns": ["col2"],
    "critical_rule": "key rule about querying this data correctly"
  }},
  "context": {{
    "name": "context_name",
    "display_name_th": "ชื่อภาษาไทย",
    "display_name_en": "English Name",
    "keywords": ["keyword1", "keyword2"],
    "instruction_th": "full Thai instruction text",
    "instruction_en": "full English instruction text"
  }},
  "schema_metadata": [
    {{
      "column_name": "col1",
      "display_name_th": "ชื่อไทย",
      "description": "คำอธิบาย",
      "is_summable": false,
      "is_groupable": true,
      "special_notes": "optional note"
    }}
  ],
  "business_rules": [
    {{
      "rule_code": "RULE_CODE",
      "rule_name": "ชื่อ rule",
      "rule_description": "คำอธิบาย",
      "severity": "critical|warning|info",
      "example_correct": "SELECT ...",
      "example_wrong": "SELECT ... -- reason why wrong",
      "inject_mode": "schema_context|instruction"
    }}
  ],
  "golden_examples": [
    {{
      "question": "คำถามภาษาไทย",
      "sql": "SELECT ...",
      "category": "category_name"
    }}
  ],
  "semantic_mappings": [
    {{
      "keyword": "keyword",
      "keyword_type": "term|abbreviation|synonym",
      "target_column": "column_name",
      "target_condition": "SQL condition"
    }}
  ],
  "hierarchy": [
    {{
      "level": 0,
      "level_label_th": "ระดับ",
      "level_columns": "column_name",
      "detection_keywords": ["kw1", "kw2"]
    }}
  ],
  "data_warnings": [
    {{
      "code": "WARN_001",
      "message": "description in Thai",
      "severity": "info"
    }}
  ]
}}
```
"""


class LLMAnalyzer:
    """Use LLM to analyze inspection results and suggest configuration."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        # Config DB path (for reading existing schema_contexts, etc.)
        from app.config import settings
        config_url = settings.CONFIG_DB_URL or settings.DATABASE_URL
        self.config_db_path = config_url.replace("sqlite:///", "").replace("sqlite://", "") or self.db_path

    def _get_existing_contexts_summary(self) -> str:
        """Get summary of existing contexts for reference."""
        try:
            conn = sqlite3.connect(self.config_db_path)
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT name, display_name, main_view FROM schema_contexts "
                "WHERE is_active = 1 AND status = 'active' ORDER BY priority"
            ).fetchall()
            conn.close()
            if not rows:
                return "No existing contexts."
            lines = []
            for r in rows:
                lines.append(f"- {r['name']}: {r['display_name']} (view: {r['main_view']})")
            return "\n".join(lines)
        except Exception:
            return "Could not load existing contexts."

    def build_prompt(self, inspection: InspectionResult) -> str:
        """Build the analysis prompt from inspection results."""
        inspection_json = json.dumps(inspection.to_dict(), ensure_ascii=False, indent=2)
        existing = self._get_existing_contexts_summary()
        return ANALYSIS_PROMPT_TEMPLATE.format(
            inspection_json=inspection_json,
            existing_contexts=existing,
            detected_structure=inspection.detected_structure,
        )

    async def analyze(self, inspection: InspectionResult,
                      provider_name: Optional[str] = None,
                      model: Optional[str] = None,
                      api_url: Optional[str] = None,
                      api_key: Optional[str] = None) -> Dict:
        """
        Send inspection to LLM and get structured analysis.

        Args:
            inspection: DataInspector output
            provider_name: "claude", "gemini", "matcha" or None (use default)
            model: Specific model name or None (use default)
            api_url: Custom API URL (for OpenAI-compatible providers)
            api_key: Custom API key (overrides env var)
        """
        prompt = self.build_prompt(inspection)

        # Create provider instance
        provider = self._create_provider(provider_name, model, api_url, api_key)
        if not provider:
            raise RuntimeError(f"Could not create AI provider: {provider_name or 'default'}")

        # Call LLM (generate_content is async for all providers)
        logger.info(f"Calling LLM ({provider.name}/{getattr(provider, 'model', '?')}) for analysis...")
        try:
            response_text = await provider.generate_content(prompt)
        except Exception as e:
            raise RuntimeError(f"LLM call failed: {e}")

        # Parse JSON from response
        return self._parse_response(response_text)

    def _create_provider(self, provider_name: Optional[str] = None,
                         model: Optional[str] = None,
                         api_url: Optional[str] = None,
                         api_key: Optional[str] = None):
        """Create an AI provider instance using the registry."""
        import os
        from app.providers.registry import provider_registry

        # Determine provider
        if not provider_name:
            provider_name = os.getenv('AI_PROVIDER', 'gemini')
            # Try to get from admin_config
            try:
                from app.services.admin_config_service import admin_config_service
                admin_provider = admin_config_service.get_config_value('default_ai_provider')
                if admin_provider:
                    provider_name = admin_provider
            except Exception:
                pass

        # Build kwargs for provider
        kwargs = {}
        if model:
            kwargs['model'] = model
        if api_url:
            kwargs['api_url'] = api_url
        if api_key:
            kwargs['api_key'] = api_key
        else:
            # Try to get API key from environment
            try:
                from app.services.admin_config_service import admin_config_service
                key = admin_config_service.get_provider_api_key(provider_name)
                if key:
                    kwargs['api_key'] = key
            except Exception:
                pass
            if 'api_key' not in kwargs:
                env_key_map = {
                    'claude': 'ANTHROPIC_API_KEY',
                    'gemini': 'GOOGLE_AI_API_KEY',
                    'matcha': 'MATCHA_AI_API_KEY',
                }
                env_var = env_key_map.get(provider_name, f'{provider_name.upper()}_API_KEY')
                kwargs['api_key'] = os.getenv(env_var, '')

        # Get API URL for matcha if not provided
        if provider_name == 'matcha' and 'api_url' not in kwargs:
            kwargs['api_url'] = os.getenv('MATCHA_API_URL', '')

        provider = provider_registry.create_provider(provider_name, **kwargs)
        return provider

    def _parse_response(self, response_text: str) -> Dict:
        """Extract JSON from LLM response."""
        # Try direct parse first
        text = response_text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting from code block
        if "```json" in text:
            json_str = text.split("```json")[1].split("```")[0].strip()
        elif "```" in text:
            json_str = text.split("```")[1].split("```")[0].strip()
        else:
            # Try finding { ... } boundary
            start = text.find('{')
            end = text.rfind('}')
            if start >= 0 and end > start:
                json_str = text[start:end + 1]
            else:
                raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}...")

        try:
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON from LLM: {e}\nText: {json_str[:500]}...")


# ---------------------------------------------------------------------------
# Phase 3: Config Generation
# ---------------------------------------------------------------------------

class ConfigGenerator:
    """Convert LLM analysis into ready-to-apply config."""

    def __init__(self, view_name: str):
        self.view_name = view_name

    def generate(self, analysis: Dict) -> ConfigBundle:
        """Generate config bundle from LLM analysis."""
        bundle = ConfigBundle()
        sql = []

        # 1. Context
        ctx = analysis.get("context", {})
        if ctx:
            bundle.context = ctx
            keywords_json = json.dumps(ctx.get("keywords", []), ensure_ascii=False)
            sql.extend(self._gen_context_sql(ctx, keywords_json))

        # 2. Schema metadata
        for meta in analysis.get("schema_metadata", []):
            bundle.metadata.append(meta)
            sql.extend(self._gen_metadata_sql(meta))

        # 3. Business rules
        for rule in analysis.get("business_rules", []):
            bundle.business_rules.append(rule)
            sql.extend(self._gen_rule_sql(rule))

        # 4. Golden examples
        for ex in analysis.get("golden_examples", []):
            bundle.golden_examples.append(ex)
            sql.extend(self._gen_example_sql(ex))

        # 5. Semantic mappings
        ctx_name = ctx.get("name", "") if ctx else ""
        for mapping in analysis.get("semantic_mappings", []):
            bundle.semantic_mappings.append(mapping)
            sql.extend(self._gen_mapping_sql(mapping, ctx_name))

        # 6. Hierarchy
        for level in analysis.get("hierarchy", []):
            bundle.hierarchy_levels.append(level)
            sql.append(self._gen_hierarchy_sql(level, ctx_name))

        # 7. Data warnings
        for warning in analysis.get("data_warnings", []):
            bundle.data_warnings.append(warning)
            sql.append(self._gen_warning_sql(warning))

        bundle.sql_statements = [s for s in sql if s]
        bundle.summary = self._build_summary(bundle)
        return bundle

    def _esc(self, s: str) -> str:
        """Escape single quotes for SQL."""
        if s is None:
            return ''
        return str(s).replace("'", "''")

    # Plan 8.1 (app/services/provenance.py): what onboarding writes is `inferred`, in use once the admin applies
    # it — a new row, or over a machine row. A row a person or the contract owns keeps its content and the inference
    # waits in knowledge_proposals. Still SQL text: the admin UI previews it and sends it back (apply-sql).
    # (_gen_hierarchy_sql / _gen_warning_sql leave out NOT NULL columns and fail as they always did — 8.2 rewrites them.)
    _REASON = "onboarding อนุมานจาก view — แถวที่ใช้อยู่เป็นของคน"

    def _lit(self, value) -> str:
        if value is None:
            return "NULL"
        if isinstance(value, bool):
            return "1" if value else "0"
        if isinstance(value, (int, float)):
            return repr(value)
        return f"'{self._esc(value)}'"

    @staticmethod
    def _machine(table: str) -> str:
        return (f"COALESCE({table}.source, '') IN ('inferred', 'learned') "
                f"AND COALESCE({table}.status, 'active') != 'rejected'")

    def _proposal_sql(self, table: str, key: Dict, values: Dict) -> str:
        """Queue the inference when the row at `key` is not a machine's and says something else."""
        where_key = " AND ".join(f"{c} = {self._lit(v)}" for c, v in key.items())
        same = " AND ".join(f"{c} IS {self._lit(v)}" for c, v in values.items())
        row_key, proposed = self._lit(as_json(key)), self._lit(as_json(values))
        return (f"INSERT INTO knowledge_proposals (table_name, row_key, proposed, source, reason) "
                f"SELECT '{table}', {row_key}, {proposed}, 'inferred', {self._lit(self._REASON)} "
                f"WHERE EXISTS (SELECT 1 FROM {table} WHERE {where_key} AND NOT ({self._machine(table)}) AND NOT ({same})) "
                f"AND NOT EXISTS (SELECT 1 FROM knowledge_proposals WHERE table_name = '{table}' AND row_key = {row_key} "
                f"AND source = 'inferred' AND status IN ('rejected', 'proposed') AND proposed = {proposed}) "
                f"ON CONFLICT (table_name, row_key, source) WHERE status = 'proposed' DO UPDATE SET "
                f"proposed = excluded.proposed, reason = excluded.reason, created_at = CURRENT_TIMESTAMP;")

    def _guarded(self, table: str, key: Dict, values: Dict, insert: Optional[Dict] = None) -> List[str]:
        """[proposal, upsert] — the upsert changes only a machine's row; a person's gets the proposal instead."""
        cols = {**key, **values, **(insert or {}), "source": "inferred", "status": "active"}
        sets = ", ".join(f"{c} = excluded.{c}" for c in values)
        return [self._proposal_sql(table, key, values),
                f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join(self._lit(v) for v in cols.values())}) "
                f"ON CONFLICT({', '.join(key)}) DO UPDATE SET {sets} WHERE {self._machine(table)};"]

    def _gen_context_sql(self, ctx: Dict, keywords_json: str) -> List[str]:
        return self._guarded("schema_contexts", {"name": ctx.get("name", "")}, {
            "display_name": ctx.get("display_name_th", ""), "main_view": self.view_name, "keywords": keywords_json,
            "instruction_th": ctx.get("instruction_th", ""), "instruction_en": ctx.get("instruction_en", ""),
        }, insert={"is_active": 1})

    def _gen_metadata_sql(self, meta: Dict) -> List[str]:
        # schema_metadata in config.db has NO is_active column
        return self._guarded("schema_metadata", {"table_name": self.view_name, "column_name": meta.get("column_name", "")}, {
            "display_name_th": meta.get("display_name_th", ""), "description": meta.get("description", ""),
            "is_summable": 1 if meta.get("is_summable") else 0, "is_groupable": 1 if meta.get("is_groupable") else 0,
            "special_notes": meta.get("special_notes", ""),
        })

    def _gen_rule_sql(self, rule: Dict) -> List[str]:
        return self._guarded("schema_business_rules", {"rule_code": rule.get("rule_code", "")}, {
            "rule_name": rule.get("rule_name", ""), "rule_description": rule.get("rule_description", ""),
            "table_name": self.view_name, "example_correct": rule.get("example_correct", ""),
            "example_wrong": rule.get("example_wrong", ""), "severity": rule.get("severity", "warning"),
            "inject_mode": rule.get("inject_mode", "schema_context"),
        }, insert={"is_active": 1})

    def _gen_example_sql(self, ex: Dict) -> List[str]:
        # golden_examples has no key of its own: the question is the key — a re-run no longer adds a duplicate
        key = {"question_pattern": ex.get("question", "")}
        values = {"expected_sql": ex.get("sql", ""), "category": ex.get("category", "")}
        q, sql, category = self._lit(key["question_pattern"]), self._lit(values["expected_sql"]), self._lit(values["category"])
        return [self._proposal_sql("golden_examples", key, values),
                f"UPDATE golden_examples SET expected_sql = {sql}, category = {category} "
                f"WHERE question_pattern = {q} AND {self._machine('golden_examples')};",
                f"INSERT INTO golden_examples (question_pattern, expected_sql, category, is_active, usage_count, source, status) "
                f"SELECT {q}, {sql}, {category}, 1, 0, 'inferred', 'active' "
                f"WHERE NOT EXISTS (SELECT 1 FROM golden_examples WHERE question_pattern = {q});"]

    def _gen_mapping_sql(self, mapping: Dict, context_name: str) -> List[str]:
        return self._guarded("schema_semantic_mapping", {"keyword": mapping.get("keyword", "")}, {
            "keyword_type": mapping.get("keyword_type", "term"), "target_column": mapping.get("target_column", ""),
            "target_condition": mapping.get("target_condition", ""), "context_name": context_name,
        }, insert={"is_active": 1})

    def _gen_hierarchy_sql(self, level: Dict, context_name: str) -> str:
        keywords_json = json.dumps(level.get("detection_keywords", []), ensure_ascii=False)
        # config.db uses level_label_th (not label_th)
        return (
            f"INSERT OR REPLACE INTO master_hierarchy "
            f"(context_name, level, level_label_th, level_columns, detection_keywords, is_active) VALUES ("
            f"'{self._esc(context_name)}', "
            f"{level.get('level', 0)}, "
            f"'{self._esc(level.get('label_th', level.get('level_label_th', '')))}', "
            f"'{self._esc(level.get('level_columns', ''))}', "
            f"'{self._esc(keywords_json)}', 1);"
        )

    def _gen_warning_sql(self, warning: Dict) -> str:
        # config.db data_warnings uses: code, message, severity, context_name, is_active
        return (
            f"INSERT INTO data_warnings "
            f"(code, message, severity, context_name, is_active) VALUES ("
            f"'{self._esc(warning.get('code', warning.get('warning_name', '')))}', "
            f"'{self._esc(warning.get('message', warning.get('warning_description', '')))}', "
            f"'{self._esc(warning.get('severity', 'info'))}', "
            f"'{self._esc(warning.get('context_name', ''))}', 1);"
        )

    def _build_summary(self, bundle: ConfigBundle) -> str:
        """Build a human-readable summary."""
        lines = [f"## Config Summary for: {self.view_name}\n"]
        if bundle.context:
            lines.append(f"**Context:** {bundle.context.get('display_name_th', '?')} ({bundle.context.get('name', '?')})")
            lines.append(f"**Keywords:** {', '.join(bundle.context.get('keywords', []))}")
        lines.append(f"\n**Schema Metadata:** {len(bundle.metadata)} columns")
        lines.append(f"**Business Rules:** {len(bundle.business_rules)} rules")
        for r in bundle.business_rules:
            lines.append(f"  - [{r.get('severity', '?')}] {r.get('rule_code', '?')}: {r.get('rule_name', '?')}")
        lines.append(f"**Golden Examples:** {len(bundle.golden_examples)} examples")
        for ex in bundle.golden_examples:
            lines.append(f"  - {ex.get('question', '?')[:60]}...")
        lines.append(f"**Semantic Mappings:** {len(bundle.semantic_mappings)} mappings")
        lines.append(f"**Hierarchy Levels:** {len(bundle.hierarchy_levels)} levels")
        lines.append(f"**Data Warnings:** {len(bundle.data_warnings)} warnings")
        lines.append(f"\n**Total SQL Statements:** {len(bundle.sql_statements)}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 4: Apply Config
# ---------------------------------------------------------------------------

class ConfigApplicator:
    """Apply generated config to the config database."""

    def __init__(self, db_path: str = None):
        if db_path:
            # Explicit path passed (e.g., from tests) — use as-is
            self.db_path = db_path
        else:
            # Production: config writes go to config DB
            from app.config import settings
            config_url = settings.CONFIG_DB_URL
            if config_url:
                self.db_path = config_url.replace("sqlite:///", "").replace("sqlite://", "")
            else:
                self.db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")

    def apply(self, bundle: ConfigBundle, dry_run: bool = True) -> Dict:
        """Apply config bundle. Returns results dict."""
        if dry_run:
            return {
                "status": "dry_run",
                "sql_count": len(bundle.sql_statements),
                "sql_statements": bundle.sql_statements,
                "summary": bundle.summary,
            }

        conn = sqlite3.connect(self.db_path)
        results = {"status": "applied", "success": 0, "errors": []}
        try:
            for sql in bundle.sql_statements:
                try:
                    conn.execute(sql)
                    results["success"] += 1
                except Exception as e:
                    results["errors"].append({"sql": sql[:200], "error": str(e)})
                    logger.warning(f"SQL error: {e}\nSQL: {sql[:200]}")
            conn.commit()
        except Exception as e:
            results["errors"].append({"error": f"Transaction failed: {e}"})
        finally:
            conn.close()

        # Invalidate caches
        self._invalidate_caches()
        results["summary"] = bundle.summary
        return results

    def apply_sql_statements(self, sql_statements: List[str]) -> Dict:
        """Apply pre-generated SQL statements directly (no LLM needed)."""
        bundle = ConfigBundle(sql_statements=sql_statements, summary="Applied from cached preview")
        return self.apply(bundle, dry_run=False)

    def _invalidate_caches(self):
        """Invalidate all relevant caches after config changes."""
        try:
            from app.services.schema_service import SchemaService
            schema_svc = SchemaService.__new__(SchemaService)
            if hasattr(schema_svc, '_cache'):
                schema_svc._cache = {}
            # Try the class-level cache
            SchemaService._cache = {}
        except Exception:
            pass
        try:
            from app.services.warning_detector import clear_warnings_cache
            clear_warnings_cache()
        except Exception:
            pass
        try:
            from app.services.query_classifier import clear_patterns_cache
            clear_patterns_cache()
        except Exception:
            pass
        logger.info("Caches invalidated after config apply")


# ---------------------------------------------------------------------------
# Phase 5: Validation
# ---------------------------------------------------------------------------

class ConfigValidator:
    """Validate applied config by running test queries."""

    def __init__(self, db_path: str = None):
        if db_path:
            # Explicit path passed (e.g., from tests) — use as-is
            self.db_path = db_path
        else:
            # Production: validation checks config DB
            from app.config import settings
            config_url = settings.CONFIG_DB_URL
            if config_url:
                self.db_path = config_url.replace("sqlite:///", "").replace("sqlite://", "")
            else:
                self.db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")

    async def validate(self, view_name: str, test_questions: List[str]) -> ValidationResult:
        """Run test questions and check SQL output for correctness."""
        # This is a lightweight validator that checks basic rules
        # Full validation would use the query engine, but that requires full app context
        result = ValidationResult(passed=True)

        # Basic check: verify config exists in DB
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            # Check context exists
            ctx = conn.execute(
                "SELECT COUNT(*) as cnt FROM schema_contexts WHERE main_view = ?",
                (view_name,)
            ).fetchone()
            if ctx['cnt'] == 0:
                result.issues.append(f"No context found for view {view_name}")
                result.passed = False

            # Check business rules exist
            rules = conn.execute(
                "SELECT COUNT(*) as cnt FROM schema_business_rules WHERE table_name = ? AND is_active = 1",
                (view_name,)
            ).fetchone()
            result.test_results.append({
                "check": "business_rules_exist",
                "count": rules['cnt'],
                "passed": rules['cnt'] > 0,
            })

            # Check metadata exists (schema_metadata has no is_active column)
            meta = conn.execute(
                "SELECT COUNT(*) as cnt FROM schema_metadata WHERE table_name = ?",
                (view_name,)
            ).fetchone()
            result.test_results.append({
                "check": "schema_metadata_exist",
                "count": meta['cnt'],
                "passed": meta['cnt'] > 0,
            })

            # Check golden examples exist
            # (golden_examples doesn't have table_name, check by category or SQL content)
            examples = conn.execute(
                "SELECT COUNT(*) as cnt FROM golden_examples WHERE expected_sql LIKE ? AND is_active = 1",
                (f"%{view_name}%",)
            ).fetchone()
            result.test_results.append({
                "check": "golden_examples_exist",
                "count": examples['cnt'],
                "passed": examples['cnt'] > 0,
            })

            if any(not t.get('passed') for t in result.test_results):
                result.passed = False

        finally:
            conn.close()

        return result


# ---------------------------------------------------------------------------
# Main Orchestrator
# ---------------------------------------------------------------------------

class ContextOnboardingService:
    """
    Main orchestrator for context onboarding pipeline.

    Usage:
        service = ContextOnboardingService("nt_fi_report.sqlite")

        # Phase 1: Inspect
        inspection = service.inspect("v_new_view")

        # Phase 2: Analyze with LLM
        analysis = await service.analyze(inspection, provider="gemini")

        # Phase 3: Generate config
        config = service.generate_config(analysis, view_name="v_new_view")

        # Phase 4: Apply (dry_run first)
        result = service.apply(config, dry_run=True)
        result = service.apply(config, dry_run=False)

        # Phase 5: Validate
        validation = await service.validate("v_new_view")
    """

    def __init__(self, db_path: str, config_db_path: Optional[str] = None):
        # db_path = the business DB the view lives in (inspect); config is written to and
        # validated against the config DB (config_db_path, default CONFIG_DB_URL) — handing
        # them the business DB made apply write to the wrong DB and validate fail (REMAIN-9.1)
        self.db_path = db_path
        self.inspector = DataInspector(db_path)
        self.llm_analyzer = LLMAnalyzer(db_path)
        self.applicator = ConfigApplicator(config_db_path)
        self.validator = ConfigValidator(config_db_path)

    def inspect(self, view_name: str) -> InspectionResult:
        """Phase 1: SQL-based data inspection."""
        logger.info(f"Phase 1: Inspecting view '{view_name}'...")
        return self.inspector.inspect(view_name)

    async def analyze(self, inspection: InspectionResult,
                      provider: Optional[str] = None,
                      model: Optional[str] = None,
                      api_url: Optional[str] = None,
                      api_key: Optional[str] = None) -> Dict:
        """Phase 2: LLM analysis."""
        logger.info(f"Phase 2: LLM analysis (provider={provider or 'default'})...")
        return await self.llm_analyzer.analyze(
            inspection, provider_name=provider, model=model,
            api_url=api_url, api_key=api_key
        )

    def generate_config(self, analysis: Dict, view_name: str) -> ConfigBundle:
        """Phase 3: Generate config from analysis."""
        generator = ConfigGenerator(view_name)
        logger.info("Phase 3: Generating config...")
        return generator.generate(analysis)

    def apply(self, config: ConfigBundle, dry_run: bool = True) -> Dict:
        """Phase 4: Apply config to DB."""
        mode = "dry_run" if dry_run else "apply"
        logger.info(f"Phase 4: {mode}...")
        return self.applicator.apply(config, dry_run=dry_run)

    def apply_sql_statements(self, sql_statements: List[str]) -> Dict:
        """Apply pre-generated SQL statements directly (no LLM needed)."""
        return self.applicator.apply_sql_statements(sql_statements)

    async def validate(self, view_name: str,
                       test_questions: Optional[List[str]] = None) -> ValidationResult:
        """Phase 5: Validate applied config."""
        logger.info(f"Phase 5: Validating config for '{view_name}'...")
        questions = test_questions or []
        return await self.validator.validate(view_name, questions)

    async def run_full_pipeline(self, view_name: str,
                                provider: Optional[str] = None,
                                model: Optional[str] = None,
                                api_url: Optional[str] = None,
                                api_key: Optional[str] = None,
                                dry_run: bool = True) -> Dict:
        """Run the complete onboarding pipeline."""

        # Phase 1
        inspection = self.inspect(view_name)

        # Phase 2
        analysis = await self.analyze(inspection, provider=provider, model=model,
                                      api_url=api_url, api_key=api_key)

        # Phase 3
        config = self.generate_config(analysis, view_name=view_name)

        # Phase 4
        apply_result = self.apply(config, dry_run=dry_run)

        # Phase 5 (only if applied)
        validation = None
        if not dry_run:
            validation = await self.validate(view_name)

        return {
            "view_name": view_name,
            "inspection": {
                "row_count": inspection.row_count,
                "columns": len(inspection.columns),
                "detected_structure": inspection.detected_structure,
                "quality_issues": len(inspection.quality_issues),
            },
            "analysis": {
                "data_structure": analysis.get("data_structure", {}),
                "rules_count": len(analysis.get("business_rules", [])),
                "examples_count": len(analysis.get("golden_examples", [])),
                "mappings_count": len(analysis.get("semantic_mappings", [])),
            },
            "config": {
                "summary": config.summary,
                "sql_count": len(config.sql_statements),
            },
            "apply": apply_result,
            "validation": {
                "passed": validation.passed if validation else None,
                "results": validation.test_results if validation else [],
            } if validation else None,
        }

    # Prefix patterns for internal/config tables (not business data)
    _INTERNAL_TABLE_PREFIXES = (
        'schema_', 'master_', 'admin_', 'golden_', 'data_warnings',
        'query_', 'ai_', 'otp_', 'chat_', 'training_',
        'alembic_', 'keyword_', 'unmatched_', 'view_column_',
        'v_active_', 'v_ai_', 'v_business_rules_', 'v_schema_for_',
        'v_semantic_mappings_',
    )
    _INTERNAL_TABLE_NAMES = {
        'users', 'sessions', 'conversations',
        'user_sessions', 'user_feedback', 'trending_queries',
        'ref_product_name_mapping',
    }

    def list_available_views(self) -> Dict:
        """List all views/tables with their onboarding status."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get all views and tables
        cursor.execute(
            "SELECT name, type FROM sqlite_master "
            "WHERE type IN ('view', 'table') AND name NOT LIKE 'sqlite_%' "
            "ORDER BY type, name"
        )
        all_objects = cursor.fetchall()

        # Get configured contexts from config DB (schema_contexts may be in separate DB)
        configured_views = set()
        try:
            from app.config import settings
            config_url = settings.CONFIG_DB_URL
            if config_url:
                config_db_path = config_url.replace("sqlite:///", "").replace("sqlite://", "")
                config_conn = sqlite3.connect(config_db_path)
                configured_views = {
                    row[0] for row in config_conn.execute(
                        "SELECT main_view FROM schema_contexts WHERE is_active = 1"
                    ).fetchall()
                }
                config_conn.close()
            else:
                cursor.execute("SELECT main_view FROM schema_contexts WHERE is_active = 1")
                configured_views = {row[0] for row in cursor.fetchall()}
        except Exception:
            pass

        unconfigured = []
        configured = []
        for name, obj_type in all_objects:
            # Skip internal/config tables by prefix or exact name
            if (name.startswith(self._INTERNAL_TABLE_PREFIXES)
                    or name in self._INTERNAL_TABLE_NAMES):
                continue

            # Get row count
            try:
                cursor.execute(f'SELECT COUNT(*) FROM "{name}"')
                row_count = cursor.fetchone()[0]
            except Exception:
                row_count = None

            item = {
                "name": name,
                "type": obj_type,
                "has_config": name in configured_views,
                "row_count": row_count,
            }

            if name in configured_views:
                configured.append(item)
            else:
                unconfigured.append(item)

        conn.close()
        return {"unconfigured": unconfigured, "configured": configured}
