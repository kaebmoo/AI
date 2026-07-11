"""F4.4: API key per-minute rate limit (Redis fixed-window, fail-open)."""

from unittest.mock import MagicMock, patch

from app.services import api_key_service as aks_module
from app.services.api_key_service import APIKeyService


def _key(per_minute=30):
    api_key = MagicMock()
    api_key.id = 1
    api_key.rate_limit_per_minute = per_minute
    api_key.rate_limit_per_day = 1000
    return api_key


def _service():
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None  # no daily usage
    return APIKeyService(db)


class TestPerMinuteLimit:
    def test_over_limit_blocked(self):
        svc = _service()
        redis_client = MagicMock()
        redis_client.incr.return_value = 31  # 31st request in the window
        cache = MagicMock()
        cache.redis = redis_client
        with patch("app.services.cache_service.CacheService", return_value=cache):
            assert svc._check_rate_limits(_key(per_minute=30)) is False

    def test_under_limit_allowed(self):
        svc = _service()
        redis_client = MagicMock()
        redis_client.incr.return_value = 5
        cache = MagicMock()
        cache.redis = redis_client
        with patch("app.services.cache_service.CacheService", return_value=cache):
            assert svc._check_rate_limits(_key(per_minute=30)) is True

    def test_first_request_sets_expiry(self):
        svc = _service()
        redis_client = MagicMock()
        redis_client.incr.return_value = 1
        cache = MagicMock()
        cache.redis = redis_client
        with patch("app.services.cache_service.CacheService", return_value=cache):
            assert svc._check_rate_limits(_key()) is True
        redis_client.expire.assert_called_once()

    def test_redis_down_fails_open_with_warning(self, caplog):
        svc = _service()
        aks_module._minute_limit_warned = False
        with patch("app.services.cache_service.CacheService", side_effect=ConnectionError("no redis")):
            with caplog.at_level("WARNING"):
                assert svc._check_rate_limits(_key()) is True
        assert any("Redis unavailable" in r.message for r in caplog.records)
        # Second failure — no duplicate warning
        caplog.clear()
        with patch("app.services.cache_service.CacheService", side_effect=ConnectionError("no redis")):
            with caplog.at_level("WARNING"):
                assert svc._check_rate_limits(_key()) is True
        assert not any("Redis unavailable" in r.message for r in caplog.records)

    def test_no_minute_limit_configured_skips_redis(self):
        svc = _service()
        with patch("app.services.cache_service.CacheService") as MockCache:
            assert svc._check_rate_limits(_key(per_minute=0)) is True
        MockCache.assert_not_called()
