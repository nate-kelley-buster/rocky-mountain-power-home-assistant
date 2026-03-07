"""Tests for XHR response parsing logic.

These tests mock the browser/page interactions and inject fake XHR data
to validate that the parsing and data transformation logic is correct.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from custom_components.rocky_mountain_power.client import RockyMountainPower
from custom_components.rocky_mountain_power.models import (
    AccountInfo,
    AggregateType,
    BillingInfo,
    CostRead,
)
from custom_components.rocky_mountain_power.scraper import (
    RockyMountainPowerUtility,
    _parse_dollar,
    _parse_interval_time,
)
from tests.conftest import (
    ACCOUNT_INFO_EMPTY_RESPONSE,
    ACCOUNT_INFO_RESPONSE,
    ACCOUNT_LIST_RESPONSE,
    DAILY_USAGE_RESPONSE,
    EMPTY_DAILY_RESPONSE,
    EMPTY_HOURLY_RESPONSE,
    EMPTY_MONTHLY_RESPONSE,
    FIFTEEN_MIN_USAGE_RESPONSE,
    HOURLY_USAGE_RESPONSE,
    METER_TYPE_RESPONSE,
    MONTHLY_USAGE_NO_ELAPSED_DAYS,
    MONTHLY_USAGE_RESPONSE,
    MULTI_ACCOUNT_LIST_RESPONSE,
    SINGLE_ENTRY_USAGE_RESPONSE,
    USER_ME_RESPONSE,
)


class TestParseDollar:
    """Test the _parse_dollar helper function."""

    def test_simple_amount(self):
        assert _parse_dollar("$143") == 143.0

    def test_with_cents(self):
        assert _parse_dollar("$5.99") == 5.99

    def test_with_commas(self):
        assert _parse_dollar("$1,234.56") == 1234.56

    def test_no_dollar_sign(self):
        assert _parse_dollar("98.50") == 98.50

    def test_empty_string(self):
        assert _parse_dollar("") is None

    def test_none_input(self):
        assert _parse_dollar(None) is None

    def test_whitespace(self):
        assert _parse_dollar("  $100  ") == 100.0

    def test_zero(self):
        assert _parse_dollar("$0") == 0.0

    def test_invalid(self):
        assert _parse_dollar("not a number") is None


class TestParseIntervalTime:
    """Test _parse_interval_time for readDate/readTime parsing, including 24:00."""

    def test_normal_time(self):
        result = _parse_interval_time("2023-11-22", "01:30", "America/Denver")
        assert result.hour == 1
        assert result.minute == 30
        assert result.day == 22

    def test_24_00_is_midnight_next_day(self):
        """24:00 = end of day = 00:00 next day per utility convention."""
        result = _parse_interval_time("2023-11-22", "24:00", "America/Denver")
        assert result.hour == 0
        assert result.minute == 0
        assert result.day == 23
        assert result.month == 11

    def test_24_00_with_whitespace(self):
        result = _parse_interval_time("2023-11-22", "  24:00  ", "America/Denver")
        assert result.day == 23
        assert result.hour == 0

    def test_regular_midnight(self):
        """00:00 on a date is start of that day (not 24:00)."""
        result = _parse_interval_time("2023-11-22", "00:00", "America/Denver")
        assert result.day == 22
        assert result.hour == 0


class TestMonthlyUsageParsing:
    """Test parsing of monthly usage XHR responses."""

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_monthly_usage(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: MONTHLY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_month()

        assert len(result) == 2
        assert result[0]["usage"] == 1124.0
        assert result[0]["amount"] == 143.0
        assert result[1]["usage"] == 756.0
        assert result[1]["amount"] == 98.0

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_monthly_usage_without_elapsed_days(self, mock_wait, mock_select, mock_goto):
        """When elapsedDays is missing, start_time should fall back to day=1."""
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: MONTHLY_USAGE_NO_ELAPSED_DAYS}
        util._page = MagicMock()

        result = util.get_usage_by_month()

        assert len(result) == 1
        assert result[0]["usage"] == 1124.0
        assert result[0]["startTime"].day == 1

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_monthly_usage_empty(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: EMPTY_MONTHLY_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_month()
        assert result == []

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_monthly_end_time_offset(self, mock_wait, mock_select, mock_goto):
        """end_time should be 1 second before the usagePeriodEndDate."""
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: MONTHLY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_month()
        for entry in result:
            assert entry["endTime"].second == 59


class TestDailyUsageParsing:
    """Test parsing of daily usage XHR responses."""

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_daily_usage(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getUsageForDateRange"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: DAILY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_day(months=1)

        assert len(result) == 2
        assert result[0]["usage"] == 37.85
        assert result[0]["amount"] == 5.0
        assert result[1]["usage"] == 42.10
        assert result[1]["amount"] == 7.0

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_daily_usage_empty(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getUsageForDateRange"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: EMPTY_DAILY_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_day(months=1)
        assert result == []

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_daily_start_time_is_one_day_before_end(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getUsageForDateRange"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: DAILY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_day(months=1)
        for entry in result:
            diff = entry["endTime"] + timedelta(seconds=1) - entry["startTime"]
            assert diff.days == 1


class TestIntervalUsageParsing:
    """Test parsing of interval usage XHR responses (hourly and 15-minute)."""

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_hourly_usage(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: HOURLY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)

        assert len(result) == 3
        assert result[0]["usage"] == 1.682
        assert result[1]["usage"] == 1.450
        assert result[2]["usage"] == 0.890
        for entry in result:
            assert entry["amount"] is None

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_hourly_24_00_handling(self, mock_wait, mock_select, mock_goto):
        """readTime '24:00' should be converted to '00:00' (next day midnight)."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: HOURLY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)

        last_entry = result[2]
        assert last_entry["endTime"].hour == 23
        assert last_entry["endTime"].minute == 59
        assert last_entry["endTime"].second == 59

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_hourly_usage_empty(self, mock_wait, mock_select, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: EMPTY_HOURLY_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)
        assert result == []

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_hourly_interval_detected_as_one_hour(self, mock_wait, mock_select, mock_goto):
        """Hourly data should produce 1-hour intervals between start and end."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: HOURLY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)
        for entry in result:
            diff = entry["endTime"] + timedelta(seconds=1) - entry["startTime"]
            assert diff.total_seconds() == 3600

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_parse_fifteen_min_usage(self, mock_wait, mock_select, mock_goto):
        """15-minute interval data should be parsed with correct intervals."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: FIFTEEN_MIN_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)

        assert len(result) == 4
        assert result[0]["usage"] == 0.412
        assert result[1]["usage"] == 0.389
        assert result[2]["usage"] == 0.401
        assert result[3]["usage"] == 0.480

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_fifteen_min_interval_detected(self, mock_wait, mock_select, mock_goto):
        """15-minute data should produce 15-minute intervals between start and end."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: FIFTEEN_MIN_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)
        for entry in result:
            diff = entry["endTime"] + timedelta(seconds=1) - entry["startTime"]
            assert diff.total_seconds() == 900  # 15 minutes

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_fifteen_min_start_times_are_correct(self, mock_wait, mock_select, mock_goto):
        """Verify each 15-minute entry has non-overlapping start/end times."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: FIFTEEN_MIN_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)

        assert result[0]["startTime"].minute == 0
        assert result[0]["endTime"].minute == 14
        assert result[1]["startTime"].minute == 15
        assert result[1]["endTime"].minute == 29
        assert result[2]["startTime"].minute == 30
        assert result[2]["endTime"].minute == 44
        assert result[3]["startTime"].minute == 45
        assert result[3]["endTime"].minute == 59

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    @patch.object(RockyMountainPowerUtility, "_select_usage_option")
    @patch.object(RockyMountainPowerUtility, "_wait_for_xhr", return_value=True)
    def test_single_entry_falls_back_to_one_hour(self, mock_wait, mock_select, mock_goto):
        """With only one data point, interval detection falls back to 1 hour."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: SINGLE_ENTRY_USAGE_RESPONSE}
        util._page = MagicMock()

        result = util.get_usage_by_interval(days=1)
        assert len(result) == 1
        diff = result[0]["endTime"] + timedelta(seconds=1) - result[0]["startTime"]
        assert diff.total_seconds() == 3600


class TestDetectInterval:
    """Test the _detect_interval static method."""

    def test_detects_hourly_interval(self):
        entries = [
            {"readDate": "2023-11-22", "readTime": "01:00"},
            {"readDate": "2023-11-22", "readTime": "02:00"},
        ]
        result = RockyMountainPowerUtility._detect_interval(entries)
        assert result.total_seconds() == 3600

    def test_detects_fifteen_min_interval(self):
        entries = [
            {"readDate": "2023-11-22", "readTime": "00:15"},
            {"readDate": "2023-11-22", "readTime": "00:30"},
        ]
        result = RockyMountainPowerUtility._detect_interval(entries)
        assert result.total_seconds() == 900

    def test_detects_thirty_min_interval(self):
        entries = [
            {"readDate": "2023-11-22", "readTime": "00:30"},
            {"readDate": "2023-11-22", "readTime": "01:00"},
        ]
        result = RockyMountainPowerUtility._detect_interval(entries)
        assert result.total_seconds() == 1800

    def test_single_entry_defaults_to_one_hour(self):
        entries = [{"readDate": "2023-11-22", "readTime": "01:00"}]
        result = RockyMountainPowerUtility._detect_interval(entries)
        assert result.total_seconds() == 3600

    def test_empty_entries_defaults_to_one_hour(self):
        result = RockyMountainPowerUtility._detect_interval([])
        assert result.total_seconds() == 3600

    def test_handles_24_00_in_entries(self):
        """24:00 gets converted to 00:00, which may produce a negative diff;
        the method should fall back to 1 hour in that case."""
        entries = [
            {"readDate": "2023-11-22", "readTime": "23:00"},
            {"readDate": "2023-11-22", "readTime": "24:00"},
        ]
        result = RockyMountainPowerUtility._detect_interval(entries)
        assert result.total_seconds() == 3600


class TestForecastParsing:
    """Test parsing of forecast/meter type XHR responses."""

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    def test_parse_forecast(self, mock_goto):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getMeterType"
        util = RockyMountainPowerUtility()
        util.xhrs = {xhr_url: METER_TYPE_RESPONSE}
        util._page = MagicMock()

        result = util.get_forecast()

        assert result["projectedCost"] == "170"
        assert result["projectedCostHigh"] == "195"
        assert result["projectedCostLow"] == "144"
        assert result["startDateForAMIAcctView"] == "2024-01-15"
        assert result["endDateForAMIAcctView"] == "2024-02-14"

    @patch.object(RockyMountainPowerUtility, "goto_energy_usage")
    def test_parse_forecast_missing_xhr(self, mock_goto):
        """When the XHR hasn't been captured, forecast should be empty."""
        util = RockyMountainPowerUtility()
        util.xhrs = {}
        util._page = MagicMock()

        result = util.get_forecast()
        assert result == {}


