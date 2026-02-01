"""
NT AI Assistant - AI Service
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
    retry_count: int = 0  # จำนวนครั้งที่ retry
    retry_history: Optional[List[Dict]] = None  # ประวัติการ retry


@dataclass
class RetryStatus:
    """Status update during retry process"""
    attempt: int
    max_attempts: int
    status: str  # "generating", "executing", "error", "retrying", "success", "failed"
    message: str
    sql_query: Optional[str] = None
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

    @abstractmethod
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate generic content"""
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
            max_tokens=2048,  # Increased for complex SQL queries
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

        question_lower = question.lower()

        # Detect complex queries that need more tokens
        complex_keywords = [
            'crosstab', 'pivot', 'ตาราง', 'แยกตาม',  # Original
            'เปรียบเทียบ', 'ผลต่าง', 'ไตรมาส', 'quarter',  # Comparison
            'เทียบ', 'vs', 'versus', 'ต่างกัน',  # vs
            'แนวโน้ม', 'trend', 'growth', 'การเติบโต',  # Trends
            'breakdown', 'แจกแจง', 'รายละเอียด',  # Breakdown
            'ทุกกลุ่ม', 'ทุกหน่วยงาน', 'ทั้งหมด'  # All groups
        ]
        is_complex = any(keyword in question_lower for keyword in complex_keywords)

        # Increase sample limit for complex queries
        sample_limit = 100 if is_complex else (50 if len(data) > 20 else 30)
        data_sample = data[:sample_limit] if len(data) > sample_limit else data

        # Estimate tokens needed - higher for complex queries
        if is_complex:
            estimated_tokens = 6000 if len(data) > 10 else 4000
        else:
            estimated_tokens = 3000 if len(data) > 20 else 2000

        prompt = f"""คำถามเดิม: {question}

SQL ที่ใช้:
```sql
{sql}
```

ผลลัพธ์ ({len(data)} rows):
```json
{json.dumps(data_sample, ensure_ascii=False, indent=2)}
```

กรุณาอธิบายผลลัพธ์นี้เป็นภาษาไทยที่เข้าใจง่าย พร้อม format ตัวเลขให้อ่านง่าย และไม่ใช้ emoji icon
หากมีข้อมูลหลายแถว ให้สรุปเป็นภาพรวมและไฮไลท์ข้อมูลสำคัญ
สำคัญ: ต้องแสดงข้อมูลทุกแถวในตารางให้ครบถ้วน อย่าตัดข้อมูลออก"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=estimated_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        result_text = response.content[0].text

        # Check for truncation via stop_reason
        if response.stop_reason == "max_tokens":
            logger.warning("Claude response truncated due to max_tokens")
            result_text += "\n\n(หมายเหตุ: คำอธิบายอาจถูกตัดทอนเนื่องจากความยาวเกินกำหนด กรุณาถามแยกเป็นคำถามย่อยๆ)"

        return result_text

    @ai_retry
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Claude"""
        messages = [{"role": "user", "content": prompt}]
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system_prompt or "",
            messages=messages
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
                    max_output_tokens=2048,  # Increased for complex SQL queries
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

        # Determine sample size and complexity based on query characteristics
        question_lower = question.lower()

        # Detect complex queries that need more tokens
        complex_keywords = [
            'crosstab', 'pivot', 'ตาราง', 'แยกตาม',  # Original
            'เปรียบเทียบ', 'ผลต่าง', 'ไตรมาส', 'quarter',  # Comparison
            'เทียบ', 'vs', 'versus', 'ต่างกัน',  # vs
            'แนวโน้ม', 'trend', 'growth', 'การเติบโต',  # Trends
            'breakdown', 'แจกแจง', 'รายละเอียด',  # Breakdown
            'ทุกกลุ่ม', 'ทุกหน่วยงาน', 'ทั้งหมด'  # All groups
        ]
        is_complex = any(keyword in question_lower for keyword in complex_keywords)

        # Increase sample limit for complex queries
        sample_limit = 100 if is_complex else (50 if len(data) > 20 else 30)
        data_sample = data[:sample_limit] if len(data) > sample_limit else data

        # Estimate tokens needed - significantly higher for complex queries
        # Complex comparison tables with multiple columns need ~4000-6000 tokens
        if is_complex:
            estimated_tokens = 6000 if len(data) > 10 else 4000
        else:
            estimated_tokens = 3000 if len(data) > 20 else 2000

        prompt = f"""คำถามเดิม: {question}

SQL ที่ใช้:
```sql
{sql}
```

ผลลัพธ์ ({len(data)} rows):
```json
{json.dumps(data_sample, ensure_ascii=False, indent=2)}
```

กรุณาอธิบายผลลัพธ์นี้เป็นภาษาไทยที่เข้าใจง่าย พร้อม format ตัวเลขให้อ่านง่าย และไม่ใช้ emoji icon
หากมีข้อมูลหลายแถว ให้สรุปเป็นภาพรวมและไฮไลท์ข้อมูลสำคัญ
สำคัญ: ต้องแสดงข้อมูลทุกแถวในตารางให้ครบถ้วน อย่าตัดข้อมูลออก"""

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=estimated_tokens
            )
        )

        result_text = response.text if response.text else ""

        # Check for truncation by examining finish_reason
        if response.candidates and response.candidates[0].finish_reason:
            finish_reason = str(response.candidates[0].finish_reason)
            if 'MAX_TOKENS' in finish_reason or 'LENGTH' in finish_reason.upper():
                logger.warning(f"Gemini response truncated: {finish_reason}")
                result_text += "\n\n(หมายเหตุ: คำอธิบายอาจถูกตัดทอนเนื่องจากความยาวเกินกำหนด กรุณาถามแยกเป็นคำถามย่อยๆ)"

        return result_text

    @ai_retry
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Gemini"""
        from google.genai import types
        
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            max_output_tokens=4000
        ) if system_prompt else None

        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config=config
        )
        return response.text if response.text else ""


class MatchaProvider(AIProvider):
    """Matcha AI (Internal Gateway) provider using OpenAI-Compatible API

    Enhanced with:
    - Few-shot examples for better SQL generation
    - Semantic mapping hints for Thai abbreviations
    - Improved SQL extraction
    """

    def __init__(self, api_key: str, api_url: str, model: str = "gpt-4o", db_path: Optional[str] = None):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.db_path = db_path
        self._examples_service = None

    @property
    def examples_service(self):
        """Lazy load examples service"""
        if self._examples_service is None and self.db_path:
            try:
                from app.services.matcha_examples import MatchaExamplesService
                self._examples_service = MatchaExamplesService(self.db_path)
            except Exception as e:
                logger.warning(f"Could not load MatchaExamplesService: {e}")
        return self._examples_service

    def _get_few_shot_messages(self) -> List[Dict]:
        """Get few-shot example messages"""
        try:
            from app.services.matcha_examples import get_matcha_few_shot_messages
            return get_matcha_few_shot_messages()
        except Exception as e:
            logger.warning(f"Could not load few-shot messages: {e}")
            return []

    def _enhance_question_with_hints(self, question: str) -> str:
        """Add semantic hints to question if keywords detected"""
        if not self.examples_service:
            return question

        try:
            hints = self.examples_service.build_semantic_hints(question)
            if hints:
                return f"{question}\n\n{hints}"
        except Exception as e:
            logger.debug(f"Could not build semantic hints: {e}")

        return question

    def _extract_sql_from_response(self, text: str) -> Optional[str]:
        """
        Enhanced SQL extraction with multiple fallback patterns

        Returns:
            Extracted SQL query or None
        """
        # Pattern 1: ```sql ... ```
        sql_match = re.search(r'```sql\s*(.*?)\s*```', text, re.DOTALL | re.IGNORECASE)
        if sql_match:
            return sql_match.group(1).strip()

        # Pattern 2: ``` ... ``` (generic code block)
        code_match = re.search(r'```\s*(.*?)\s*```', text, re.DOTALL)
        if code_match:
            code = code_match.group(1).strip()
            # Check if it looks like SQL
            if re.match(r'(?:SELECT|WITH)\s+', code, re.IGNORECASE):
                return code

        # Pattern 3: Raw SQL starting with SELECT or WITH
        # Match until we hit a clear ending (double newline, explanation text, or end)
        raw_patterns = [
            # SELECT ... until double newline or explanation
            r'(SELECT\s+[\s\S]*?)(?:\n\n|คำอธิบาย|Explanation|$)',
            # WITH ... until double newline or explanation
            r'(WITH\s+[\s\S]*?)(?:\n\n|คำอธิบาย|Explanation|$)',
            # Fallback: SELECT/WITH until semicolon or end
            r'((?:WITH|SELECT)\s+.*?)(?:;|$)',
        ]

        for pattern in raw_patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                sql = match.group(1).strip()
                # Remove trailing semicolon if present
                sql = sql.rstrip(';').strip()
                if sql:
                    return sql

        return None

    def _extract_explanation(self, text: str, sql: Optional[str] = None) -> str:
        """Extract explanation from response"""
        # Try to find explicit explanation
        patterns = [
            r'คำอธิบาย[:\s]*(.*?)(?:\n\n|$)',
            r'Explanation[:\s]*(.*?)(?:\n\n|$)',
            r'หมายเหตุ[:\s]*(.*?)(?:\n\n|$)',
        ]

        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: text after SQL block
        if sql and sql in text:
            idx = text.find(sql) + len(sql)
            remaining = text[idx:].strip()
            # Clean up remaining text
            remaining = re.sub(r'^```\s*', '', remaining)
            remaining = re.sub(r'^\s*\n', '', remaining)
            if remaining:
                return remaining[:500]  # Limit length

        return text[:500] if text else ""

    @ai_retry
    def generate_sql(self, question: str, system_prompt: str, history: List[Dict] = []) -> Dict[str, Any]:
        """Generate SQL using Matcha API (OpenAI Compatible) with few-shot examples"""

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        # Prepare messages with few-shot examples
        messages = [{"role": "system", "content": system_prompt}]

        # Add few-shot examples (before history)
        few_shot = self._get_few_shot_messages()
        messages.extend(few_shot)

        # Add conversation history
        for msg in history:
            role = msg.get("role")
            content = msg.get("content")
            if role and content:
                messages.append({"role": role, "content": content})

        # Enhance question with semantic hints
        enhanced_question = self._enhance_question_with_hints(question)
        messages.append({"role": "user", "content": enhanced_question})

        logger.debug(f"Matcha: Sending {len(messages)} messages (including {len(few_shot)} few-shot examples)")

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': 0.1,  # Low temperature for consistent SQL generation
            'max_tokens': 2048,  # Increased for complex SQL queries
            'top_p': 0.95
        }

        try:
            with httpx.Client(verify=False, timeout=60.0) as client:
                response = client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            ai_message = result['choices'][0]['message']['content']
            total_tokens = result.get('usage', {}).get('total_tokens', 0)

            # Enhanced SQL extraction
            sql_query = self._extract_sql_from_response(ai_message)
            explanation = self._extract_explanation(ai_message, sql_query)

            return {
                "sql": sql_query,
                "explanation": explanation,
                "tokens_used": total_tokens,
                "raw_response": ai_message
            }

        except Exception as e:
            logger.error(f"Matcha API Error: {str(e)}")
            raise

    @ai_retry
    def explain_result(self, question: str, sql: str, data: List[Dict], system_prompt: str) -> str:
        """Explain query result using Matcha AI"""

        question_lower = question.lower()

        # Detect complex queries that need more tokens
        complex_keywords = [
            'crosstab', 'pivot', 'ตาราง', 'แยกตาม',  # Original
            'เปรียบเทียบ', 'ผลต่าง', 'ไตรมาส', 'quarter',  # Comparison
            'เทียบ', 'vs', 'versus', 'ต่างกัน',  # vs
            'แนวโน้ม', 'trend', 'growth', 'การเติบโต',  # Trends
            'breakdown', 'แจกแจง', 'รายละเอียด',  # Breakdown
            'ทุกกลุ่ม', 'ทุกหน่วยงาน', 'ทั้งหมด'  # All groups
        ]
        is_complex = any(keyword in question_lower for keyword in complex_keywords)

        # Increase sample limit for complex queries
        sample_limit = 100 if is_complex else (50 if len(data) > 20 else 30)
        data_sample = data[:sample_limit] if len(data) > sample_limit else data

        # Estimate tokens needed - higher for complex queries
        if is_complex:
            estimated_tokens = 6000 if len(data) > 10 else 4000
        else:
            estimated_tokens = 3000 if len(data) > 20 else 2000

        prompt = f"""คำถามเดิม: {question}

