# Task: Update DATABASE_TABLES_GUIDE.md and DATA_DICTIONARY.md

**Project root:** `/Users/seal/Documents/GitHub/AI/`
**Files to update:**
- `docs/DATABASE_TABLES_GUIDE.md`
- `docs/DATA_DICTIONARY.md`

**Priority:** DATABASE_TABLES_GUIDE.md first (it is consumed by Vanna RAG via `vanna_service._sync_documentation()` — inaccurate content directly degrades AI SQL generation quality).

---

## Why this matters

`vanna_service.py` method `_sync_documentation()` reads `docs/DATABASE_TABLES_GUIDE.md`, splits it by `## ` headings, and feeds each chunk into ChromaDB as training documentation. When users ask questions, Vanna retrieves these chunks as RAG context. **Wrong documentation = wrong RAG context = wrong SQL.**

Both docs were written in January 2025 and never updated. The system has changed significantly since then.

---

## Part 1: DATABASE_TABLES_GUIDE.md

### Source of truth (read these BEFORE writing)

Schema definitions — use SQLAlchemy models as authoritative source:
- `app/models/schema_models.py` — SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule, ViewColumnMapping, DataWarningModel, QueryComplexityPattern
- `app/models/feedback_models.py` — GoldenExample (and any related models)

For tables not in SQLAlchemy models, use migration files:
- `database/migrations/009_master_hierarchy.sql` — master_hierarchy, master_hierarchy_values
- `database/migrations/004_admin_config.sql` — schema_contexts (NOT schema_context_tables)
- `database/migrations/030_add_rule_pattern_columns.sql` — pattern/check_type additions to schema_business_rules

Code that uses these tables:
- `app/services/schema/service.py` — SchemaService facade (how tables are queried)
- `app/services/schema/prompt_builder.py` — how metadata/rules/mappings become prompts
- `app/services/schema/keyword_index.py` — keyword_value_index usage
- `app/services/schema/view_manager.py` — view_column_mappings usage
- `app/services/schema/context_store.py` — schema_contexts usage
- `app/services/hierarchy_service.py` — master_hierarchy/master_hierarchy_values usage
- `app/services/vanna_service.py` — how guide is consumed by RAG

### What to fix

#### 1. Replace section 4 (`schema_context_tables`) with `schema_contexts`

The guide documents `schema_context_tables` but the actual table used by the system is `schema_contexts` (created in migration 004). This is a different table with different columns. Document the real one:
- Columns from migration 004: id, name, display_name, description, main_view, keywords, priority, database_url, default_instruction, sample_queries, is_active, created_at, updated_at, created_by, metadata
- Additional columns added later: instruction_th, instruction_en (see migration 020)
- Explain multi-context concept (revenue, expense, pl_costtype, etc.)

If `schema_context_tables` still exists in the DB, mention it briefly as a secondary/legacy table but clarify that `schema_contexts` is what the code uses.

#### 2. Fix schema_metadata definition

Current guide is missing columns that exist in the SQLAlchemy model:
- `sample_values` (JSON)
- `dimension_group` (used by dimension family detection)
- `updated_at`

#### 3. Fix schema_semantic_mapping definition

Missing columns:
- `context_name` — critical, used for context-scoped mappings (NULL = global, value = scoped to specific context)
- `updated_at`
- `full_condition` — already in guide but verify it matches model

Also: the UNIQUE constraint is on `keyword` alone in the guide, but the actual behavior may differ when context_name scoping is involved. Check the model.

#### 4. Fix schema_business_rules definition

Missing columns from the SQLAlchemy model and migrations:
- `table_name` — filter rules per view/table (NULL = ALL)
- `inject_mode` — separates 'schema_context' vs 'instruction' rules
- `rule_category` — groups rules (context_retention, unit_conversion, etc.)
- `pattern` — regex pattern for validation (migration 030)
- `check_type` — validation type (migration 030)
- `updated_at`

#### 5. Add new table sections

Add documentation for these tables that are core to the current system but missing from the guide:

**Must add (directly relevant to SQL generation):**
- `schema_contexts` (replacing schema_context_tables section)
- `view_column_mappings` — maps view columns back to source table columns, used by metadata propagation
- `master_hierarchy` — hierarchy level definitions per context (DB-driven, replaces hardcoded COLUMN_HIERARCHIES)
- `master_hierarchy_values` — actual values per hierarchy level with parent_value chains and aliases
- `keyword_value_index` — smart value lookup index for matching user keywords to actual DB values