class TestLoginParsing:
    """Test parsing of login XHR responses."""

    def test_login_parses_user_and_account(self):
        util = RockyMountainPowerUtility()
        util._playwright = MagicMock()
        util._browser = MagicMock()
        util._context = MagicMock()

        mock_page = MagicMock()
        util._page = mock_page

        mock_frame = MagicMock()
        mock_iframe_el = MagicMock()
        mock_iframe_el.content_frame.return_value = mock_frame
        mock_page.wait_for_selector.return_value = mock_iframe_el

        mock_page.query_selector.return_value = None

        util.xhrs = {
            "https://csapps.rockymountainpower.net/api/user/me": USER_ME_RESPONSE,
            "https://csapps.rockymountainpower.net/api/self-service/getAccountList": ACCOUNT_LIST_RESPONSE,
        }

        with patch.object(util, "init_browser"):
            util.login("testuser", "testpass")

        assert util.user_id == "user-123-uuid"
        assert util.account["accountNumber"] == "1234567890"


class TestRockyMountainPowerAPI:
    """Test the high-level RockyMountainPower API class."""

    def test_get_account(self):
        api = RockyMountainPower("user", "pass")
        api.account = {"accountNumber": "1234567890"}
        api.customer_id = "user-123-uuid"

        account = api.get_account()

        assert account.uuid == "1234567890"
        assert account.utility_account_id == "user-123-uuid"
        assert account.customer.uuid == "user-123-uuid"

    def test_get_forecast_builds_forecast_objects(self):
        api = RockyMountainPower("user", "pass")
        api.account = {"accountNumber": "1234567890"}
        api.customer_id = "user-123-uuid"

        forecast_data = json.loads(METER_TYPE_RESPONSE)["getMeterTypeResponseBody"]
        api.utility.forecast = forecast_data

        with patch.object(api.utility, "get_forecast"):
            forecasts = api.get_forecast()

        assert len(forecasts) == 1
        f = forecasts[0]
        assert f.forecasted_cost == 170.0
        assert f.forecasted_cost_low == 144.0
        assert f.forecasted_cost_high == 195.0
        assert f.account.uuid == "1234567890"

    def test_get_forecast_empty_when_no_data(self):
        api = RockyMountainPower("user", "pass")
        api.account = {"accountNumber": "1234567890"}
        api.customer_id = "user-123-uuid"
        api.utility.forecast = {}

        with patch.object(api.utility, "get_forecast"):
            forecasts = api.get_forecast()

        assert forecasts == []

    def test_get_cost_reads_returns_sorted(self):
        api = RockyMountainPower("user", "pass")
        fake_reads = [
            {"startTime": datetime(2024, 1, 2), "endTime": datetime(2024, 1, 2, 23, 59, 59), "usage": 20.0, "amount": 2.0},
            {"startTime": datetime(2024, 1, 1), "endTime": datetime(2024, 1, 1, 23, 59, 59), "usage": 10.0, "amount": 1.0},
        ]

        with patch.object(api.utility, "get_usage_by_month", return_value=fake_reads):
            reads = api.get_cost_reads(AggregateType.MONTH)

        assert len(reads) == 2
        assert reads[0].start_time < reads[1].start_time
        assert reads[0].consumption == 10.0
        assert reads[1].consumption == 20.0

    def test_get_cost_reads_null_amount_becomes_zero(self):
        api = RockyMountainPower("user", "pass")
        fake_reads = [
            {"startTime": datetime(2024, 1, 1), "endTime": datetime(2024, 1, 1, 23, 59, 59), "usage": 10.0, "amount": None},
        ]

        with patch.object(api.utility, "get_usage_by_month", return_value=fake_reads):
            reads = api.get_cost_reads(AggregateType.MONTH)

        assert reads[0].provided_cost == 0

    def test_get_cost_reads_dispatches_to_correct_method(self):
        api = RockyMountainPower("user", "pass")
        empty = []

        with patch.object(api.utility, "get_usage_by_month", return_value=empty) as mock_month:
            api.get_cost_reads(AggregateType.MONTH)
            mock_month.assert_called_once()

        with patch.object(api.utility, "get_usage_by_day", return_value=empty) as mock_day:
            api.get_cost_reads(AggregateType.DAY, 3)
            mock_day.assert_called_once_with(months=3)

        with patch.object(api.utility, "get_usage_by_interval", return_value=empty) as mock_interval:
            api.get_cost_reads(AggregateType.HOUR, 7)
            mock_interval.assert_called_once_with(days=7)

    def test_get_cost_reads_invalid_aggregate_type(self):
        api = RockyMountainPower("user", "pass")
        with pytest.raises(ValueError, match="not valid"):
            api.get_cost_reads("invalid")

    def test_get_account_triggers_login_if_no_account(self):
        api = RockyMountainPower("user", "pass")
        api.account = {}

        with patch.object(api, "login") as mock_login:
            def set_account():
                api.account = {"accountNumber": "999"}
                api.customer_id = "cust-id"
                api.utility.account = api.account
            mock_login.side_effect = set_account
            account = api.get_account()

        mock_login.assert_called_once()
        assert account.uuid == "999"

    def test_end_session(self):
        api = RockyMountainPower("user", "pass")
        with patch.object(api.utility, "on_quit") as mock_quit:
            api.end_session()
            mock_quit.assert_called_once()


