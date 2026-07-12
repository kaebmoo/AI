"""
Wave 4: chart_max_series 3-tier config (admin_config DB -> .env -> hardcoded default).
See plan/PLAN_UI_CHART_IMPROVEMENT.md Wave 4.
"""

from unittest.mock import MagicMock

from app.config import settings


class TestGetChartMaxSeries:
    def _service_with(self, values: dict):
        from app.services.admin_config_service import AdminConfigService
        svc = AdminConfigService(db=MagicMock())
        svc.get_config = lambda key, default=None: values.get(key, default)
        return svc

    def test_db_tier_wins_when_present(self):
        """get_config already resolves DB -> .env -> passed-in default; this
        method's own default arg is str(settings.CHART_MAX_SERIES), so a value
        present in the values dict simulates a DB hit."""
        svc = self._service_with({"chart_max_series": "8"})
        assert svc.get_chart_max_series() == 8

    def test_falls_back_to_hardcoded_default_when_unset(self):
        svc = self._service_with({})
        assert svc.get_chart_max_series() == settings.CHART_MAX_SERIES

    def test_invalid_value_falls_back_to_default(self):
        svc = self._service_with({"chart_max_series": "not-a-number"})
        assert svc.get_chart_max_series() == settings.CHART_MAX_SERIES

    def test_too_small_value_falls_back_to_default(self):
        """<2 can't support Top-(N-1) + one 'อื่นๆ' bucket."""
        svc = self._service_with({"chart_max_series": "1"})
        assert svc.get_chart_max_series() == settings.CHART_MAX_SERIES

    def test_zero_falls_back_to_default(self):
        svc = self._service_with({"chart_max_series": "0"})
        assert svc.get_chart_max_series() == settings.CHART_MAX_SERIES

    def test_valid_small_value_accepted(self):
        svc = self._service_with({"chart_max_series": "3"})
        assert svc.get_chart_max_series() == 3