SQL ที่ใช้:
```sql
{sql}
```

ผลลัพธ์ ({len(data)} rows):
```json
{json.dumps(data_sample, ensure_ascii=False, indent=2)}
```

กรุณาอธิบายผลลัพธ์นี้เป็นภาษาไทยที่เข้าใจง่าย พร้อม format ตัวเลขให้อ่านง่าย และไม่ใช้ emoji icon
หากมีข้อมูลหลายแถว ให้สรุปเป็นภาพรวมและไฮไลท์ข้อมูลสำคัญ
สำคัญ: ต้องแสดงข้อมูลทุกแถวในตารางให้ครบถ้วน อย่าตัดข้อมูลออก"""

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        payload = {
            'model': self.model,
            'messages': [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ],
            'temperature': 0.5,  # Lower for more consistent output
            'max_tokens': estimated_tokens
        }

        try:
            with httpx.Client(verify=False, timeout=120.0) as client:  # Increased timeout for longer responses
                response = client.post(self.api_url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()

            content = result['choices'][0]['message']['content']

            # Check if response was truncated (ended mid-sentence)
            finish_reason = result['choices'][0].get('finish_reason', '')
            if finish_reason == 'length':
                logger.warning("Matcha response was truncated due to max_tokens limit")
                content += "\n\n(หมายเหตุ: คำอธิบายอาจถูกตัดทอนเนื่องจากความยาวเกินกำหนด กรุณาถามแยกเป็นคำถามย่อยๆ)"

            return content

        except Exception as e:
            logger.error(f"Matcha Explain Error: {str(e)}")
            return "ไม่สามารถอธิบายผลลัพธ์ได้เนื่องจากเกิดข้อผิดพลาดในการเชื่อมต่อ AI"

    @ai_retry
    def generate_content(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate content using Matcha AI"""
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {self.api_key}'
        }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': 0.7,
            'max_tokens': 4000
        }

        with httpx.Client(verify=False, timeout=60.0) as client:
            response = client.post(self.api_url, headers=headers, json=payload)
            response.raise_for_status()
            result = response.json()
            
        return result['choices'][0]['message']['content']