class TestUtilityCleanup:
    """Test browser cleanup logic."""

    def test_on_quit_clears_references(self):
        util = RockyMountainPowerUtility()
        util._playwright = MagicMock()
        util._browser = MagicMock()
        util._context = MagicMock()
        util._page = MagicMock()

        util.on_quit()

        assert util._playwright is None
        assert util._browser is None
        assert util._context is None
        assert util._page is None

    def test_on_quit_handles_errors(self):
        util = RockyMountainPowerUtility()
        mock_context = MagicMock()
        mock_context.close.side_effect = Exception("already closed")
        util._context = mock_context
        util._browser = MagicMock()
        util._playwright = MagicMock()

        util.on_quit()
        assert util._context is None


class TestXHRCapture:
    """Test the response capture callback."""

    def test_on_response_captures_json(self):
        util = RockyMountainPowerUtility()
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.url = "https://example.com/api/data"
        mock_response.text.return_value = '{"key": "value"}'

        util._on_response(mock_response)

        assert "https://example.com/api/data" in util.xhrs
        assert util.xhrs["https://example.com/api/data"] == '{"key": "value"}'

    def test_on_response_ignores_non_json(self):
        util = RockyMountainPowerUtility()
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "text/html"}
        mock_response.url = "https://example.com/page"

        util._on_response(mock_response)

        assert "https://example.com/page" not in util.xhrs

    def test_on_response_handles_missing_content_type(self):
        util = RockyMountainPowerUtility()
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.url = "https://example.com/page"

        util._on_response(mock_response)

        assert "https://example.com/page" not in util.xhrs

    def test_on_response_handles_text_error(self):
        util = RockyMountainPowerUtility()
        mock_response = MagicMock()
        mock_response.headers = {"content-type": "application/json"}
        mock_response.url = "https://example.com/api/data"
        mock_response.text.side_effect = Exception("connection closed")

        util._on_response(mock_response)
        assert "https://example.com/api/data" not in util.xhrs