**Do NOT add (not relevant to SQL generation, would add noise to Vanna RAG):**
- admin_config, api_keys, audit_log, admin_agent tables, data_warnings, query_complexity_patterns, telegram tables

#### 6. Fix file path references

| Old reference | Correct reference |
|---|---|
| `app/api/v1/admin.py` | `app/api/v1/admin/` (package with schema.py, mappings.py, rules.py, etc.) |
| `app/services/schema_service.py` | `app/services/schema/service.py` (schema_service.py is now a compatibility shim) |

#### 7. Fix code examples

Replace all `SchemaService(db_path="...")` with the current engine-based constructor:
```python
from app.services.schema_service import SchemaService
from app.db.session import config_engine, business_engine

service = SchemaService(db_engine=config_engine, business_engine=business_engine)
```

Remove references to methods that don't exist:
- `service.get_abbreviation_mappings()` — use `service.get_semantic_mappings(keyword_type="abbreviation")`
- `service.get_term_mappings()` — use `service.get_semantic_mappings(keyword_type="term")`

#### 8. Add multi-context and hierarchy explanation

Add a section explaining:
- The system supports multiple contexts (revenue, expense, pl_costtype, etc.) via `schema_contexts`
- Each context has a `main_view` that AI queries against
- Semantic mappings can be global (context_name=NULL) or scoped to a specific context
- Hierarchy levels prevent "OR across levels" errors (BUSINESS_GROUP > SERVICE_GROUP > PRODUCT_NAME)
- `master_hierarchy_values` stores actual values with parent chains for validation

#### 9. Update the workflow diagram at the bottom

The existing workflow diagram shows 4 steps. Update it to include:
- Step 0: Context routing (schema_contexts determines which view to query)
- Step 1.5: Hierarchy level detection (master_hierarchy)
- Step 2.5: Value lookup (keyword_value_index matches user keywords to actual DB values)

#### 10. Update version/date

Set version to 2.0, date to 2026-03-22.

---

## Part 2: DATA_DICTIONARY.md

### Source of truth

- The actual views/tables in the business DB — check `schema_contexts` table for the list of main_views
- `database/migrations/003_schema_metadata.sql` — has INSERT statements showing actual column definitions for revenue_search
- `app/services/schema/prompt_builder.py` — how schema info is presented to AI

### What to fix

#### 1. Change table reference from `revenue` to `revenue_search`

The guide documents raw table `revenue` but the system uses view `revenue_search` (set as `main_view` in `schema_contexts`). Column names are different (lowercase in view vs UPPERCASE in raw table).

#### 2. Add expense and P&L views

At minimum, add overview sections for:
- `v_expense_mart` — expense context main_view
- `v_pl_costtype_nt_mth` — pl_costtype context main_view

Read the actual column definitions from schema_metadata table or by inspecting the views. If you can't access the actual DB, note "schema to be documented from live DB" and add the context info that IS available from code.

#### 3. Add hierarchy explanation

Add a section explaining the product/service hierarchy:
- `BUSINESS_GROUP` > `SERVICE_GROUP` > `PRODUCT_NAME` (for revenue context)
- Explain why OR across levels is dangerous (inflates numbers by orders of magnitude)
- Reference `master_hierarchy` table

#### 4. Update Common Queries

- Change table name from `revenue` to `revenue_search`
- Use lowercase column names matching the view (e.g., `year` not `YEAR`, `revenue` not `REVENUE_VALUE`)
- Add hierarchy-aware query examples

#### 5. Update version/date

Set to version 2.0, date 2026-03-22.

---

## Verification after completion

1. Read the updated DATABASE_TABLES_GUIDE.md and verify every table schema matches the SQLAlchemy model in `app/models/schema_models.py` or the migration SQL
2. Verify all code examples use the current constructor pattern (`config_engine`/`business_engine`)
3. Verify all file path references point to files that actually exist in the current repo structure
4. Verify no methods are referenced that don't exist on `SchemaService`
5. Check that the Vanna-consumed chunks (split by `## ` headings) each make sense as standalone RAG context

---

## Post-update action

After updating the docs, the Vanna brain should be re-synced to pick up the new content. This is done via the admin API endpoint that calls `vanna_service.sync_brain()`, or by restarting the service. This is NOT part of this task — just note it in the commit message.