class AIService:
    """Main AI Service for NT AI Assistant"""
    
    def __init__(
        self,
        provider: str,
        api_key: str,
        db_path: str = "revenue.db",
        model: Optional[str] = None,
        prompt_manager: Optional[PromptManager] = None,
        **kwargs
    ):
        """
        Initialize AI Service
        
        Args:
            provider: "claude", "gemini", or "matcha"
            api_key: API key for the provider
            db_path: Path to SQLite database
            model: Model name (optional, uses default if not specified)
            prompt_manager: PromptManager instance for version control
            **kwargs: Additional arguments for providers (e.g. api_url)
        """
        self.provider_name = provider
        self.db_path = db_path
        self.prompt_manager = prompt_manager
        
        # Determine database engine from path/url
        db_engine = "sqlite"
        if "postgres" in db_path:
            db_engine = "postgresql"
        elif "mssql" in db_path or "sqlserver" in db_path:
            db_engine = "mssql"
            
        # Initialize schema service
        self.schema_service = SchemaService(db_path=db_path, db_engine=None)
        
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
        elif provider == "matcha":
            api_url = kwargs.get("api_url")
            if not api_url:
                raise ValueError("api_url is required for matcha provider")
            self.provider = MatchaProvider(
                api_key=api_key,
                api_url=api_url,
                model=model or "gpt-4o",
                db_path=db_path  # Pass db_path for loading few-shot examples
            )
        else:
            raise ValueError(f"Unknown provider: {provider}. Use 'claude', 'gemini', or 'matcha'")
        
        # Cache system prompts by context
        self._system_prompts: Dict[str, str] = {}
    
    def get_system_prompt(self, context_name: str = "revenue") -> str:
        """Get cached system prompt for specific context"""
        if context_name not in self._system_prompts:
            if self.prompt_manager:
                base_instruction = self.schema_service.get_default_instruction(self.provider_name, context_name=context_name)
                schema_context = self.schema_service.get_schema_context(context_name=context_name)
                self._system_prompts[context_name] = self.prompt_manager.compose_system_prompt(
                    base_prompt=base_instruction,
                    schema_text=schema_context
                )
            else:
                self._system_prompts[context_name] = self.schema_service.build_system_prompt(
                    ai_provider=self.provider_name,
                    context_name=context_name
                )
        return self._system_prompts[context_name]
    
    @property
    def system_prompt(self) -> str:
        """Legacy property for backward compatibility (defaults to revenue)"""
        return self.get_system_prompt("revenue")
    
    def refresh_schema(self):
        """Refresh schema cache"""
        self.schema_service.refresh_cache()
        self._system_prompts.clear()
    
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
        # Logic update: Allow (SELECT ... ) which can happen with UNION or subqueries
        # Also remove any leading parenthesis for the check
        normalized_sql = sql_upper.lstrip('(').strip()
        
        if not (normalized_sql.startswith('SELECT') or normalized_sql.startswith('WITH')):
            return False, "Only SELECT queries (or Common Table Expressions starting with WITH) are allowed"
        
        return True, ""
    
    def execute_sql(self, sql: str) -> List[Dict]:
        """Execute SQL query and return results"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            # logger.error(f"SQL execution error for query '{sql}': {e}")
            raise
        finally:
            if conn:
                conn.close()

    def generate_content(self, prompt: str) -> str:
        """Generate generic content using the configured provider"""
        return self.provider.generate_content(prompt, system_prompt=self.system_prompt)

    def _find_similar_values(self, sql: str, limit: int = 5, context_name: str = "revenue") -> Dict[str, List[str]]:
        """
        Find actual values in database for columns used in WHERE clause.
        Helps AI understand what values exist when query returns 0 rows.

        Returns:
            Dict mapping column names to sample values found in DB
        """
        import re
        suggestions = {}
        
        # Get table name for context
        try:
            context_info = self.schema_service.get_context_info(context_name)
            table_name = context_info['main_view'] if context_info else 'revenue_search'
        except:
            table_name = 'revenue_search'

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Extract column conditions from WHERE clause
            # Patterns: column = 'value', column LIKE '%value%', column IN (...)
            where_match = re.search(r'WHERE\s+(.+?)(?:GROUP BY|ORDER BY|LIMIT|$)', sql, re.IGNORECASE | re.DOTALL)
            if not where_match:
                return suggestions

            where_clause = where_match.group(1)

            # Find column = 'value' patterns
            eq_patterns = re.findall(r"(\w+)\s*=\s*'([^']+)'", where_clause, re.IGNORECASE)
            like_patterns = re.findall(r"(\w+)\s+LIKE\s+'%?([^%']+)%?'", where_clause, re.IGNORECASE)

            all_patterns = eq_patterns + like_patterns

            for column, value in all_patterns:
                # Skip common columns that don't need suggestions
                if column.lower() in ('year', 'month', 'date'):
                    continue

                try:
                    # Find distinct values that might match
                    query = f"""
                        SELECT DISTINCT "{column}"
                        FROM {table_name}
                        WHERE "{column}" IS NOT NULL
                        LIMIT {limit * 2}
                    """
                    cursor.execute(query)
                    all_values = [row[0] for row in cursor.fetchall() if row[0]]

                    # Find similar values (containing search term or similar)
                    search_term = value.lower()
                    similar = []
                    exact_exists = False

                    for v in all_values:
                        v_lower = str(v).lower()
                        if v_lower == search_term:
                            exact_exists = True
                        elif search_term in v_lower or v_lower in search_term:
                            similar.append(str(v))

                    # If exact value doesn't exist, provide suggestions
                    if not exact_exists:
                        if similar:
                            suggestions[column] = similar[:limit]
                        else:
                            # No similar found, show sample values
                            suggestions[column] = [str(v) for v in all_values[:limit]]

                except Exception as e:
                    # logger.debug(f"Could not find values for column {column}: {e}")
                    continue

            conn.close()

        except Exception as e:
            # logger.warning(f"Error finding similar values: {e}")
            pass

        return suggestions

    def _check_zero_results_reason(self, sql: str, context_name: str = "revenue") -> Optional[str]:
        """
        Analyze why a query might return 0 results.
        Returns hint text if issues found.
        """
        suggestions = self._find_similar_values(sql, context_name=context_name)

        if not suggestions:
            return None

        hint_parts = ["ค่าที่ใช้ใน WHERE clause อาจไม่ตรงกับข้อมูลจริง:"]

        for column, values in suggestions.items():
            values_str = ", ".join([f"'{v}'" for v in values[:5]])
            hint_parts.append(f"  - Column '{column}': ค่าที่มีในระบบ เช่น {values_str}")

        return "\n".join(hint_parts)
    
    def query(self, question: str, explain: bool = True, history: List[Dict] = [], context_name: str = "revenue") -> QueryResult:
        """
        Process a natural language question
        
        Args:
            question: Question in Thai or English
            explain: Whether to generate explanation
            context_name: Data scope (revenue, expense, etc.)
        
        Returns:
            QueryResult with SQL, data, and explanation
        """
        
        system_prompt = self.get_system_prompt(context_name)
        
        # Generate SQL
        # logger.info(f"AIService: Querying {self.provider_name} [{context_name}] for '{question}'")
        import time
        t_start = time.time()
        
        ai_result = self.provider.generate_sql(question, system_prompt, history)
        
        # logger.info(f"AIService: Generated SQL in {time.time() - t_start:.2f}s")
        
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
                    question, sql_query, data, system_prompt
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
    
    def query_with_retry(
        self,
        question: str,
        max_retries: int = 3,
        history: List[Dict] = [],
        on_status: Optional[Callable[[RetryStatus], None]] = None,
        explain: bool = True,
        context_name: str = "revenue"
    ) -> QueryResult:
        """
        Process question with automatic retry on SQL errors.

        When SQL generation or execution fails, sends the error back to AI
        to self-correct and try again.

        Args:
            question: User's question
            max_retries: Maximum retry attempts (default 3)
            history: Conversation history
            on_status: Callback function for status updates
            explain: Whether to generate explanation
            context_name: Data context (revenue, expense)

        Returns:
            QueryResult with retry information
        """

        def notify(attempt: int, status: str, message: str, sql: str = None, error: str = None):
            """Send status notification if callback provided"""
            if on_status:
                on_status(RetryStatus(
                    attempt=attempt,
                    max_attempts=max_retries + 1,  # +1 for initial attempt
                    status=status,
                    message=message,
                    sql_query=sql,
                    error=error
                ))

        retry_history = []
        total_tokens = 0
        current_history = list(history)  # Copy to avoid mutation
        system_prompt = self.get_system_prompt(context_name)

        for attempt in range(max_retries + 1):  # +1 for initial attempt
            attempt_num = attempt + 1

            # Status: Generating SQL
            notify(attempt_num, "generating",
                   f"กำลังสร้าง SQL ({context_name})... (ครั้งที่ {attempt_num})")

            # Generate SQL
            try:
                if attempt == 0:
                    # First attempt - use original question
                    ai_result = self.provider.generate_sql(
                        question, system_prompt, current_history
                    )
                else:
                    # Retry attempt - include error context
                    retry_prompt = self._build_retry_prompt(
                        question,
                        retry_history[-1] if retry_history else {}
                    )
                    ai_result = self.provider.generate_sql(
                        retry_prompt, system_prompt, current_history
                    )

            except Exception as e:
                # logger.error(f"AI generation error on attempt {attempt_num}: {str(e)}")
                notify(attempt_num, "error",
                       f"เกิดข้อผิดพลาดในการติดต่อ AI: {str(e)}")

                retry_history.append({
                    "attempt": attempt_num,
                    "error_type": "generation_error",
                    "error": str(e)
                })
                continue

            sql_query = ai_result.get("sql")
            total_tokens += ai_result.get("tokens_used", 0)

            # Check if SQL was generated
            if not sql_query:
                # logger.warning(f"No SQL generated on attempt {attempt_num}")
                notify(attempt_num, "error",
                       "AI ไม่สามารถสร้าง SQL ได้ กำลังลองใหม่...")

                retry_history.append({
                    "attempt": attempt_num,
                    "error_type": "no_sql",
                    "error": "AI did not generate SQL query",
                    "raw_response": ai_result.get("raw_response", "")[:500]
                })
                continue

            # Validate SQL
            notify(attempt_num, "executing",
                   f"กำลังตรวจสอบและ execute SQL...", sql=sql_query)

            is_valid, validation_error = self.validate_sql(sql_query)

            if not is_valid:
                # logger.warning(f"SQL validation failed on attempt {attempt_num}: {validation_error}")
                notify(attempt_num, "error",
                       f"SQL ไม่ถูกต้อง: {validation_error}",
                       sql=sql_query, error=validation_error)

                retry_history.append({
                    "attempt": attempt_num,
                    "error_type": "validation_error",
                    "sql": sql_query,
                    "error": validation_error
                })
                continue

            # Execute SQL
            try:
                data = self.execute_sql(sql_query)
                if data is None:
                    data = []

                # Check for zero results - might need retry with better conditions
                if len(data) == 0 and attempt < max_retries:
                    # Analyze why we got 0 results
                    zero_hint = self._check_zero_results_reason(sql_query, context_name=context_name)

                    if zero_hint:
                        # logger.info(f"Query returned 0 rows on attempt {attempt_num}, will retry with hints")
                        notify(attempt_num, "retrying",
                               f"ได้ 0 แถว - กำลังตรวจสอบเงื่อนไขและลองใหม่...",
                               sql=sql_query, error="Zero results - conditions may not match data")

                        retry_history.append({
                            "attempt": attempt_num,
                            "error_type": "zero_results",
                            "sql": sql_query,
                            "error": "Query returned 0 rows",
                            "hint": zero_hint
                        })
                        continue  # Try again with hints

                # Success! (either has data, or 0 rows but no hints to improve)
                notify(attempt_num, "success",
                       f"สำเร็จ! ได้ข้อมูล {len(data)} แถว", sql=sql_query)

                # Generate explanation
                explanation = ai_result.get("explanation", "")
                if explain and data:
                    try:
                        explanation = self.provider.explain_result(
                            question, sql_query, data, system_prompt
                        )
                    except:
                        pass
                elif len(data) == 0:
                    # No data - provide helpful message
                    explanation = "ไม่พบข้อมูลที่ตรงกับเงื่อนไขที่ระบุ อาจเป็นเพราะ:\n" \
                                  "- ชื่อหน่วยงาน/ผลิตภัณฑ์ไม่ตรงกับที่มีในระบบ\n" \
                                  "- ช่วงเวลาที่ระบุไม่มีข้อมูล\n" \
                                  "กรุณาตรวจสอบเงื่อนไขหรือลองถามใหม่ด้วยคำอื่น"

                return QueryResult(
                    question=question,
                    sql_query=sql_query,
                    data=data,
                    explanation=explanation,
                    tokens_used=total_tokens,
                    provider=self.provider_name,
                    retry_count=attempt,
                    retry_history=retry_history if retry_history else None
                )

            except Exception as e:
                error_msg = str(e)
                # logger.warning(f"SQL execution error on attempt {attempt_num}: {error_msg}")

                notify(attempt_num, "retrying" if attempt < max_retries else "failed",
                       f"SQL Error: {error_msg}", sql=sql_query, error=error_msg)

                retry_history.append({
                    "attempt": attempt_num,
                    "error_type": "execution_error",
                    "sql": sql_query,
                    "error": error_msg
                })

        # All retries exhausted
        notify(max_retries + 1, "failed",
               f"ไม่สามารถสร้าง SQL ที่ถูกต้องได้หลังจากลอง {max_retries + 1} ครั้ง")

        last_error = retry_history[-1] if retry_history else {}

        return QueryResult(
            question=question,
            sql_query=last_error.get("sql", ""),
            data=[],
            explanation="",
            tokens_used=total_tokens,
            provider=self.provider_name,
            error=f"ไม่สามารถสร้าง SQL ที่ถูกต้องได้หลังจากลอง {max_retries + 1} ครั้ง: {last_error.get('error', 'Unknown error')}",
            retry_count=max_retries,
            retry_history=retry_history
        )

    def _build_retry_prompt(self, original_question: str, last_error: Dict) -> str:
        """
        Build a prompt for retry attempt, including error context.
        """
        error_type = last_error.get("error_type", "unknown")
        error_msg = last_error.get("error", "Unknown error")
        failed_sql = last_error.get("sql", "")

        if error_type == "no_sql":
            return f"""คำถามเดิม: {original_question}