class TestBillingInfoParsing:
    """Test parsing of billing/account info XHR responses."""

    def test_get_billing_info_parses_all_fields(self):
        api = RockyMountainPower("user", "pass")
        api.account = {"accountNumber": "1234567890"}
        api.customer_id = "user-123-uuid"

        xhr_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"
        api.utility.xhrs = {xhr_url: ACCOUNT_INFO_RESPONSE}
        api.utility._page = MagicMock()

        billing = api.get_billing_info()

        assert billing is not None
        assert isinstance(billing, BillingInfo)
        assert billing.current_balance == 115.59
        assert billing.due_date.isoformat() == "2026-03-23"
        assert billing.past_due_amount == 0.0
        assert billing.last_payment_amount == 119.93
        assert billing.last_payment_date.isoformat() == "2026-02-20"
        assert billing.next_statement_date.isoformat() == "2026-03-30"
        assert billing.enrolled_payment_program == "APP"
        assert billing.account.uuid == "1234567890"

    def test_get_billing_info_empty_response(self):
        api = RockyMountainPower("user", "pass")
        api.account = {"accountNumber": "1234567890"}
        api.customer_id = "user-123-uuid"

        xhr_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"
        api.utility.xhrs = {xhr_url: ACCOUNT_INFO_EMPTY_RESPONSE}
        api.utility._page = MagicMock()

        billing = api.get_billing_info()

        assert billing is not None
        assert billing.current_balance == 0.0
        assert billing.due_date is None
        assert billing.past_due_amount == 0.0
        assert billing.last_payment_amount == 0.0
        assert billing.last_payment_date is None
        assert billing.next_statement_date is None

    def test_get_billing_info_no_xhr(self):
        api = RockyMountainPower("user", "pass")
        api.account = {"accountNumber": "1234567890"}
        api.customer_id = "user-123-uuid"
        api.utility.xhrs = {}
        api.utility._page = MagicMock()

        with patch.object(api.utility, "goto_billing"):
            with patch.object(api.utility, "_wait_for_xhr", return_value=False):
                billing = api.get_billing_info()

        assert billing is None

    def test_utility_get_billing_info_triggers_navigation(self):
        """If XHR isn't cached, should navigate to billing page."""
        util = RockyMountainPowerUtility()
        util.xhrs = {}
        util._page = MagicMock()

        with patch.object(util, "goto_billing") as mock_goto:
            with patch.object(util, "_wait_for_xhr", return_value=False):
                util.get_billing_info()

        mock_goto.assert_called_once()

    def test_utility_get_billing_info_skips_navigation_if_cached(self):
        """If XHR is already cached, should not navigate."""
        util = RockyMountainPowerUtility()
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"
        util.xhrs = {xhr_url: ACCOUNT_INFO_RESPONSE}
        util._page = MagicMock()

        with patch.object(util, "goto_billing") as mock_goto:
            result = util.get_billing_info()

        mock_goto.assert_not_called()
        assert result["totalDueAmount"] == 115.59


