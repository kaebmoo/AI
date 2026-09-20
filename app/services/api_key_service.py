"""
API Key Service
================
Create, validate, revoke, and track usage of API keys.
"""

import hashlib
import logging
import secrets
from datetime import datetime, date
from typing import Dict, List, Optional, Tuple

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.api_key import APIKey, APIKeyUsage
from app.core.time_utils import utcnow

logger = logging.getLogger(__name__)

# One-time warning flag when Redis is down and per-minute limit is disabled
_minute_limit_warned = False

KEY_PREFIX = "ntai_"
KEY_LENGTH = 32  # 32 random bytes → 64 hex chars


class APIKeyService:
    """Manage API keys for external integrations."""

    def __init__(self, db: Session):
        self.db = db
        from app.services.workspaces import ensure_api_key_columns
        ensure_api_key_columns(db.get_bind())  # Phase 4a columns on a pre-Phase-4 app DB

    def create_key(
        self,
        user_id: int,
        name: str,
        scopes: str = "query",
        rate_limit_per_minute: int = 30,
        rate_limit_per_day: int = 1000,
        expires_at: Optional[datetime] = None,
        workspace_id: Optional[int] = None,
        allowed_contexts: Optional[str] = None,
    ) -> Tuple[str, APIKey]:
        """Create a new API key.

        Returns:
            Tuple of (raw_key, APIKey model). Raw key is shown ONCE.
        """
        raw_secret = secrets.token_hex(KEY_LENGTH)
        raw_key = f"{KEY_PREFIX}{raw_secret}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:12]

        api_key = APIKey(
            key_hash=key_hash,
            key_prefix=key_prefix,
            name=name,
            user_id=user_id,
            scopes=scopes,
            workspace_id=workspace_id,          # Phase 4a — see app/services/workspaces.py
            allowed_contexts=allowed_contexts,  # JSON list; validated by resolve_key_binding
            rate_limit_per_minute=rate_limit_per_minute,
            rate_limit_per_day=rate_limit_per_day,
            is_active=True,
            expires_at=expires_at,
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)

        logger.info(f"API key created: {key_prefix}... for user {user_id}, name='{name}'")
        return raw_key, api_key

    def authenticate(self, raw_key: str) -> Optional[APIKey]:
        """The active, unexpired key — no rate-limit counting, no last_used_at (Plan 7 Phase 6: the MCP
        gate checks every HTTP request with this; a tool call is then counted once by validate_key)."""
        if not raw_key or not raw_key.startswith(KEY_PREFIX):
            return None

        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        api_key = self.db.query(APIKey).filter(
            APIKey.key_hash == key_hash,
            APIKey.is_active == True,
        ).first()

        if not api_key:
            return None

        # Check expiry
        if api_key.expires_at and api_key.expires_at < utcnow():
            logger.warning(f"API key {api_key.key_prefix} expired")
            return None

        return api_key

    def check_key(self, raw_key: str) -> Tuple[Optional[APIKey], Optional[str]]:
        """(key, None) when the key may be used now, else (None, reason): 'unauthorized' when the key
        itself cannot be used (unknown, revoked, expired) and 'rate_limited' when it exists but is over
        a limit. Two different answers to the caller — 401 vs 429 — so they are told apart here."""
        api_key = self.authenticate(raw_key)
        if not api_key:
            return None, "unauthorized"

        # Check rate limits
        if not self._check_rate_limits(api_key):
            logger.warning(f"API key {api_key.key_prefix} rate limited")
            return None, "rate_limited"

        # Update last_used_at
        api_key.last_used_at = utcnow()
        self.db.commit()

        return api_key, None

    def validate_key(self, raw_key: str) -> Optional[APIKey]:
        """Validate an API key and return the APIKey if valid.

        Checks: exists, is_active, not expired, rate limits.
        Returns None if invalid — use check_key() when the reason matters.
        """
        return self.check_key(raw_key)[0]

    def revoke_key(self, key_id: int, user_id: Optional[int] = None) -> bool:
        """Revoke an API key (soft delete)."""
        query = self.db.query(APIKey).filter(APIKey.id == key_id)
        if user_id:
            query = query.filter(APIKey.user_id == user_id)

        api_key = query.first()
        if not api_key:
            return False

        api_key.is_active = False
        api_key.updated_at = utcnow()
        self.db.commit()

        logger.info(f"API key revoked: {api_key.key_prefix}")
        return True

    def track_usage(self, api_key_id: int, tokens: int = 0):
        """Track API key usage for the current day — one atomic upsert: parallel requests (MCP clients
        call tools in bursts) neither lose increments nor collide on the first row of the day."""
        self.db.execute(text(
            "INSERT INTO api_key_usage (api_key_id, date, request_count, token_count, created_at) "
            "VALUES (:key, :date, 1, :tokens, :now) ON CONFLICT (api_key_id, date) DO UPDATE SET "
            "request_count = api_key_usage.request_count + 1, token_count = api_key_usage.token_count + :tokens"),
            {"key": api_key_id, "date": date.today().isoformat(), "tokens": tokens, "now": utcnow()})
        self.db.commit()

    def usage_today(self, api_key_id: int) -> int:
        return self.db.execute(text("SELECT request_count FROM api_key_usage WHERE api_key_id = :key AND date = :date"),
                               {"key": api_key_id, "date": date.today().isoformat()}).scalar() or 0

    def get_usage_stats(self, key_id: int, days: int = 30) -> Dict:
        """Get usage statistics for an API key."""
        usage_records = self.db.query(APIKeyUsage).filter(
            APIKeyUsage.api_key_id == key_id,
        ).order_by(APIKeyUsage.date.desc()).limit(days).all()

        total_requests = sum(u.request_count for u in usage_records)
        total_tokens = sum(u.token_count for u in usage_records)

        return {
            "total_requests": total_requests,
            "total_tokens": total_tokens,
            "daily": [
                {"date": u.date, "requests": u.request_count, "tokens": u.token_count}
                for u in usage_records
            ]
        }

    def list_keys(self, user_id: Optional[int] = None) -> List[APIKey]:
        """List all API keys, optionally filtered by user."""
        query = self.db.query(APIKey)
        if user_id:
            query = query.filter(APIKey.user_id == user_id)
        return query.order_by(APIKey.created_at.desc()).all()

    def _check_rate_limits(self, api_key: APIKey) -> bool:
        """Check if API key is within rate limits (daily via DB, per-minute via Redis)."""
        today = date.today().isoformat()

        # Daily limit
        usage = self.db.query(APIKeyUsage).filter(
            APIKeyUsage.api_key_id == api_key.id,
            APIKeyUsage.date == today,
        ).first()

        if usage and usage.request_count >= api_key.rate_limit_per_day:
            return False

        return self._check_minute_limit(api_key)

    def _check_minute_limit(self, api_key: APIKey) -> bool:
        """Redis fixed-window per-minute limit.

        Fixed windows allow up to 2x burst across a minute boundary — acceptable
        for this internal use case. Fail-open when Redis is unavailable
        (availability first for an internal system) with a one-time warning.
        """
        if not api_key.rate_limit_per_minute:
            return True
        try:
            import time as _time
            from app.services.cache_service import CacheService
            redis_client = CacheService().redis
            key = f"ratelimit:apikey:{api_key.id}:{int(_time.time() // 60)}"
            count = redis_client.incr(key)
            if count == 1:
                redis_client.expire(key, 120)
            if count > api_key.rate_limit_per_minute:
                return False
        except Exception as e:
            global _minute_limit_warned
            if not _minute_limit_warned:
                logger.warning(f"Per-minute rate limit disabled — Redis unavailable: {e}")
                _minute_limit_warned = True
        return True

    @staticmethod
    def has_scope(api_key: APIKey, required_scope: str) -> bool:
        """Check if API key has the required scope. 'full' implies all scopes."""
        scopes = [s.strip() for s in (api_key.scopes or "").split(",")]
        return required_scope in scopes or "full" in scopes
