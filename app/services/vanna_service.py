from typing import List, Dict, Any, Optional
from vanna.legacy.chromadb.chromadb_vector import ChromaDB_VectorStore
from vanna.legacy.base import VannaBase
from app.services.schema_service import SchemaService
from sqlalchemy import text
from app.models.feedback_models import GoldenExample
from app.models.schema_models import SchemaSemanticMapping, SchemaBusinessRule, SchemaMetadata

class VannaService(ChromaDB_VectorStore, VannaBase):
    def __init__(self, config: Dict[str, Any] = None):
        if config is None:
            config = {}

        # Initialize ChromaDB at project root
        db_path = config.get("path", "./chroma_db")
        self.distance_threshold = config.get("distance_threshold", 1.8)  # Configurable threshold

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
        print("🧠 Starting Vanna Brain Sync...")
        
        # Clear existing collections to avoid duplicates
        try:
            collections_to_clear = ["ddl", "documentation", "sql"]
            for col_name in collections_to_clear:
                try:
                    self.chroma_client.delete_collection(name=col_name)
                    print(f"   ✅ Cleared collection: {col_name}")
                except Exception:
                    # Collection doesn't exist yet
                    pass
            print("   ✅ Cleared all existing vectors")
            
            # Re-initialize collections after deletion
            # This is crucial because the self.*_collection attributes still point to the deleted objects
            self.ddl_collection = self.chroma_client.get_or_create_collection(name="ddl")
            self.documentation_collection = self.chroma_client.get_or_create_collection(name="documentation")
            self.sql_collection = self.chroma_client.get_or_create_collection(name="sql")
            print("   ✅ Re-initialized collections")
            
        except Exception as e:
            print(f"   ⚠️  Could not clear collections: {e}")
        
        self._sync_ddl(schema_service)
        self._sync_documentation(schema_service)
        self._sync_golden_examples(schema_service)
        
        print("✅ Vanna Brain Sync Complete.")

    def _sync_ddl(self, service: SchemaService):
        """Train DDL from Schema Metadata"""
        # We construct DDLs for all tables managed by SchemaService
        tables = service.get_all_tables()
        
        for table in tables:
            # generating "Enhanced DDL" using metadata
            ddl = None
            try:
                with service.engine.connect() as conn:
                    res = conn.execute(text(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"))
                    row = res.fetchone()
                    if row:
                        ddl = row[0]
            except Exception as e:
                print(f"Error getting DDL for {table}: {e}")
            
            if ddl:
                # Add metadata context to DDL training
                self.train(ddl=ddl)
                print(f"   - Trained DDL: {table}")

    def _sync_documentation(self, service: SchemaService):
        """Train Documentation from Business Rules, Mappings, and Guide"""
        
        # 1. Business Rules
        with service.engine.connect() as conn:
            rules = conn.execute(text("SELECT * FROM schema_business_rules WHERE is_active=1")).mappings().all()
            for rule in rules:
                doc_text = f"**Rule: {rule['rule_name']}**\nCode: {rule['rule_code']}\nDescription: {rule['rule_description']}\nCorrect Example: {rule['example_correct']}\nSeverity: {rule['severity']}"
                self.train(documentation=doc_text)
        
        # 2. Semantic Mappings (Group by type for better context)
        with service.engine.connect() as conn:
            mappings = conn.execute(text("SELECT * FROM schema_semantic_mapping WHERE is_active=1")).mappings().all()
            for m in mappings:
                doc_text = f"**Term Mapping**\nKeyword: '{m['keyword']}' means column `{m['target_column']}` ({m['keyword_type']})\nCondition: {m['target_condition']}\nNote: {m['description']}"
                self.train(documentation=doc_text)
                
        # 3. External Guide (DATABASE_TABLES_GUIDE.md) with Chunking
        try:
            import os
            guide_path = "docs/DATABASE_TABLES_GUIDE.md"
            
            if os.path.exists(guide_path):
                with open(guide_path, "r", encoding="utf-8") as f:
                    content = f.read()
                
                # Split by Markdown sections (##)
                sections = content.split('\n## ')
                trained_count = 0
                
                for i, section in enumerate(sections):
                    section = section.strip()
                    if not section: continue
                    
                    # Re-add header for clarity (except maybe first intro)
                    header = f"## {section}" if i > 0 else section
                    
                    if len(header) > 100:
                        self.train(documentation=header)
                        trained_count += 1
                        
                print(f"   - Trained DATABASE_TABLES_GUIDE.md ({trained_count} chunks)")
            else:
                print(f"   ! Guide file not found: {guide_path}")
                
        except Exception as e:
            print(f"   ! Could not train from guide file: {e}")

    def _sync_golden_examples(self, service: SchemaService):
        """Train SQL from Golden Examples"""
        with service.engine.connect() as conn:
            examples = conn.execute(text("SELECT * FROM golden_examples WHERE is_active=1")).mappings().all()
            for ex in examples:
                self.train(question=ex['question_pattern'], sql=ex['expected_sql'])
                
        print(f"   - Trained {len(examples)} Golden Examples")

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
            print(f"Error querying Chroma: {e}")
            return []

    def get_rag_context(self, question: str, distance_threshold: float = None) -> Dict[str, List[str]]:
        """
        Retrieve relevant context for a question with score filtering.
        Returns mapped DDLs, Docs, and SQLs.
        """
        if distance_threshold is None:
            distance_threshold = self.distance_threshold

        import time
        import logging
        logger = logging.getLogger(__name__)

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
        logger.info(f"Vanna RAG Timing - Total: {total_time:.4f}s | DDL: {t_ddl:.4f}s (n={len(related_ddl)}) | Doc: {t_doc:.4f}s (n={len(related_doc)}) | SQL: {t_sql:.4f}s (n={len(related_sql)})")
        
        return {
            "ddl": related_ddl,
            "doc": related_doc,
            "sql": related_sql
        }