class TestMultiAccountSupport:
    """Test multiple account discovery and handling."""

    def test_login_stores_all_accounts(self):
        util = RockyMountainPowerUtility()
        util._playwright = MagicMock()
        util._browser = MagicMock()
        util._context = MagicMock()

        mock_page = MagicMock()
        util._page = mock_page

        mock_frame = MagicMock()
        mock_iframe_el = MagicMock()
        mock_iframe_el.content_frame.return_value = mock_frame
        mock_page.wait_for_selector.return_value = mock_iframe_el
        mock_page.query_selector.return_value = None

        util.xhrs = {
            "https://csapps.rockymountainpower.net/api/user/me": USER_ME_RESPONSE,
            "https://csapps.rockymountainpower.net/api/self-service/getAccountList": MULTI_ACCOUNT_LIST_RESPONSE,
        }

        with patch.object(util, "init_browser"):
            util.login("testuser", "testpass")

        assert len(util.accounts) == 2
        assert util.accounts[0]["accountNumber"] == "25656074-001 9"
        assert util.accounts[1]["accountNumber"] == "54802745-001 2"
        # First account is the default active one
        assert util.account["accountNumber"] == "25656074-001 9"

    def test_get_accounts_returns_all(self):
        api = RockyMountainPower("user", "pass")
        api.customer_id = "user-123-uuid"
        api.utility.accounts = json.loads(MULTI_ACCOUNT_LIST_RESPONSE)[
            "getAccountListResponseBody"
        ]["accountList"]["webAccount"]

        accounts = api.get_accounts()

        assert len(accounts) == 2
        assert isinstance(accounts[0], AccountInfo)
        assert accounts[0].account_number == "25656074-001 9"
        assert accounts[0].nickname == "9984 S"
        assert accounts[0].status == "Active"
        assert not accounts[0].is_business
        assert accounts[0].customer_idn == 25656074
        assert accounts[1].account_number == "54802745-001 2"
        assert accounts[1].nickname == "1058 W 570 N Orem"

    def test_get_accounts_empty(self):
        api = RockyMountainPower("user", "pass")
        api.utility.accounts = []

        accounts = api.get_accounts()
        assert accounts == []


