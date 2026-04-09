# NT AI Assistant — Refactoring Changelog

**Date:** 2026-03-04
**Phases Completed:** 1, 2, 3, 5 (Phase 4 skipped — OpenMiniCrew integration)
**Status:** All completed, 0 regressions

---

## Phase 1: Provider Extraction ✅

**Goal:** Break up `ai_service.py` God File (~2,190 lines) into modular provider files.

### Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `app/providers/__init__.py` | Package init, re-exports | 19 |
| `app/providers/base.py` | `AIProvider` ABC + dataclasses (`ConfidenceResult`, `QueryResult`, `RetryStatus`) | 82 |
| `app/providers/retry_config.py` | `create_retry_decorator()` + `ai_retry` singleton | 47 |
| `app/providers/chart_postprocessor.py` | `parse_explanation_response()`, `enforce_time_series_rule()`, `auto_detect_chart_config()` | 190 |
| `app/providers/claude_provider.py` | `ClaudeProvider` class | 155 |
| `app/providers/gemini_provider.py` | `GeminiProvider` class | 230 |
| `app/providers/matcha_provider.py` | `MatchaProvider` class | 155 |
| `app/providers/registry.py` | `ProviderRegistry` with auto-discover + fallback | 120 |

### Files Modified

| File | Changes |
|------|---------|
| `app/services/ai_service.py` | Removed embedded provider classes. Added re-exports for backward compatibility. `AIService.__init__` now accepts `AIProvider` instance OR string (legacy). Factory functions (`create_*_service`) now create provider first, then pass to `AIService`. |

### Backward Compatibility

- All existing imports (`from app.services.ai_service import ClaudeProvider, ...`) still work via re-exports
- `AIService(provider="claude", api_key=..., mcp_client=...)` legacy constructor still works
- Factory functions `create_claude_service()`, `create_gemini_service()`, `create_matcha_service()` still work
- API endpoints unchanged, frontend unchanged
- **New recommended pattern:** `AIService(provider=claude_instance, mcp_client=mcp)`

### Key Design Decisions

1. **chart_postprocessor.py** consolidates duplicate JSON parsing + Time-Series Rule enforcement from all 3 providers
2. **registry.py** auto-discovers providers using `importlib` + `inspect` on import — no manual registration needed
3. Each provider has `name`, `is_configured()`, `get_model(tier)` for registry and cost control
4. Provider files are independent — can be edited without touching other providers

---

## Phase 2: QueryEngine ✅

**Goal:** Extract business logic from `chat.py` POST endpoint into reusable `QueryEngine`.

### Files Created

| File | Purpose |
|------|---------|
| `app/services/query_engine.py` | `QueryEngine` orchestrator — resolve provider, detect context, execute, detect warnings |
| `app/services/warning_detector.py` | `WarningDetector` class + standalone functions for backward compat |

### Key Classes

```python
# QueryEngine — can be called from Web, Telegram, tests, scripts
engine = QueryEngine(mcp_client=mcp, db_session=db)
result = await engine.query("รายได้เดือนนี้เท่าไหร่")
# Returns QueryEngineResult with:
#   .query_result (QueryResult)
#   .context_name (str)
#   .warnings (List[DataWarning])
#   .execution_time_ms (float)
#   .provider_used (str)
```

### chat.py Changes

- Added imports for `QueryEngine` and `WarningDetector`
- Original endpoint logic **kept intact** (no behavioral change yet)
- `detect_data_warnings()` and `detect_multiple_sources_warning()` now importable from `warning_detector.py` too
- Future: endpoint can be simplified to ~50 lines by delegating to `QueryEngine`

---

## Phase 3: Internal Tool System ✅

**Goal:** Create auto-discover tool system for features beyond database queries.

### Files Created

| File | Purpose |
|------|---------|
| `app/tools/__init__.py` | Package init |
| `app/tools/base.py` | `BaseTool` ABC with `name`, `description`, `preferred_tier`, `execute()`, `get_tool_spec()` |
| `app/tools/registry.py` | `ToolRegistry` with auto-discover |
| `app/tools/report_export.py` | Example tool: export query results to CSV |

