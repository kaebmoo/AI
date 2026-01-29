import pandas as pd
import io
import json
from typing import List, Dict, Any, Optional
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session
from app.services.ai_service import AIService
from app.models.schema_models import SchemaMetadata, SchemaSemanticMapping, SchemaBusinessRule

class AnalyzerService:
    def __init__(self, db: Session, ai_service: AIService):
        self.db = db
        self.ai_service = ai_service

    def analyze_file(self, file_content: bytes, filename: str) -> Dict[str, Any]:
        """
        Analyze uploaded file (CSV/Excel) and return schema suggestions.
        """
        df = None
        if filename.endswith('.csv'):
            df = pd.read_csv(io.BytesIO(file_content))
        elif filename.endswith('.xlsx') or filename.endswith('.xls'):
            df = pd.read_excel(io.BytesIO(file_content))
        
        if df is None:
            raise ValueError("Unsupported file format")

        columns = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            # Safe sample values convert to native python types
            sample_values = df[col].dropna().head(5).astype(str).tolist()
            
            columns.append({
                "column_name": col,
                "data_type": dtype,
                "sample_values": sample_values
            })

        return {
            "source": filename,
            "columns": columns,
            "total_rows": len(df)
        }

    def analyze_database_table(self, table_name: str) -> Dict[str, Any]:
        """
        Introspect database table and get schema info.
        """
        inspector = inspect(self.db.bind)
        columns = []
        
        try:
            cols = inspector.get_columns(table_name)
            for col in cols:
                columns.append({
                    "column_name": col['name'],
                    "data_type": str(col['type']),
                    "nullable": col['nullable']
                })
        except Exception as e:
            raise ValueError(f"Table {table_name} not found or error: {str(e)}")

        return {
            "source": table_name,
            "columns": columns
        }

    async def get_ai_suggestions(self, schema_info: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send schema info to AI to get friendly names, descriptions, and mapping rules.
        """
        prompt = f"""
        Analyze this data schema and provide comprehensive suggestions for a Natural Language to SQL system.
        
        Source Name: {schema_info.get('source')}
        Total Rows: {schema_info.get('total_rows', 'N/A')}
        
        Columns & Samples:
        {json.dumps(schema_info.get('columns'), indent=2, ensure_ascii=False)}
        
        TASKS:
        1. Suggest Thai friendly names (display_name_th) and descriptions for each column.
        2. Identify semantic mapping keywords (common synonyms/terms users might use to refer to this column).
        3. Identify if the column is a Dimension (can group by) or Measure (numeric/calculable).
        4. Suggest 2-3 common business rules or calculations if applicable (e.g. Total Revenue = sum(amount)).

        OUTPUT JSON FORMAT ONLY:
        {{
            "columns": [
                {{
                    "column_name": "original_name",
                    "display_name_th": "ชื่อไทย",
                    "description": "คำอธิบาย",
                    "is_measure": boolean,
                    "is_dimension": boolean
                }}
            ],
            "potential_mappings": [
                {{
                    "keyword": "term/synonym",
                    "target_column": "column_name",
                    "relevance_score": 0.0-1.0
                }}
            ],
            "business_rules": [
                {{
                    "rule_name": "Rule Name",
                    "description": "Description",
                    "sql_condition": "SQL snippet or calculation logic"
                }}
            ]
        }}
        """
        
        # Use the generic generate_content method we added
        try:
             # Run in threadpool if it was blocking, but our generate_content is synchronous built on HTTP calls. 
             # For async FastAPI, we should ideally run this in threadpool.
             # However, since we are calling it from async method, let's keep it simple for now or use run_in_threadpool if strictly needed.
             # But wait, generate_content in implementations uses synchronous clients (anthropic, google-genai, httpx).
             # So we must wrap it.
             import anyio
             response_text = await anyio.to_thread.run_sync(
                 self.ai_service.generate_content, 
                 prompt
             )
             
             # Extract JSON from response
             json_str = response_text
             if "```json" in response_text:
                 json_str = response_text.split("```json")[1].split("```")[0]
             elif "```" in response_text:
                 json_str = response_text.split("```")[1].split("```")[0]
                 
             return json.loads(json_str)
             
        except Exception as e:
            print(f"AI Analysis Error: {e}")
            return {
                "error": str(e),
                "columns": [],
                "potential_mappings": [],
                "business_rules": []
            }
