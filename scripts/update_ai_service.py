
import os

FILE_PATH = 'app/services/ai_service.py'

NEW_CONTENT = r'''class AIService:
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
        self.schema_service = SchemaService(db_path, db_engine=db_engine)
        
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
'''

def process_file():
    with open(FILE_PATH, 'r') as f:
        content = f.read()

    # Find the start of class AIService
    marker = 'class AIService:'
    idx = content.find(marker)
    
    if idx == -1:
        print("Error: Could not find class AIService in file")
        return

    # Keep content before marker
    new_file_content = content[:idx] + NEW_CONTENT
    
    with open(FILE_PATH, 'w') as f:
        f.write(new_file_content)
    
    print(f"Successfully updated {FILE_PATH}")

if __name__ == "__main__":
    process_file()
