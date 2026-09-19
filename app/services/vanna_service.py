from typing import List, Dict, Any
import io
import contextlib

# Lazy imports — vanna/chromadb may not be available in all environments (e.g., Python 3.14)
try:
    from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
    from vanna.legacy.base import VannaBase
    _VANNA_AVAILABLE = True
except Exception:
    # Catch ALL errors: ImportError, ConfigError (pydantic.v1), AttributeError, etc.
    # chromadb can fail with pydantic.v1.errors.ConfigError on Python 3.14
    class ChromaDB_VectorStore:
        pass
    class VannaBase:
        pass
    _VANNA_AVAILABLE = False

import logging

from app.services.schema_service import SchemaService
from sqlalchemy import text

logger = logging.getLogger(__name__)

class _KeepAll:
    """BrainFilter stand-in until sync_brain sets the real one: train everything (the old behaviour)."""

    def context(self, _name) -> bool:
        return True

    view = context


class VannaService(ChromaDB_VectorStore, VannaBase):
    _keep = _KeepAll()

    def __init__(self, config: Dict[str, Any] = None):
        if not _VANNA_AVAILABLE:
            raise ImportError(
                "vanna/chromadb not available in this environment. "
                "Install with: pip install 'vanna[chromadb]'"
            )

        if config is None:
            config = {}

        # Plan 7 Phase 4b: one brain per workspace — 'default' keeps the path it always had
        from app.services.workspaces import brain_path
        self.workspace = config.get("workspace")
        db_path = brain_path(config.get("path", "./chroma_db"), self.workspace)
        self.distance_threshold = config.get("distance_threshold", 1.8)

        # Initialize Vanna's Vector Store
        ChromaDB_VectorStore.__init__(self, config={'path': db_path})

    def system_message(self, message: str) -> any:
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> any:
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> any:
        return {"role": "assistant", "content": message}

    def submit_prompt(self, prompt, **kwargs) -> str:
        # Placeholder for LLM call
        return "SQL_PLACEHOLDER"

    def sync_brain(self, schema_service: SchemaService):
        """
        Synchronize the Vanna 'Brain' (Vector DB) with the current Database state.
        This wipes and re-trains to ensure consistency.
        """
        from app.services.workspaces import BrainFilter
        # what belongs in this workspace's brain (no other workspace defined = everything, as before)
        self._keep = BrainFilter(self.workspace, schema_service.engine)
        logger.info("Starting Vanna Brain Sync (workspace=%s)...", self._keep.workspace)

        # Clear existing collections to avoid duplicates
        try:
            collections_to_clear = ["ddl", "documentation", "sql"]
            for col_name in collections_to_clear:
                try:
                    self.chroma_client.delete_collection(name=col_name)
                except Exception:
                    # Collection doesn't exist yet
                    pass
            logger.info("Cleared all existing vectors")

            # Re-initialize collections after deletion
            # This is crucial because the self.*_collection attributes still point to the deleted objects
            self.ddl_collection = self.chroma_client.get_or_create_collection(name="ddl")
            self.documentation_collection = self.chroma_client.get_or_create_collection(name="documentation")
            self.sql_collection = self.chroma_client.get_or_create_collection(name="sql")
            logger.info("Re-initialized collections")

        except Exception as e:
            logger.warning(f"Could not clear collections: {e}")

        # Suppress verbose per-item "Adding documentation...." from Vanna base
        # by redirecting stdout during training, then printing a clean summary
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()

        try:
            with contextlib.redirect_stdout(captured_stdout), contextlib.redirect_stderr(captured_stderr):
                self._sync_ddl(schema_service)
                self._sync_documentation(schema_service)
                self._sync_golden_examples(schema_service)
        finally:
            pass

        # Parse captured output for summary counts
        captured_output = "\n".join(
            part for part in [captured_stdout.getvalue().strip(), captured_stderr.getvalue().strip()] if part
        )
        lines = captured_output.split('\n') if captured_output else []
        adding_count = sum(1 for l in lines if 'Adding' in l)
        # Print non-"Adding" lines (our own summary prints) + a count summary
        for line in lines:
            if 'Adding' not in line and line.strip():
                logger.info(line)
        if adding_count > 0:
            logger.info(f"Trained {adding_count} total vector entries")

        logger.info("Vanna Brain Sync Complete.")

    def _sync_ddl(self, service: SchemaService):
        """Train the DDL of each active context's main view — the views the LLM should query;
        raw tables stay out (they would pull SQL toward them).

        DDL is read from the business DB: the config DB's sqlite_master never had these
        objects, so no DDL was ever trained (REMAIN-9.4).
        """
        with service.engine.connect() as conn:
            views = sorted({row[0] for row in conn.execute(text(
                "SELECT main_view FROM schema_contexts WHERE is_active = 1 AND main_view IS NOT NULL"))
                if self._keep.view(row[0])})
        # Phase 4d: a file-source view has no DDL in the business DB — what is there under the same
        # name is F10's stale imported copy. Its DDL is the registry's column list.
        from app.services.data_sources import registered_tables
        file_tables = registered_tables(service.engine)
        with service.business_engine.connect() as conn:
            for name in views:
                if name in file_tables:
                    columns = ", ".join(f'"{c["name"]}" {c["type"]}' for c in file_tables[name]["columns"])
                    self.train(ddl=f'CREATE TABLE "{name}" ({columns})')
                    logger.info(f"Trained DDL (file source): {name}")
                    continue
                try:
                    row = conn.execute(
                        text("SELECT sql FROM sqlite_master WHERE type IN ('table', 'view') AND name = :name"),
                        {"name": name},
                    ).fetchone()
                except Exception as e:
                    logger.warning(f"Error getting DDL for {name}: {e}")
                    continue
                if row and row[0]:
                    self.train(ddl=row[0])
                    logger.info(f"Trained DDL: {name}")

    def _sync_documentation(self, service: SchemaService):
        """Train Documentation — DB-driven, no static files."""

        # 1. Business Rules
        with service.engine.connect() as conn:
            rules = conn.execute(text("SELECT * FROM schema_business_rules WHERE is_active=1")).mappings().all()
            for rule in rules:
                if not self._keep.view(rule['table_name']):  # a rule about another workspace's view
                    continue
                doc_text = f"**Rule: {rule['rule_name']}**\nCode: {rule['rule_code']}\nDescription: {rule['rule_description']}\nCorrect Example: {rule['example_correct']}\nSeverity: {rule['severity']}"
                self.train(documentation=doc_text)

        # 2. Semantic Mappings (Group by type for better context)
        with service.engine.connect() as conn:
            mappings = conn.execute(text("SELECT * FROM schema_semantic_mapping WHERE is_active=1")).mappings().all()
            for m in mappings:
                if not self._keep.context(m['context_name']):
                    continue
                doc_text = f"**Term Mapping**\nKeyword: '{m['keyword']}' means column `{m['target_column']}` ({m['keyword_type']})\nCondition: {m['target_condition']}\nNote: {m['description']}"
                self.train(documentation=doc_text)

        # 3. Auto-generated context summaries (replaces static guide file)
        self._sync_context_summaries(service)

        # 4. Manual documentation from vanna_documentation table
        try:
            with service.engine.connect() as conn:
                docs = [d for d in conn.execute(text(
                    "SELECT title, content, context_name FROM vanna_documentation WHERE is_active = 1 ORDER BY category, doc_key"
                )).mappings().all() if self._keep.context(d['context_name'])]
                for doc in docs:
                    self.train(documentation=f"## {doc['title']}\n{doc['content']}")
            logger.info(f"Trained {len(docs)} documentation entries from DB")
        except Exception as e:
            logger.warning(f"Could not load vanna_documentation: {e}")

    def _sync_context_summaries(self, service: SchemaService):
        """Auto-generate and train one documentation chunk per active context."""
        contexts = service.get_all_contexts()
        if not contexts:
            logger.info("No active contexts found for summary generation")
            return

        trained = 0
        for ctx in contexts:
            if not self._keep.context(ctx.get('name')):
                continue
            try:
                main_view = ctx.get('main_view', '')
                display_name = ctx.get('display_name', ctx.get('name', ''))
                description = ctx.get('description', '')

                metadata = service.get_schema_metadata(main_view)
                summable = [m['column_name'] for m in metadata if m.get('is_summable')]
                groupable = [m['column_name'] for m in metadata if m.get('is_groupable')]

                summary = f"## Context: {display_name} ({ctx['name']})\n"
                summary += f"Main View: {main_view}\n"
                if description:
                    summary += f"Description: {description}\n"
                summary += f"\nSummable columns (ใช้ SUM ได้): {', '.join(summable) or 'none'}\n"
                summary += f"Groupable columns (ใช้ GROUP BY ได้): {', '.join(groupable[:15]) or 'none'}\n"

                try:
                    from app.services.hierarchy_service import hierarchy_service
                    levels = hierarchy_service.get_levels(ctx['name'])
                    if levels:
                        chain = ' > '.join(lv['level_label_th'] for lv in levels)
                        summary += f"\nHierarchy: {chain}\n"
                        summary += "CRITICAL: ห้าม OR ข้ามระดับ hierarchy — ทำให้ตัวเลขผิดเพี้ยนหลายสิบเท่า\n"
                except Exception:
                    pass

                # NOTE: instruction_th is intentionally excluded from context summaries.
                # It contains rule-like content already trained via business_rules.
                # Including it would duplicate policy guidance and skew retrieval ranking.

                self.train(documentation=summary)
                trained += 1
            except Exception as e:
                logger.warning("Could not generate summary for context '%s': %s", ctx.get('name'), e)

        logger.info(f"Generated {trained} context summaries")

    def _sync_golden_examples(self, service: SchemaService):
        """Train SQL from Golden Examples"""
        with service.engine.connect() as conn:
            # category = the context name for generated golden; free text (legacy) belongs to 'default'
            examples = [e for e in conn.execute(text("SELECT * FROM golden_examples WHERE is_active=1")).mappings().all()
                        if self._keep.context(e['category'])]
            for ex in examples:
                self.train(question=ex['question_pattern'], sql=ex['expected_sql'])
                
        logger.info(f"Trained {len(examples)} Golden Examples")

    def _get_chroma_results(self, collection, question: str, n_results: int = 10, threshold: float = None) -> List[str]:
        """Helper to query ChromaDB with distance filtering"""
        if threshold is None:
            threshold = self.distance_threshold
        try:
            results = collection.query(
                query_texts=[question],
                n_results=n_results
            )
            
            documents = results.get('documents', [[]])[0]
            distances = results.get('distances', [[]])[0]
            
            filtered_docs = []
            if distances:
                for doc, dist in zip(documents, distances):
                    if dist <= threshold:
                        filtered_docs.append(doc)
            else:
                # Fallback if distances not returned (unlikely)
                filtered_docs = documents
                 
            return filtered_docs
        except Exception as e:
            logger.warning(f"Error querying Chroma: {e}")
            return []

    def get_rag_context(self, question: str, distance_threshold: float = None) -> Dict[str, List[str]]:
        """
        Retrieve relevant context for a question with score filtering.
        Returns mapped DDLs, Docs, and SQLs.
        """
        if distance_threshold is None:
            distance_threshold = self.distance_threshold

        import time

        start_total = time.perf_counter()
        
        # Use direct chroma query for filtering
        t0 = time.perf_counter()
        # DDL usually needs higher threshold or specific matching?
        # DDLs are often just trained as table names/schema.
        # Let's keep DDL threshold slightly looser or standard.
        related_ddl = self._get_chroma_results(self.ddl_collection, question, threshold=distance_threshold)
        t_ddl = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        related_doc = self._get_chroma_results(self.documentation_collection, question, threshold=distance_threshold)
        t_doc = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        related_sql = self._get_chroma_results(self.sql_collection, question, threshold=distance_threshold)
        t_sql = time.perf_counter() - t0
        
        total_time = time.perf_counter() - start_total
        logger.info(
            "Vanna RAG Timing - Total: %.4fs | DDL: %.4fs (n=%s) | Doc: %.4fs (n=%s) | SQL: %.4fs (n=%s)",
            total_time,
            t_ddl,
            len(related_ddl),
            t_doc,
            len(related_doc),
            t_sql,
            len(related_sql),
        )
        
        return {
            "ddl": related_ddl,
            "doc": related_doc,
            "sql": related_sql
        }