ความพยายามก่อนหน้านี้ไม่ได้สร้าง SQL query ออกมา
กรุณาสร้าง SQL query ให้ถูกต้อง โดยใช้ columns ที่มีอยู่ใน schema เท่านั้น"""

        elif error_type == "validation_error":
            return f"""คำถามเดิม: {original_question}

SQL ที่สร้างไม่ถูกต้อง:
```sql
{failed_sql}
```

ข้อผิดพลาด: {error_msg}

กรุณาแก้ไข SQL ให้ถูกต้อง"""

        elif error_type == "execution_error":
            # Extract useful info from error
            hint = ""
            if "no such column" in error_msg.lower():
                # Extract column name
                import re
                col_match = re.search(r'no such column:\s*(\w+)', error_msg, re.IGNORECASE)
                if col_match:
                    bad_column = col_match.group(1)
                    hint = f"\n\nหมายเหตุ: Column '{bad_column}' ไม่มีอยู่ในตาราง กรุณาตรวจสอบ schema และใช้ column ที่มีอยู่จริง"

            elif "no such table" in error_msg.lower():
                hint = "\n\nหมายเหตุ: ตารางที่ระบุไม่มีอยู่ กรุณาใช้ตาราง revenue_search"

            elif "syntax error" in error_msg.lower():
                hint = "\n\nหมายเหตุ: มี syntax error ใน SQL กรุณาตรวจสอบ syntax ให้ถูกต้อง"

            return f"""คำถามเดิม: {original_question}

