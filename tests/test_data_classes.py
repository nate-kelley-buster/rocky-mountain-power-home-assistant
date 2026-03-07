"""Tests for data classes and enums."""
from datetime import date, datetime

from custom_components.rocky_mountain_power.exceptions import CannotConnect, InvalidAuth
from custom_components.rocky_mountain_power.models import (
    Account,
    AggregateType,
    CostRead,
    Customer,
    Forecast,
    UsageRead,
)


class TestAggregateType:
    def test_values(self):
        assert AggregateType.MONTH.value == "month"
        assert AggregateType.DAY.value == "day"
        assert AggregateType.HOUR.value == "hour"

    def test_str(self):
        assert str(AggregateType.MONTH) == "month"
        assert str(AggregateType.DAY) == "day"
        assert str(AggregateType.HOUR) == "hour"


class TestCustomer:
    def test_create(self):
        customer = Customer(uuid="test-uuid")
        assert customer.uuid == "test-uuid"


class TestAccount:
    def test_create(self):
        customer = Customer(uuid="cust-uuid")
        account = Account(
            customer=customer,
            uuid="acct-uuid",
            utility_account_id="util-id",
        )
        assert account.customer.uuid == "cust-uuid"
        assert account.uuid == "acct-uuid"
        assert account.utility_account_id == "util-id"


class TestForecast:
    def test_create(self):
        customer = Customer(uuid="cust-uuid")
        account = Account(customer=customer, uuid="acct-uuid", utility_account_id="util-id")
        forecast = Forecast(
            account=account,
            start_date=date(2024, 1, 15),
            end_date=date(2024, 2, 14),
            current_date=date(2024, 1, 20),
            forecasted_cost=170.0,
            forecasted_cost_low=144.0,
            forecasted_cost_high=195.0,
        )
        assert forecast.forecasted_cost == 170.0
        assert forecast.forecasted_cost_low == 144.0
        assert forecast.forecasted_cost_high == 195.0
        assert forecast.start_date == date(2024, 1, 15)
        assert forecast.end_date == date(2024, 2, 14)


class TestCostRead:
    def test_create(self):
        read = CostRead(
            start_time=datetime(2024, 1, 1, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 59, 59),
            consumption=1.5,
            provided_cost=0.15,
        )
        assert read.consumption == 1.5
        assert read.provided_cost == 0.15


class TestUsageRead:
    def test_create(self):
        read = UsageRead(
            start_time=datetime(2024, 1, 1, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 59, 59),
            consumption=1.5,
        )
        assert read.consumption == 1.5


class TestExceptions:
    def test_cannot_connect(self):
        exc = CannotConnect()
        assert isinstance(exc, Exception)

    def test_invalid_auth(self):
        exc = InvalidAuth()
        assert isinstance(exc, Exception)
