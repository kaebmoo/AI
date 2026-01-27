from typing import List, Dict, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.feedback_models import PromptVersion, GoldenExample
from app.config import settings

class PromptManager:
    """Manage prompt versions and few-shot examples"""
    
    def __init__(self, db: Session):
        self.db = db
        self._cache = {}
    
    def get_active_prompt(self) -> PromptVersion:
        """Get currently active prompt version"""
        if 'active_prompt' in self._cache:
            return self._cache['active_prompt']
        
        prompt = self.db.query(PromptVersion).filter(
            PromptVersion.is_active == True
        ).order_by(PromptVersion.created_at.desc()).first()
        
        if not prompt:
            # Return dummy if none exists, to prevent crashes
            return PromptVersion(
                version=0,
                system_prompt="", # Will fallback to default in AIService
                is_active=True
            )
        
        self._cache['active_prompt'] = prompt
        return prompt
    
    def get_few_shot_examples(self, category: Optional[str] = None, limit: int = 5) -> List[Dict]:
        """Get few-shot examples for prompt"""
        
        query = self.db.query(GoldenExample).filter(
            GoldenExample.is_active == True
        )
        
        if category:
            query = query.filter(GoldenExample.category == category)
        
        examples = query.order_by(
            GoldenExample.usage_count.desc()
        ).limit(limit).all()
        
        return [
            {
                "question": ex.question_pattern,
                "sql": ex.expected_sql
            }
            for ex in examples
        ]
    
    def compose_system_prompt(self, base_prompt: str, schema_text: str) -> str:
        """
        Compose the final system prompt by combining:
        1. Base instructions (from DB or default)
        2. Schema info
        3. Few-shot examples
        """
        active_version = self.get_active_prompt()
        
        # Use DB prompt if available and not empty, otherwise use provided base_prompt
        main_instruction = active_version.system_prompt if active_version.version > 0 else base_prompt
        
        examples = self.get_few_shot_examples(limit=5)
        few_shot_text = ""
        
        if examples:
            few_shot_text = "\n\n## Examples / ตัวอย่างการเขียน SQL\n"
            for i, ex in enumerate(examples, 1):
                few_shot_text += f"\nQ: {ex['question']}\nSQL: {ex['sql']}\n"
        
        full_prompt = f"""{main_instruction}

## Schema Information
{schema_text}

{few_shot_text}

## Version Info
Prompt Version: {active_version.version}
"""
        return full_prompt