class TestSelectorFallback:
    """Test CSS selector fallback mechanism."""

    def test_first_selector_matches(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()
        mock_el = MagicMock()
        util._page.query_selector.side_effect = [mock_el]

        result = util._query_selector_with_fallback(["sel1", "sel2"])
        assert result is mock_el
        util._page.query_selector.assert_called_once_with("sel1")

    def test_fallback_to_second_selector(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()
        mock_el = MagicMock()
        util._page.query_selector.side_effect = [None, mock_el]

        result = util._query_selector_with_fallback(["sel1", "sel2"])
        assert result is mock_el
        assert util._page.query_selector.call_count == 2

    def test_no_selector_matches(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()
        util._page.query_selector.return_value = None

        result = util._query_selector_with_fallback(["sel1", "sel2"])
        assert result is None

    def test_query_selector_all_fallback(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()
        util._page.query_selector_all.side_effect = [[], [MagicMock(), MagicMock()]]

        result = util._query_selector_all_with_fallback(["sel1", "sel2"])
        assert len(result) == 2


class TestSwitchAccount:
    """Test account switching logic."""

    def test_switch_account_success(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()

        mock_picker = MagicMock()
        mock_option = MagicMock()
        mock_option.evaluate.return_value = "South Jordan (25656074)"

        with patch.object(util, "_query_selector_with_fallback", return_value=mock_picker):
            with patch.object(util, "_query_selector_all_with_fallback", return_value=[mock_option]):
                with patch.object(util, "_wait_for_xhr", return_value=True):
                    result = util.switch_account("South Jordan")

        assert result is True
        mock_picker.click.assert_called_once()
        mock_option.click.assert_called_once()

    def test_switch_account_not_found(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()

        mock_picker = MagicMock()
        mock_option = MagicMock()
        mock_option.evaluate.return_value = "South Jordan (25656074)"

        with patch.object(util, "_query_selector_with_fallback", return_value=mock_picker):
            with patch.object(util, "_query_selector_all_with_fallback", return_value=[mock_option]):
                result = util.switch_account("Nonexistent Account")

        assert result is False
        util._page.keyboard.press.assert_called_once_with("Escape")

    def test_switch_account_no_picker(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()

        with patch.object(util, "_query_selector_with_fallback", return_value=None):
            result = util.switch_account("South Jordan")

        assert result is False

    def test_switch_clears_xhrs(self):
        util = RockyMountainPowerUtility()
        util._page = MagicMock()
        util.xhrs = {"https://example.com/old": "data"}

        mock_picker = MagicMock()
        mock_option = MagicMock()
        mock_option.evaluate.return_value = "South Jordan"

        with patch.object(util, "_query_selector_with_fallback", return_value=mock_picker):
            with patch.object(util, "_query_selector_all_with_fallback", return_value=[mock_option]):
                with patch.object(util, "_wait_for_xhr", return_value=True):
                    util.switch_account("South Jordan")

        assert util.xhrs == {}

    def test_high_level_switch_delegates(self):
        api = RockyMountainPower("user", "pass")
        with patch.object(api.utility, "switch_account", return_value=True) as mock_switch:
            result = api.switch_account("South Jordan")

        assert result is True
        mock_switch.assert_called_once_with("South Jordan")


class TestSelectUsageOption:
    """Test the usage dropdown selection with bounds checking."""

    def test_select_usage_option_out_of_range(self):
        """Should log warning and return without crashing when fallback index is invalid."""
        util = RockyMountainPowerUtility()
        util._page = MagicMock()

        dropdowns = [MagicMock(), MagicMock()]
        mock_options = [MagicMock() for _ in range(2)]
        with patch.object(util, "_query_selector_with_fallback", return_value=None):
            with patch.object(
                util, "_query_selector_all_with_fallback", side_effect=[dropdowns, mock_options]
            ):
                util._select_usage_option(fallback_index=99)  # Out of range, should not crash

    def test_select_usage_no_options(self):
        """Should handle case where dropdown has no options."""
        util = RockyMountainPowerUtility()
        util._page = MagicMock()

        dropdowns = [MagicMock() for _ in range(2)]
        with patch.object(util, "_query_selector_with_fallback", return_value=None):
            with patch.object(util, "_query_selector_all_with_fallback", side_effect=[dropdowns, []]):
                util._select_usage_option(fallback_index=0)  # Should not crash
