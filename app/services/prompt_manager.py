"""
NT Revenue Assistant - Prompt Manager
======================================
Manages prompt versions and few-shot examples for AI context.

Enhanced Features (v2.0):
- Auto-categorization of golden examples
- Category-aware example selection
- Improved prompt composition
"""

import re
from typing import List, Dict, Optional, Set
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime

from app.models.feedback_models import PromptVersion, GoldenExample
from app.config import settings


# Category keywords for auto-categorization
CATEGORY_KEYWORDS = {
    'aggregation': ['รวม', 'ผลรวม', 'sum', 'total', 'รายได้รวม', 'ยอดรวม'],
    'comparison': ['เปรียบเทียบ', 'compare', 'vs', 'มากกว่า', 'น้อยกว่า', 'สูงสุด', 'ต่ำสุด', 'top', 'bottom'],
    'time_series': ['แนวโน้ม', 'trend', 'เดือน', 'ปี', 'ไตรมาส', 'quarter', 'month', 'year', 'รายเดือน'],
    'organization': ['หน่วยงาน', 'สายงาน', 'ฝ่าย', 'กลุ่ม', 'division', 'department', 'business_unit'],
    'product': ['ผลิตภัณฑ์', 'product', 'บริการ', 'service', 'mobile', 'fixed line', 'internet'],
    'filter': ['เฉพาะ', 'only', 'where', 'กรอง', 'filter', 'เงื่อนไข'],
    'abbreviation': ['นป.', 'บชง.', 'สญ.', 'นต.', 'กส.', 'ปต.'],
}


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
                system_prompt="",  # Will fallback to default in AIService
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
                "sql": ex.expected_sql,
                "category": ex.category
            }
            for ex in examples
        ]

    def get_relevant_examples(self, question: str, limit: int = 5) -> List[Dict]:
        """
        Get relevant examples based on question content.
        Uses category matching and keyword analysis.
        """
        # Detect categories from question
        detected_categories = self.detect_categories(question)

        if detected_categories:
            # Get examples from detected categories
            examples = []
            remaining_limit = limit

            for category in detected_categories:
                if remaining_limit <= 0:
                    break

                cat_examples = self.get_few_shot_examples(
                    category=category,
                    limit=min(2, remaining_limit)  # Max 2 per category
                )
                examples.extend(cat_examples)
                remaining_limit -= len(cat_examples)

            # Fill remaining with top examples
            if remaining_limit > 0:
                top_examples = self.get_few_shot_examples(limit=remaining_limit)
                # Avoid duplicates
                existing_questions = {e['question'] for e in examples}
                for ex in top_examples:
                    if ex['question'] not in existing_questions:
                        examples.append(ex)
                        if len(examples) >= limit:
                            break

            return examples[:limit]

        # No specific category detected, return top examples
        return self.get_few_shot_examples(limit=limit)

    def detect_categories(self, text: str) -> List[str]:
        """
        Detect categories from text using keyword matching.

        Args:
            text: Question or text to analyze

        Returns:
            List of detected category names
        """
        text_lower = text.lower()
        detected = []

        for category, keywords in CATEGORY_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    detected.append(category)
                    break  # One match per category is enough

        return detected

    def auto_categorize(self, question: str, sql: str) -> Optional[str]:
        """
        Auto-categorize a golden example based on question and SQL content.

        Args:
            question: The question pattern
            sql: The expected SQL

        Returns:
            Detected category name or None
        """
        combined_text = f"{question} {sql}"
        categories = self.detect_categories(combined_text)

        if categories:
            return categories[0]  # Return primary category

        # Additional SQL-based categorization
        sql_upper = sql.upper()

        if 'SUM(' in sql_upper or 'COUNT(' in sql_upper or 'AVG(' in sql_upper:
            return 'aggregation'
        if 'GROUP BY' in sql_upper and ('YEAR' in sql_upper or 'MONTH' in sql_upper):
            return 'time_series'
        if 'ORDER BY' in sql_upper and ('DESC' in sql_upper or 'ASC' in sql_upper):
            return 'comparison'
        if 'BUSINESS_UNIT' in sql_upper or 'DIVISION' in sql_upper or 'DEPARTMENT' in sql_upper:
            return 'organization'
        if 'PRODUCT' in sql_upper or 'SERVICE_GROUP' in sql_upper or 'BUSINESS_GROUP' in sql_upper:
            return 'product'

        return None

    def get_all_categories(self) -> List[str]:
        """Get all distinct categories from golden examples"""
        categories = self.db.query(GoldenExample.category).distinct().filter(
            GoldenExample.category.isnot(None),
            GoldenExample.is_active == True
        ).all()
        return [c[0] for c in categories if c[0]]

    def get_category_counts(self) -> Dict[str, int]:
        """Get count of examples per category"""
        results = self.db.query(
            GoldenExample.category,
            func.count(GoldenExample.id)
        ).filter(
            GoldenExample.is_active == True
        ).group_by(GoldenExample.category).all()

        return {
            cat or 'uncategorized': count
            for cat, count in results
        }

    def increment_usage_count(self, example_id: int):
        """Increment usage count for an example"""
        example = self.db.query(GoldenExample).filter(
            GoldenExample.id == example_id
        ).first()
        if example:
            example.usage_count += 1
            self.db.commit()
    
    def compose_system_prompt(
        self,
        base_prompt: str,
        schema_text: str,
        question: Optional[str] = None
    ) -> str:
        """
        Compose the final system prompt by combining:
        1. Base instructions (from DB or default)
        2. Schema info
        3. Few-shot examples (context-aware if question provided)

        Args:
            base_prompt: Default instruction prompt
            schema_text: Schema context including metadata, rules, mappings
            question: Optional current question for context-aware example selection
        """
        active_version = self.get_active_prompt()

        # Use DB prompt if available and not empty, otherwise use provided base_prompt
        main_instruction = active_version.system_prompt if active_version.version > 0 else base_prompt

        # Get examples - use relevant examples if question provided
        if question:
            examples = self.get_relevant_examples(question, limit=5)
        else:
            examples = self.get_few_shot_examples(limit=5)

        few_shot_text = ""

        if examples:
            few_shot_text = "\n\n## Examples / ตัวอย่างการเขียน SQL\n"
            for i, ex in enumerate(examples, 1):
                category_tag = f" [{ex.get('category', '')}]" if ex.get('category') else ""
                few_shot_text += f"\n**Example {i}**{category_tag}\nQ: {ex['question']}\n```sql\n{ex['sql']}\n```\n"

        full_prompt = f"""{main_instruction}

## Schema Information
{schema_text}
{few_shot_text}

## Version Info
Prompt Version: {active_version.version}
"""
        return full_prompt
    def activate_version(self, version_id: int) -> Optional[PromptVersion]:
        """Activate a specific prompt version"""
        # Deactivate all
        self.db.query(PromptVersion).update({PromptVersion.is_active: False})
        
        # Activate target
        target = self.db.query(PromptVersion).filter(PromptVersion.id == version_id).first()
        if target:
            target.is_active = True
            self.db.commit()
            self.db.refresh(target)
            # Clear cache
            if 'active_prompt' in self._cache:
                del self._cache['active_prompt']
            return target
        
        self.db.rollback()
        return None

    def create_new_version(self, system_prompt: str, notes: str = None, user_id: int = None) -> PromptVersion:
        """Create a new prompt version"""
        # Get latest version number
        latest = self.db.query(PromptVersion).order_by(PromptVersion.version.desc()).first()
        new_version_num = (latest.version + 1) if latest else 1
        
        new_ver = PromptVersion(
            version=new_version_num,
            system_prompt=system_prompt,
            notes=notes,
            created_by=user_id,
            is_active=False # Default inactive
        )
        self.db.add(new_ver)
        self.db.commit()
        return new_ver
