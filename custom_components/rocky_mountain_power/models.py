"""Data models for the Rocky Mountain Power integration."""
from __future__ import annotations

import dataclasses
from datetime import date, datetime
from enum import Enum


class AggregateType(Enum):
    """How to aggregate historical data."""

    MONTH = "month"
    DAY = "day"
    HOUR = "hour"

    def __str__(self) -> str:
        """Return the value of the enum."""
        return self.value


@dataclasses.dataclass
class Customer:
    """Data about a customer."""

    uuid: str


@dataclasses.dataclass
class Account:
    """Data about an account."""

    customer: Customer
    uuid: str
    utility_account_id: str


@dataclasses.dataclass
class AccountInfo:
    """Extended account info from getAccountList."""

    account_number: str
    address: str
    nickname: str
    status: str
    is_business: bool
    customer_idn: int


@dataclasses.dataclass
class Forecast:
    """Forecast data for an account."""

    account: Account
    start_date: date
    end_date: date
    current_date: date
    forecasted_cost: float
    forecasted_cost_low: float
    forecasted_cost_high: float


@dataclasses.dataclass
class BillingInfo:
    """Billing and payment info for an account."""

    account: Account
    current_balance: float
    due_date: date | None
    past_due_amount: float
    last_payment_amount: float
    last_payment_date: date | None
    next_statement_date: date | None
    enrolled_payment_program: str | None


@dataclasses.dataclass
class CostRead:
    """A read from the meter that has both consumption and cost data."""

    start_time: datetime
    end_time: datetime
    consumption: float  # taken from value field, in KWH
    provided_cost: float  # in $


@dataclasses.dataclass
class UsageRead:
    """A read from the meter that has consumption data."""

    start_time: datetime
    end_time: datetime
    consumption: float  # taken from consumption.value field, in KWH
