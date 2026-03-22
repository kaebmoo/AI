
import sqlite3
import json
from typing import Dict, List, Optional, Tuple
import re

class ContextRouter:
    """Service to determine the appropriate data context for a question"""
    
    def __init__(self, db_path: str = None):
        from app.config import settings
        if db_path:
            self.db_path = db_path
        elif settings.CONFIG_DB_URL:
            self.db_path = settings.CONFIG_DB_URL.replace("sqlite:///", "").replace("sqlite://", "")
        else:
            self.db_path = settings.DATABASE_URL.replace("sqlite:///", "").replace("sqlite://", "")
        self._cache = None
        self._last_refresh = 0
        
    def _get_contexts(self) -> List[Dict]:
        """Fetch contexts and keywords from DB"""
        if self._cache:
            return self._cache
            
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            cursor.execute("SELECT name, keywords, priority FROM schema_contexts WHERE is_active = 1")
            rows = cursor.fetchall()
            
            contexts = []
            for row in rows:
                keywords = []
                if row['keywords']:
                    try:
                        keywords = json.loads(row['keywords'])
                    except:
                        pass
                        
                contexts.append({
                    'name': row['name'],
                    'keywords': keywords,
                    'priority': row['priority'] or 0
                })
                
            self._cache = contexts
            return contexts
            
        except Exception as e:
            print(f"Error loading contexts: {e}")
            return []
        finally:
            if 'conn' in locals():
                conn.close()
                
    def route(self, question: str) -> str:
        """
        Determine context from question.
        Returns context_name (e.g. 'revenue', 'expense')
        Defaults to 'revenue' if no clear match.
        """
        contexts = self._get_contexts()
        if not contexts:
            return "revenue"
            
        question_lower = question.lower()
        scores = {}
        
        for ctx in contexts:
            name = ctx['name']
            keywords = ctx['keywords']
            score = 0
            
            for kw in keywords:
                if kw.lower() in question_lower:
                    score += 1
            
            if score > 0:
                scores[name] = {
                    'score': score,
                    'priority': ctx['priority']
                }
        
        if not scores:
            return "revenue"
            
        # Sort by Score (Desc) then Priority (Desc)
        sorted_contexts = sorted(
            scores.items(), 
            key=lambda x: (x[1]['score'], x[1]['priority']), 
            reverse=True
        )
        
        best_match = sorted_contexts[0][0]
        return best_match

    def refresh(self):
        self._cache = None

if __name__ == "__main__":
    router = ContextRouter()
    print(f"Revenue Question -> {router.route('ยอดขายเดือนนี้ เท่าไหร่')}")
    print(f"Expense Question -> {router.route('มีค่าใช้จ่ายอะไรบ้าง')}")
    print(f"Mixed Question -> {router.route('ยอดขาย และ ต้นทุน')}") # Priority?