### Adding New Tools

Create a file in `app/tools/`, e.g. `app/tools/trending_analysis.py`:

```python
from app.tools.base import BaseTool

class TrendingAnalysisTool(BaseTool):
    name = "trending_analysis"
    description = "Analyze revenue trends"
    preferred_tier = "mid"

    async def execute(self, **kwargs):
        # ... implementation
        return {"success": True, "trends": [...]}
```

That's it — auto-discovered on next import. No registration needed.

---

## Phase 5: Tier-based Cost Control ✅

**Goal:** Use cheaper models for simple queries, more expensive models for complex ones.

### Files Created

| File | Purpose |
|------|---------|
| `app/services/query_classifier.py` | `QueryComplexityClassifier` — rule-based, 0 token cost |

### Classification Rules

| Tier | Example Queries | Models Used |
|------|----------------|-------------|
| **cheap** | "รายได้เดือนมกราคม", "ค่าใช้จ่ายรวม", "ยอดรวมเท่าไหร่" | Claude Haiku, Gemini Flash, GPT-4o-mini |
| **mid** | "เปรียบเทียบรายได้ปีนี้กับปีก่อน", "แนวโน้มรายได้", "top 10 ฝ่าย" | Claude Sonnet, Gemini Pro, GPT-4o |

### Integration

- `QueryEngine` calls `query_classifier.classify(question)` before executing
- Each provider implements `get_model(tier)` returning appropriate model ID
- Admin can override via feature flags:
  - `tier_classification_enabled`: Enable/disable auto classification
  - `force_tier`: Force specific tier ("cheap" or "mid")

### Model Mapping

| Provider | cheap | mid (default) |
|----------|-------|---------------|
| Claude | claude-haiku-4-5-20251001 | claude-sonnet-4-6 |
| Gemini | gemini-2.0-flash-exp | gemini-3-flash-preview |
| Matcha | gpt-4o-mini | gpt-4o |

---

## Test Results

```
Total: 82 passed, 1 failed (pre-existing), 16 deselected (pre-existing)
Regressions: 0
```

Pre-existing failures (NOT caused by refactoring):
- `PromptVersion` model doesn't exist in `feedback_models.py`
- `validate_sql` method was already removed from `AIService`
- `test_generate_sql_with_tool_use` uses sync call on async method
- `test_chat_history_empty` API validation issue

---

## File Tree After Refactoring

```
app/
├── providers/              # NEW — Phase 1
│   ├── __init__.py
│   ├── base.py             # AIProvider ABC + dataclasses
│   ├── retry_config.py     # Shared retry decorator
│   ├── chart_postprocessor.py  # Shared chart logic
│   ├── claude_provider.py  # ClaudeProvider
│   ├── gemini_provider.py  # GeminiProvider
│   ├── matcha_provider.py  # MatchaProvider
│   └── registry.py         # Auto-discover + fallback
├── services/
│   ├── ai_service.py       # MODIFIED — slimmed down, re-exports
│   ├── query_engine.py     # NEW — Phase 2
│   ├── warning_detector.py # NEW — Phase 2
│   ├── query_classifier.py # NEW — Phase 5
│   └── ... (unchanged)
├── tools/                  # NEW — Phase 3
│   ├── __init__.py
│   ├── base.py             # BaseTool ABC
│   ├── registry.py         # Auto-discover
│   └── report_export.py    # Example tool
└── api/v1/
    └── chat.py             # MODIFIED — added QueryEngine import
```

---

## Next Steps

1. **Phase 4 (Pending):** Create `openminicrew/tools/nt_query.py` to integrate via Telegram
2. **Optional:** Migrate `chat.py` POST endpoint to use `QueryEngine.query()` directly (reduce to ~50 lines)
3. **Optional:** Add more tools to `app/tools/` (trending_analysis, data_export_excel)
4. **Optional:** Add admin UI controls for `tier_classification_enabled` and `force_tier`