SQL ที่ลองแล้วมีปัญหา:
```sql
{failed_sql}
```

Error ที่เกิดขึ้น: {error_msg}
{hint}

กรุณาแก้ไข SQL โดย:
1. ใช้เฉพาะ columns ที่มีอยู่ใน schema จริงๆ
2. ตรวจสอบชื่อ column ให้ถูกต้อง (ใช้ double quotes สำหรับชื่อไทย)
3. ตรวจสอบ syntax ให้ถูกต้อง

ถ้าไม่มี column ที่ตรงกับคำถาม ให้ใช้ column ที่ใกล้เคียงที่สุดหรืออธิบายว่าข้อมูลนี้ไม่มีในระบบ"""

        elif error_type == "zero_results":
            # Get hints about actual values in database
            hint = last_error.get("hint", "")

            return f"""คำถามเดิม: {original_question}

SQL ที่สร้างทำงานได้แต่ไม่พบข้อมูล (0 rows):
```sql
{failed_sql}
```

สาเหตุที่เป็นไปได้:
{hint}

กรุณาแก้ไข SQL โดย:
1. ตรวจสอบค่าใน WHERE clause ให้ตรงกับค่าจริงในระบบ (ดูค่าที่แนะนำด้านบน)
2. ลองใช้ LIKE '%...%' แทน = สำหรับการค้นหาที่ยืดหยุ่นกว่า
3. ตรวจสอบการสะกดชื่อหน่วยงาน/ผลิตภัณฑ์ให้ถูกต้อง
4. ถ้าผู้ใช้ถามเรื่อง "จังหวัด" แต่ไม่มี column จังหวัด ให้ใช้ COST_CENTER หรือ organization_group_abbr แทน และอธิบายให้ผู้ใช้ทราบ

