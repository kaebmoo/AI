import os
import vanna
from vanna.base import VannaBase
from vanna.chromadb import ChromaDB_VectorStore
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any, Optional

# We will inject our existing AIService logic here later
# to keep using the same LLM providers/keys nicely.
class CustomLLM(VannaBase):
    def __init__(self, config=None):
        pass

    def system_message(self, message: str) -> any:
        return {"role": "system", "content": message}

    def user_message(self, message: str) -> any:
        return {"role": "user", "content": message}

    def assistant_message(self, message: str) -> any:
        return {"role": "assistant", "content": message}

    # This is the key method Vanna calls to get a response
    def submit_prompt(self, prompt, **kwargs) -> str:
        # We will separate the LLM call logic effectively.
        # For now, this class acts as a placeholder if we want to 
        # route strictly through our AIService. 
        # Ideally, we pass the AIService instance or callback here.
        if 'ai_service_callback' in kwargs:
            return kwargs['ai_service_callback'](prompt)
        return "SQL GENERATION PLACEHOLDER"

class VannaService(ChromaDB_VectorStore, CustomLLM):
    def __init__(self, config: Dict[str, Any] = None):
        if config is None:
            config = {}
            
        # Initialize ChromaDB
        # We use a local persistent path
        db_path = config.get("path", "./chroma_db")
        
        # Call ChromaDB_VectorStore init
        ChromaDB_VectorStore.__init__(self, config={'path': db_path})
        
        # Call CustomLLM init
        CustomLLM.__init__(self, config=config)

    def train_from_schema_service(self, schema_service):
        """
        Syncs entire knowledge base from SchemaService + Database
        """
        # 1. Train Golden Examples (SQL)
        self._train_golden_examples(schema_service)
        
        # 2. Train Schema DDL (Metadata)
        self._train_ddl(schema_service)
        
        # 3. Train Documentation (Business Rules + Semantics)
        self._train_documentation(schema_service)

    def _train_golden_examples(self, schema_service):
        """Fetch GoldenExamples from DB and train Vanna"""
        from app.models.feedback_models import GoldenExample
        # We need a db session here ideally, or use the service method
        # Assuming schema_service has access or we pass a db session
        # For now, let's assume we can fetch raw data via schema_service engine
        
        # Implementation to follow...
        pass
    
    def _train_ddl(self, schema_service):
        """Fetch tables and metadata to build DDLs"""
        # Implementation to follow...
        pass

    def _train_documentation(self, schema_service):
        """Fetch rules and mappings as documentation"""
        # Implementation to follow...
        pass

    def generate_sql_with_aiservice(self, question: str, ai_service_callback) -> str:
        """
        Main entry point.
        1. Vanna retrieves context (RAG).
        2. Vanna builds the prompt.
        3. Vanna calls submit_prompt -> which calls our ai_service_callback.
        """
        # Vanna's generate_sql internally calls submit_prompt
        # We can pass the callback via kwargs if modified, 
        # or we just rely on the Prompt construction and call LLM manually to be safer.
        
        # Manual RAG Flow to control the Prompt 100%
        
        # 1. Get Related Training Data
        related_ddl = self.get_related_ddl(question)
        related_doc = self.get_related_documentation(question)
        related_sql = self.get_similar_question_sql(question)
        
        # 2. Construct Prompt (Vanna has a get_sql_prompt method, or we use our own)
        # We might want to combine Vanna's retrieval with OUR existing prompt structure
        # for consistency.
        
        return {
            "related_ddl": related_ddl,
            "related_doc": related_doc,
            "related_sql": related_sql
        }
