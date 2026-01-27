"""
NT Revenue Assistant - AI Service
==================================
Service สำหรับเรียก AI API เพื่อแปลงคำถามเป็น SQL

รองรับ:
- Claude API (Anthropic)
- Google AI / Gemini API

Usage:
    # Claude
    ai_service = AIService(provider="claude", api_key="sk-ant-...")
    result = ai_service.query("รายได้รวมเดือนมกราคม 2568")
    
    # Gemini
    ai_service = AIService(provider="gemini", api_key="AIza...")
    result = ai_service.query("รายได้รวมเดือนมกราคม 2568")
"""

import json
import sqlite3
import re
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type, before_sleep_log
import logging

logger = logging.getLogger(__name__)

# Retry Configuration
def create_retry_decorator():
    """Create retry decorator with standard configuration"""
    # Import provider exceptions locally to avoid hard dependencies if not installed
    exceptions_to_retry = [
        httpx.TimeoutException, 
        httpx.ConnectError,
        httpx.ReadTimeout
    ]
    
    try:
        import anthropic
        exceptions_to_retry.extend([
            anthropic.RateLimitError, 
            anthropic.APIError,
            anthropic.APIConnectionError
        ])
    except ImportError:
        pass
        
    try:
        from google.api_core import exceptions as google_exceptions
        exceptions_to_retry.extend([
            google_exceptions.ResourceExhausted,
            google_exceptions.ServiceUnavailable,
            google_exceptions.DeadlineExceeded,
            google_exceptions.InternalServerError
        ])
    except ImportError:
        pass

    return retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(tuple(exceptions_to_retry)),
        reraise=True
    )

ai_retry = create_retry_decorator()

from .schema_service import SchemaService
from app.services.prompt_manager import PromptManager


@dataclass
class QueryResult:
    """Result from AI query"""
    question: str
    sql_query: str
    data: List[Dict]
    explanation: str
    tokens_used: int
    provider: str
    raw_response: Optional[str] = None
    error: Optional[str] = None


class AIProvider(ABC):
    """Abstract base class for AI providers"""
    
    @abstractmethod
    def generate_sql(self, question: str, system_prompt: str, history: List[Dict] = []) -> Dict[str, Any]:
        """Generate SQL from question"""
        pass
    
    @abstractmethod
    def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        """Explain query result"""
        pass


class ClaudeProvider(AIProvider):
    """Claude API provider"""
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                raise ImportError("Please install anthropic: pip install anthropic")
        return self._client
    
    @ai_retry
    def generate_sql(self, question: str, system_prompt: str, history: List[Dict] = []) -> Dict[str, Any]:
        """Generate SQL using Claude API with Tool Use"""
        
        # Prepare messages from history
        messages = []
        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            if role and content:
                messages.append({"role": role, "content": content})
        
        # Add current question
        messages.append({"role": "user", "content": question})
        # Add current question
        messages.append({"role": "user", "content": question})

        tools = [
            {
                "name": "execute_sql",
                "description": "Execute a SQL query against the revenue database",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The SQL SELECT query to execute"
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Brief explanation of what this query does (in Thai)"
                        }
                    },
                    "required": ["query", "explanation"]
                }
            }
        ]
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            tools=tools,
            messages=messages
        )
        
        # Extract SQL from tool use
        sql_query = None
        explanation = None
        
        for block in response.content:
            if block.type == "tool_use" and block.name == "execute_sql":
                sql_query = block.input.get("query")
                explanation = block.input.get("explanation")
                break
            elif block.type == "text":
                # Try to extract SQL from text response
                sql_match = re.search(r'```sql\s*(.*?)\s*```', block.text, re.DOTALL)
                if sql_match:
                    sql_query = sql_match.group(1).strip()
                explanation = block.text
        
        return {
            "sql": sql_query,
            "explanation": explanation,
            "tokens_used": response.usage.input_tokens + response.usage.output_tokens,
            "raw_response": str(response.content)
        }
    
    @ai_retry
    def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        """Explain query result using Claude"""
        
        # Limit data for context
        data_sample = data[:20] if len(data) > 20 else data
        
        prompt = f"""คำถามเดิม: {question}

SQL ที่ใช้:
```sql
{sql}
```

ผลลัพธ์ ({len(data)} rows):
```json
{json.dumps(data_sample, ensure_ascii=False, indent=2)}
```

กรุณาอธิบายผลลัพธ์นี้เป็นภาษาไทยที่เข้าใจง่าย พร้อม format ตัวเลขให้อ่านง่าย และไม่ใช้ emoji icon"""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )
        
        return response.content[0].text