สำคัญ: ใช้ค่าที่มีอยู่จริงในระบบตามที่แนะนำด้านบน"""

        else:
            return f"""คำถามเดิม: {original_question}

เกิดข้อผิดพลาด: {error_msg}

กรุณาสร้าง SQL query ใหม่ที่ถูกต้อง"""

    def chat(
        self,
        question: str,
        history: Optional[List[Dict]] = None,
        context_name: str = "revenue"
    ) -> Dict[str, Any]:
        """
        Chat interface with conversation history
        
        Args:
            question: User's question
            history: List of previous messages [{role: "user/assistant", content: "..."}]
            context_name: Data scope
        
        Returns:
            Dict with response and updated history
        """
        
        result = self.query(question, history=history or [], context_name=context_name)
        
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

    def suggest_mappings(self, columns: List[Dict[str, Any]], sample_values: Dict[str, List[Any]]) -> List[Dict[str, str]]:
        """
        Suggest standard column mappings using AI
        
        Args:
            columns: List of column info [{'name': '...', 'type': '...'}]
            sample_values: Dict of {col_name: [samples...]}
            
        Returns:
            List of directives: [{'col': 'original', 'alias': 'suggested', 'reason': '...'}]
        """
        import json
        
        # Build prompt
        col_list_str = "\n".join([f"- {c['name']} ({c['type']})" for c in columns])
        
        samples_str = ""
        samples_str = ""
        for col, vals in sample_values.items():
            if isinstance(vals, list):
                val_str = ", ".join(map(str, vals[:5]))
                samples_str += f"- {col}: [{val_str}]\n"
            elif col == 'DATA_RANGE' and isinstance(vals, dict):
                 samples_str += f"- Data Range: {vals.get('min_year')}-{vals.get('max_year')}\n"
            
        prompt = f"""You are a Database Schema Expert.
