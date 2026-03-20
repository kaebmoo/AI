"""
Auto-Analyzer Service
======================
Analyzes failed/thumbs-down queries and suggests config fixes.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class SuggestedFix:
    fix_type: str  # add_mapping, add_rule, add_example, update_instruction
    params: Dict[str, Any]
    confidence: float  # 0.0 - 1.0
    reason: str
    source_query_ids: List[int] = field(default_factory=list)

    @property
    def auto_applicable(self) -> bool:
        return self.confidence >= 0.8


@dataclass
class FailureGroup:
    pattern: str
    queries: List[Dict]
    count: int


@dataclass
class AnalysisResult:
    total_failures: int
    groups: List[FailureGroup]
    suggested_fixes: List[SuggestedFix]


class AutoAnalyzer:
    """Analyzes query failures and suggests configuration fixes."""

    def __init__(self, db: Session):
        self.db = db

    async def analyze_recent_failures(self, period_hours: int = 24) -> AnalysisResult:
        """Analyze failed/thumbs-down queries from the last N hours."""
        from app.models.chat import ChatHistory
        from app.models.feedback_models import UserFeedback, FeedbackRating

        since = datetime.utcnow() - timedelta(hours=period_hours)

        # Fetch failed queries (no SQL generated or thumbs down)
        failed_chats = self.db.query(ChatHistory).outerjoin(
            UserFeedback, ChatHistory.id == UserFeedback.chat_id
        ).filter(
            ChatHistory.created_at >= since,
            (
                (ChatHistory.generated_sql == None) |
                (ChatHistory.generated_sql == "") |
                (UserFeedback.rating == FeedbackRating.THUMBS_DOWN)
            )
        ).order_by(ChatHistory.created_at.desc()).limit(100).all()

        if not failed_chats:
            return AnalysisResult(total_failures=0, groups=[], suggested_fixes=[])

        # Group similar failures
        groups = self._group_similar_failures(failed_chats)

        # Generate suggested fixes for each group
        suggested_fixes = []
        for group in groups:
            fixes = self._suggest_fixes_for_group(group)
            suggested_fixes.extend(fixes)

        return AnalysisResult(
            total_failures=len(failed_chats),
            groups=groups,
            suggested_fixes=suggested_fixes,
        )

    async def analyze_single_query(self, chat_id: int) -> Optional[AnalysisResult]:
        """Analyze a single query and suggest fixes."""
        from app.models.chat import ChatHistory

        chat = self.db.query(ChatHistory).filter(ChatHistory.id == chat_id).first()
        if not chat:
            return None

        group = FailureGroup(
            pattern=chat.question[:80] if chat.question else "",
            queries=[{
                "id": chat.id,
                "question": chat.question,
                "generated_sql": chat.generated_sql,
                "context": chat.context_name,
            }],
            count=1,
        )

        fixes = self._suggest_fixes_for_group(group)

        return AnalysisResult(
            total_failures=1,
            groups=[group],
            suggested_fixes=fixes,
        )

    def _group_similar_failures(self, chats) -> List[FailureGroup]:
        """Group failed queries by similarity (simple keyword overlap)."""
        groups: List[FailureGroup] = []
        used = set()

        for i, chat in enumerate(chats):
            if i in used:
                continue

            q = (chat.question or "").lower()
            group_queries = [{
                "id": chat.id,
                "question": chat.question,
                "generated_sql": chat.generated_sql,
                "context": chat.context_name,
            }]
            used.add(i)

            # Find similar queries
            q_words = set(q.split())
            for j, other in enumerate(chats):
                if j in used or j == i:
                    continue
                other_q = (other.question or "").lower()
                other_words = set(other_q.split())
                overlap = len(q_words & other_words) / max(len(q_words | other_words), 1)
                if overlap > 0.5:
                    group_queries.append({
                        "id": other.id,
                        "question": other.question,
                        "generated_sql": other.generated_sql,
                        "context": other.context_name,
                    })
                    used.add(j)

            groups.append(FailureGroup(
                pattern=q[:80],
                queries=group_queries,
                count=len(group_queries),
            ))

        return groups

    def _suggest_fixes_for_group(self, group: FailureGroup) -> List[SuggestedFix]:
        """Suggest fixes based on failure patterns (heuristic, no LLM)."""
        fixes = []
        query_ids = [q["id"] for q in group.queries]

        # Heuristic: if SQL is None, likely a mapping issue
        no_sql = [q for q in group.queries if not q.get("generated_sql")]
        if no_sql:
            # Extract potential keywords from questions
            keywords = self._extract_keywords(group.pattern)
            for kw in keywords[:3]:
                if self._keyword_not_mapped(kw):
                    fixes.append(SuggestedFix(
                        fix_type="add_mapping",
                        params={"keyword": kw, "target_column": "UNKNOWN", "target_value": kw},
                        confidence=0.5,  # Low confidence — needs manual review
                        reason=f"Keyword '{kw}' appears in {group.count} failed queries but has no mapping",
                        source_query_ids=query_ids,
                    ))

        # Heuristic: if SQL exists but wrong, might need an example
        has_sql = [q for q in group.queries if q.get("generated_sql")]
        if has_sql and group.count >= 3:
            fixes.append(SuggestedFix(
                fix_type="add_example",
                params={"question": group.pattern, "sql": "NEEDS_MANUAL_SQL"},
                confidence=0.4,
                reason=f"{group.count} queries with similar pattern failed — may need a golden example",
                source_query_ids=query_ids,
            ))

        return fixes

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract potential Thai keywords from a question."""
        # Simple: split by spaces, filter short words and common words
        common = {"ของ", "ที่", "ใน", "และ", "หรือ", "จาก", "เป็น", "ไป", "มา", "ได้", "ให้", "กับ", "แต่", "จะ", "ก็", "ว่า", "อะไร", "ทั้ง", "แล้ว", "ดู", "รวม", "ปี", "เดือน"}
        words = text.split()
        return [w for w in words if len(w) > 2 and w not in common]

    def _keyword_not_mapped(self, keyword: str) -> bool:
        """Check if a keyword has no existing mapping."""
        from app.models.schema_models import SchemaSemanticMapping
        exists = self.db.query(SchemaSemanticMapping).filter(
            SchemaSemanticMapping.keyword.ilike(f"%{keyword}%"),
            SchemaSemanticMapping.is_active == True,
        ).first()
        return exists is None

    def save_suggested_fixes(self, fixes: List[SuggestedFix]):
        """Save suggested fixes to DB for admin review."""
        from sqlalchemy import text

        for fix in fixes:
            self.db.execute(text("""
                INSERT INTO suggested_fixes (fix_type, params, confidence, reason, source_query_ids, status)
                VALUES (:fix_type, :params, :confidence, :reason, :source_ids, 'pending')
            """), {
                "fix_type": fix.fix_type,
                "params": json.dumps(fix.params, ensure_ascii=False),
                "confidence": fix.confidence,
                "reason": fix.reason,
                "source_ids": json.dumps(fix.source_query_ids),
            })
        self.db.commit()