class GeminiProvider(AIProvider):
    """Google Gemini API provider using google-genai SDK"""
    
    def __init__(self, api_key: str, model: str = "gemini-3-flash-preview"):
        self.api_key = api_key
        self.model = model
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            try:
                from google import genai
                self._client = genai.Client(api_key=self.api_key)
            except ImportError:
                raise ImportError("Please install google-genai: pip install google-genai")
        return self._client
    
    @ai_retry
    def generate_sql(self, question: str, system_prompt: str, history: List[Dict] = []) -> Dict[str, Any]:
        """Generate SQL using Gemini API with Tool Use"""
        
        # Define tool using google-genai types if possible, or simple dict
        # The new SDK supports python functions directly or schema dicts
        
        def execute_sql(query: str, explanation: str):
            """Execute a SQL query against the revenue database"""
            pass

        try:
            from google.genai import types
            
            # Tools config
            tools = [types.Tool(function_declarations=[
                types.FunctionDeclaration(
                    name="execute_sql",
                    description="Execute a SQL query against the revenue database",
                    parameters=types.Schema(
                        type="OBJECT",
                        properties={
                            "query": types.Schema(type="STRING", description="The SQL SELECT query to execute"),
                            "explanation": types.Schema(type="STRING", description="Brief explanation of what this query does (in Thai)")
                        },
                        required=["query", "explanation"]
                    )
                )
            ])]

            # Prepare contents with history
            contents = []
            for msg in history:
                role = "user" if msg.get("role") == "user" else "model"
                contents.append(types.Content(
                    role=role,
                    parts=[types.Part(text=msg.get("content", ""))]
                ))
            
            # Add current question
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=question)]
            ))

            logger.info(f"Gemini: Sending request for '{question}' with {len(history)} history items.")
            import time
            t_start = time.time()

            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=tools,
                    temperature=0.0,
                    # Explicitly disable AFC to strictly return tool calls
                    automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True) 
                )
            )
            
            logger.info(f"Gemini: Received response in {time.time() - t_start:.2f}s")
            
            # Extract SQL from tool call
            sql_query = None
            explanation = None
            raw_response = str(response)

            # Check for function calls in candidates
            if response.candidates and response.candidates[0].content.parts:
                for part in response.candidates[0].content.parts:
                    if part.function_call and part.function_call.name == "execute_sql":
                        args = part.function_call.args
                        sql_query = args.get("query")
                        explanation = args.get("explanation")
                        break
            
            # Fallback text extraction if tool use fails but returns text
            if not sql_query and response.text:
                sql_match = re.search(r'```sql\s*(.*?)\s*```', response.text, re.DOTALL)
                if sql_match:
                    sql_query = sql_match.group(1).strip()
                explanation = response.text
            
            if not sql_query:
                logger.warning(f"Gemini failed to generate SQL. Raw response: {response.text}")

            # Get token count if available
            tokens_used = 0
            if response.usage_metadata:
                tokens_used = (
                    response.usage_metadata.prompt_token_count + 
                    response.usage_metadata.candidates_token_count
                )
                
            return {
                "sql": sql_query,
                "explanation": explanation,
                "tokens_used": tokens_used,
                "raw_response": raw_response
            }
            
        except Exception as e:
            # Fallback to text-only if SDK usage fails
            return self._generate_sql_text_only(question, system_prompt)
    
    def _generate_sql_text_only(self, question: str, system_prompt: str) -> Dict[str, Any]:
        """Fallback: Generate SQL using text-only mode"""
        
        from google.genai import types

        prompt = f"""{system_prompt}

คำถาม: {question}

กรุณาสร้าง SQL query และอธิบายเป็นภาษาไทย

ตอบในรูปแบบ:
```sql
[SQL QUERY HERE]
```

คำอธิบาย: [EXPLANATION IN THAI]"""
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt
        )
        text = response.text if response.text else ""
        
        # Extract SQL
        sql_match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL)
        sql_query = sql_match.group(1).strip() if sql_match else None
        
        return {
            "sql": sql_query,
            "explanation": text,
            "tokens_used": 0,
            "raw_response": text
        }
    
    @ai_retry
    def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        """Explain query result using Gemini"""
        
        from google.genai import types

        data_sample = data[:20] if len(data) > 20 else data
        
        prompt = f"""คำถามเดิม: {question}

SQL ที่ใช้:
```sql
{sql}
```

ผลลัพธ์ ({len(data)} rows):
```json
{json.dumps(data_sample, ensure_ascii=False, indent=2)}
```

กรุณาอธิบายผลลัพธ์นี้เป็นภาษาไทยที่เข้าใจง่าย พร้อม format ตัวเลขให้อ่านง่าย"""
        
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt
            )
        )
        return response.text if response.text else ""


