"""Review round 3: numeric config endpoint must enforce the same range as the UI (5-300)."""

import pytest
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from app.api.v1.admin.config import set_numeric_config, _NUMERIC_CONFIG_RANGES


def _call(key, value):
    user = MagicMock()
    user.email = "admin@example.com"
    with patch("app.api.v1.admin.config.AdminConfigService") as MockSvc:
        MockSvc.return_value.set_config.return_value = True
        return set_numeric_config(key=key, value=value, current_user=user, _db=MagicMock())


class TestNumericConfigRange:
    def test_budget_range_matches_ui(self):
        assert _NUMERIC_CONFIG_RANGES["query_latency_budget_s"] == (5.0, 300.0)

    def test_value_in_range_accepted(self):
        result = _call("query_latency_budget_s", 90)
        assert result["status"] == "success"
        assert result["value"] == 90

    def test_below_min_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _call("query_latency_budget_s", 3)
        assert exc.value.status_code == 400
        assert "between 5.0 and 300.0" in exc.value.detail

    def test_above_max_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _call("query_latency_budget_s", 500)
        assert exc.value.status_code == 400

    def test_boundaries_inclusive(self):
        assert _call("query_latency_budget_s", 5)["value"] == 5
        assert _call("query_latency_budget_s", 300)["value"] == 300

    def test_unknown_key_rejected(self):
        with pytest.raises(HTTPException) as exc:
            _call("arbitrary_key", 10)
        assert exc.value.status_code == 400
        assert "not settable" in exc.value.detail