I have a raw table with the following columns:
{col_list_str}

Sample Data:
{samples_str}

Please suggest standardized English aliases for these columns to make them suitable for a clean SQL View.
Target Rules:
1. snake_case only (e.g. `customer_id`, `total_revenue`, `year`, `month`).
2. Use standard business terms.
3. If a column is already good, keep it similar but ensure lowercase.
4. Rename Thai columns to understandable English names.

Return ONLY a JSON array of objects with this format:
[
  {{ "col": "original_name", "alias": "suggested_name", "reason": "Explanation" }},
  ...
]
Do not include any markdown formatting or explanation outside the JSON.
"""
        try:
            # Generate content
            response_text = self.provider.generate_content(prompt)
            
            # Clean response (remove markdown code blocks if any)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
                
            suggestions = json.loads(response_text)
            return suggestions
            
        except Exception as e:
            logger.error(f"Failed to suggest mappings: {e}")
            # Fallback: simple lowercase
            return [
                {"col": c['name'], "alias": c['name'].lower(), "reason": "Fallback: Lowercase"}
                for c in columns
            ]


# =========================================================
# Factory Functions
# =========================================================

def create_claude_service(api_key: str, db_path: str = "revenue.db", model: Optional[str] = None, prompt_manager: Optional[PromptManager] = None) -> AIService:
    """Create AI service with Claude provider"""
    return AIService(provider="claude", api_key=api_key, db_path=db_path, model=model, prompt_manager=prompt_manager)


def create_gemini_service(api_key: str, db_path: str = "revenue.db", model: Optional[str] = None, prompt_manager: Optional[PromptManager] = None) -> AIService:
    """Create AI service with Gemini provider"""
    return AIService(provider="gemini", api_key=api_key, db_path=db_path, model=model, prompt_manager=prompt_manager)
def create_matcha_service(api_key: str, api_url: str, db_path: str = "revenue.db", model: Optional[str] = None, prompt_manager: Optional[PromptManager] = None) -> AIService:
    """Create AI service with Matcha provider"""
    return AIService(provider="matcha", api_key=api_key, db_path=db_path, model=model, prompt_manager=prompt_manager, api_url=api_url)

# =========================================================
# Example Usage
# =========================================================

if __name__ == "__main__":
    import os
    
    # Example with Claude
    claude_key = os.getenv("ANTHROPIC_API_KEY")
    if claude_key:
        service = create_claude_service(claude_key)
        # result = service.query("รายได้รวมเดือนมกราคม 2568", context_name="revenue") 
        # print(f"SQL: {result.sql_query}")
        # print(f"Data: {result.data[:5]}")
        # print(f"Explanation: {result.explanation}")