class AIService:
    """Main AI Service for NT Revenue Assistant"""
    
    def __init__(
        self,
        provider: str,
        api_key: str,
        db_path: str = "revenue.db",
        model: Optional[str] = None,
        prompt_manager: Optional[PromptManager] = None
    ):
        """
        Initialize AI Service
        
        Args:
            provider: "claude" or "gemini"
            api_key: API key for the provider
            db_path: Path to SQLite database
            model: Model name (optional, uses default if not specified)
            prompt_manager: PromptManager instance for version control
        """
        self.provider_name = provider
        self.db_path = db_path
        self.prompt_manager = prompt_manager
        
        # Initialize schema service
        self.schema_service = SchemaService(db_path)
        
        # Initialize AI provider
        if provider == "claude":
            self.provider = ClaudeProvider(
                api_key=api_key,
                model=model or "claude-sonnet-4-20250514"
            )
        elif provider == "gemini":
            self.provider = GeminiProvider(
                api_key=api_key,
        model=model or "gemini-2.0-flash-exp"
            )
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'claude' or 'gemini'")
        
        # Cache system prompt
        self._system_prompt = None
    
    @property
    def system_prompt(self) -> str:
        """Get cached system prompt"""
        if self._system_prompt is None:
            if self.prompt_manager:
                base_instruction = self.schema_service.get_default_instruction(self.provider_name)
                schema_context = self.schema_service.get_schema_context()
                self._system_prompt = self.prompt_manager.compose_system_prompt(
                    base_prompt=base_instruction,
                    schema_text=schema_context
                )
            else:
                self._system_prompt = self.schema_service.build_system_prompt(
                    ai_provider=self.provider_name
                )
        return self._system_prompt
    
    def refresh_schema(self):
        """Refresh schema cache"""
        self.schema_service.refresh_cache()
        self._system_prompt = None
    
    def validate_sql(self, sql: str) -> tuple[bool, str]:
        """
        Validate SQL query for safety
        
        Returns:
            (is_valid, error_message)
        """
        if not sql:
            return False, "SQL query is empty"
        
        sql_upper = sql.upper().strip()
        
        # Check for dangerous operations
        dangerous = ['INSERT', 'UPDATE', 'DELETE', 'DROP', 'CREATE', 'ALTER', 'TRUNCATE']
        for keyword in dangerous:
            if keyword in sql_upper:
                return False, f"SQL contains forbidden keyword: {keyword}"
        
        # Must be SELECT
        if not sql_upper.startswith('SELECT'):
            return False, "Only SELECT queries are allowed"
        
        return True, ""
    
    def execute_sql(self, sql: str) -> List[Dict]:
        """Execute SQL query and return results"""
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        try:
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
    
    def query(self, question: str, explain: bool = True, history: List[Dict] = []) -> QueryResult:
        """
        Process a natural language question
        
        Args:
            question: Question in Thai or English
            explain: Whether to generate explanation
        
        Returns:
            QueryResult with SQL, data, and explanation
        """
        
        # Generate SQL
        logger.info(f"AIService: Querying {self.provider_name} for '{question}'")
        import time
        t_start = time.time()
        
        ai_result = self.provider.generate_sql(question, self.system_prompt, history)
        
        logger.info(f"AIService: Generated SQL in {time.time() - t_start:.2f}s")
        
        sql_query = ai_result.get("sql")
        tokens_used = ai_result.get("tokens_used", 0)
        
        # Validate SQL
        is_valid, error_msg = self.validate_sql(sql_query)
        
        if not is_valid:
            return QueryResult(
                question=question,
                sql_query=sql_query or "",
                data=[],
                explanation="",
                tokens_used=tokens_used,
                provider=self.provider_name,
                error=error_msg
            )
        
        # Execute SQL
        try:
            data = self.execute_sql(sql_query)
        except Exception as e:
            return QueryResult(
                question=question,
                sql_query=sql_query,
                data=[],
                explanation="",
                tokens_used=tokens_used,
                provider=self.provider_name,
                error=f"SQL execution error: {str(e)}"
            )
        
        # Generate explanation
        explanation = ai_result.get("explanation", "")
        if explain and data:
            try:
                explanation = self.provider.explain_result(
                    question, sql_query, data, self.system_prompt
                )
            except:
                pass  # Keep original explanation if API fails
        
        return QueryResult(
            question=question,
            sql_query=sql_query,
            data=data,
            explanation=explanation,
            tokens_used=tokens_used,
            provider=self.provider_name
        )
    
    def chat(
        self,
        question: str,
        history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """
        Chat interface with conversation history
        
        Args:
            question: User's question
            history: List of previous messages [{role: "user/assistant", content: "..."}]
        
        Returns:
            Dict with response and updated history
        """
        
        result = self.query(question, history=history or [])
        
        response = {
            "question": question,
            "sql": result.sql_query,
            "data": result.data,
            "explanation": result.explanation,
            "error": result.error,
            "tokens_used": result.tokens_used
        }
        
        # Update history
        new_history = history or []
        new_history.append({"role": "user", "content": question})
        new_history.append({"role": "assistant", "content": result.explanation or result.error})
        
        return {
            "response": response,
            "history": new_history
        }


# =========================================================
# Factory Functions
# =========================================================

def create_claude_service(api_key: str, db_path: str = "revenue.db", model: Optional[str] = None, prompt_manager: Optional[PromptManager] = None) -> AIService:
    """Create AI service with Claude provider"""
    return AIService(provider="claude", api_key=api_key, db_path=db_path, model=model, prompt_manager=prompt_manager)


def create_gemini_service(api_key: str, db_path: str = "revenue.db", model: Optional[str] = None, prompt_manager: Optional[PromptManager] = None) -> AIService:
    """Create AI service with Gemini provider"""
    return AIService(provider="gemini", api_key=api_key, db_path=db_path, model=model, prompt_manager=prompt_manager)


# =========================================================
# Example Usage
# =========================================================

if __name__ == "__main__":
    import os
    
    # Example with Claude
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    if claude_key:
        service = create_claude_service(claude_key)
        result = service.query("รายได้รวมเดือนมกราคม 2568")
        print(f"SQL: {result.sql_query}")
        print(f"Data: {result.data[:5]}")
        print(f"Explanation: {result.explanation}")
    
    # Example with Gemini
    gemini_key = os.getenv("GOOGLE_API_KEY")
    if gemini_key:
        service = create_gemini_service(gemini_key)
        result = service.query("รายได้รวมเดือนมกราคม 2568")
        print(f"SQL: {result.sql_query}")
        print(f"Data: {result.data[:5]}")
        print(f"Explanation: {result.explanation}")
