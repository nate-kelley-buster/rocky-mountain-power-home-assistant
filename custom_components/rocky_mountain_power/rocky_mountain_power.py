"""Implementation of Rocky Mountain Power API using Playwright."""
import dataclasses
import json
import locale
import logging
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Optional

import arrow
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext

_LOGGER = logging.getLogger(__file__)
locale.setlocale(locale.LC_ALL, "en_US")


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


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


class RockyMountainPowerUtility:
    LOGIN_URL = "https://csapps.rockymountainpower.net/idm/login"
    TZ = "America/Denver"

    def __init__(self):
        self.user_id = None
        self.account = {}
        self.forecast = {}
        self.xhrs: dict[str, str] = {}
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _on_response(self, response):
        """Capture XHR JSON responses."""
        if "json" in (response.headers.get("content-type", "")):
            try:
                self.xhrs[response.url] = response.text()
            except Exception:
                pass

    def on_quit(self, *args, **kwargs):
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            pass
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def init_browser(self):
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.on("response", self._on_response)

    def login(self, username, password):
        self.init_browser()
        page = self._page

        page.goto(self.LOGIN_URL)
        try:
            page.wait_for_function("document.title === 'Sign in'", timeout=30000)
        except Exception:
            raise CannotConnect

        # Dismiss cookie banner if present
        cookie_btn = page.query_selector("wcss-cookie-banner>aside>button")
        if cookie_btn and cookie_btn.is_visible():
            cookie_btn.click()

        # Wait for and switch to login iframe
        iframe_el = page.wait_for_selector("iframe#loginframe", timeout=30000)
        frame = iframe_el.content_frame()

        frame.fill("input#signInName", username)
        frame.fill("input#password", password)
        frame.click("button#next")

        try:
            page.wait_for_function("document.title === 'My account'", timeout=30000)
        except Exception:
            raise InvalidAuth

        # Wait briefly for XHR responses to be captured
        page.wait_for_timeout(2000)

        me = json.loads(self.xhrs["https://csapps.rockymountainpower.net/api/user/me"])
        self.user_id = me["id"]
        accounts = json.loads(self.xhrs["https://csapps.rockymountainpower.net/api/self-service/getAccountList"])
        self.account = accounts["getAccountListResponseBody"]["accountList"]["webAccount"][0]
        return self.xhrs

    def goto_energy_usage(self):
        page = self._page
        page.goto("https://csapps.rockymountainpower.net/secure/my-account/energy-usage")
        try:
            page.wait_for_function("document.title === 'Energy usage'", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception:
            raise CannotConnect

    def get_forecast(self):
        self.goto_energy_usage()
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getMeterType"
        page = self._page
        page.wait_for_timeout(2000)

        if xhr_url not in self.xhrs:
            # Wait a bit more for the XHR to come in
            page.wait_for_timeout(5000)

        if xhr_url in self.xhrs:
            details = json.loads(self.xhrs[xhr_url])
            self.forecast = details.get("getMeterTypeResponseBody", {})

        return self.forecast

    def _wait_for_xhr(self, xhr_url: str, timeout: int = 30000):
        """Wait for a specific XHR URL to appear in captured responses."""
        page = self._page
        interval = 500
        elapsed = 0
        while xhr_url not in self.xhrs and elapsed < timeout:
            page.wait_for_timeout(interval)
            elapsed += interval
        return xhr_url in self.xhrs

    def _select_usage_option(self, option_index: int):
        """Click the usage dropdown and select an option by index."""
        page = self._page
        dropdowns = page.query_selector_all("div.mat-form-field-infix")
        dropdowns[3].click()
        page.wait_for_timeout(500)
        options = page.query_selector_all(".mat-option")
        options[option_index].click()

    def get_usage_by_month(self):
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        self.goto_energy_usage()
        self._select_usage_option(0)
        self._wait_for_xhr(xhr_url)

        details = json.loads(self.xhrs[xhr_url])
        usage = []
        for d in details.get("getUsageHistoryAndGraphDataV1ResponseBody", {}).get("usageHistory", {}).get("usageHistoryLineItem", []):
            end_time = arrow.get(datetime.fromisoformat(d["usagePeriodEndDate"]), self.TZ).datetime
            try:
                start_time = end_time - timedelta(days=int(d["elapsedDays"]))
            except KeyError:
                start_time = end_time.replace(day=1)
            amount = None
            try:
                amount = locale.atof(d.get("invoiceAmount", "").strip("$")) or None
            except ValueError:
                pass
            usage.append({
                "startTime": start_time,
                "endTime": end_time - timedelta(seconds=1),
                "usage": float(d.get("kwhUsageQuantity", 0)),
                "amount": amount,
            })
        return usage

    def get_usage_by_day(self, months=1):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getUsageForDateRange"
        self.goto_energy_usage()
        self._select_usage_option(2)
        self._wait_for_xhr(xhr_url)

        usage = []
        while months > 0:
            if xhr_url not in self.xhrs:
                break
            details = json.loads(self.xhrs[xhr_url])
            for d in details.get("getUsageForDateRangeResponseBody", {}).get("dailyUsageList", {}).get("usgHistoryLineItem", []):
                end_time = arrow.get(datetime.fromisoformat(d["usagePeriodEndDate"]), self.TZ).datetime
                start_time = end_time - timedelta(days=1)
                amount = None
                try:
                    amount = locale.atof(d.get("dollerAmount", "").strip("$")) or None
                except ValueError:
                    pass
                usage.append({
                    "startTime": start_time,
                    "endTime": end_time - timedelta(seconds=1),
                    "usage": float(d.get("kwhUsageQuantity", 0)),
                    "amount": amount,
                })
            months -= 1
            if months > 0:
                self.xhrs.pop(xhr_url, None)
                page = self._page
                prev_btn = page.query_selector("button.link:has-text('PREVIOUS')")
                if not prev_btn:
                    break
                try:
                    prev_btn.click()
                except Exception:
                    break
                if not self._wait_for_xhr(xhr_url):
                    break
        return usage

    def get_usage_by_hour(self, days=1):
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        self.goto_energy_usage()
        self._select_usage_option(-1)
        self._wait_for_xhr(xhr_url)

        usage = []
        while days > 0:
            if xhr_url not in self.xhrs:
                break
            details = json.loads(self.xhrs[xhr_url])
            for d in details.get("getIntervalUsageForDateResponseBody", {}).get("response", {}).get("intervalDataResponse", []):
                end_time = arrow.get(
                    datetime.fromisoformat(f"{d['readDate']}T{d['readTime'].replace('24', '00')}:00"),
                    self.TZ,
                ).datetime
                start_time = end_time - timedelta(hours=1)
                usage.append({
                    "startTime": start_time,
                    "endTime": end_time - timedelta(seconds=1),
                    "usage": float(d.get("usage", 0)),
                    "amount": None,
                })
            days -= 1
            if days > 0:
                self.xhrs.pop(xhr_url, None)
                page = self._page
                prev_btn = page.query_selector("button.link:has-text('PREVIOUS')")
                if not prev_btn:
                    break
                try:
                    prev_btn.click()
                except Exception:
                    break
                if not self._wait_for_xhr(xhr_url):
                    break
        return usage


class RockyMountainPower:
    """Class that can get historical and forecasted usage/cost from Rocky Mountain Power."""

    def __init__(
        self,
        username: str,
        password: str,
    ) -> None:
        """Initialize."""
        self.username: str = username
        self.password: str = password
        self.account = {}
        self.customer_id = None
        self.utility: RockyMountainPowerUtility = RockyMountainPowerUtility()

    def login(self) -> None:
        """Login to the utility website.

        :raises InvalidAuth: if login information is incorrect
        :raises CannotConnect: if we receive any HTTP error
        """
        self.utility.login(self.username, self.password)
        if not self.account:
            self.account = self.utility.account
        if not self.customer_id:
            self.customer_id = self.utility.user_id

    def end_session(self) -> None:
        self.utility.on_quit()

    def get_account(self) -> Account:
        """Get the account for the signed in user."""
        account = self._get_account()
        return Account(
            customer=Customer(uuid=self.customer_id),
            uuid=account["accountNumber"],
            utility_account_id=self.customer_id,
        )

    def get_forecast(self) -> list[Forecast]:
        """Get current and forecasted usage and cost for the current monthly bill."""
        forecasts = []
        self.utility.get_forecast()
        if self.utility.forecast:
            forecast = self.utility.forecast
            forecasts.append(
                Forecast(
                    account=Account(
                        customer=Customer(uuid=self.customer_id),
                        uuid=self.account["accountNumber"],
                        utility_account_id=self.customer_id,
                    ),
                    start_date=arrow.get(date.fromisoformat(forecast["startDateForAMIAcctView"]), self.utility.TZ).datetime,
                    end_date=arrow.get(date.fromisoformat(forecast["endDateForAMIAcctView"]), self.utility.TZ).datetime,
                    current_date=arrow.get(date.today(), self.utility.TZ).datetime,
                    forecasted_cost=float(forecast.get("projectedCost", 0)),
                    forecasted_cost_low=float(forecast.get("projectedCostLow", 0)),
                    forecasted_cost_high=float(forecast.get("projectedCostHigh", 0)),
                )
            )
        return forecasts

    def _get_account(self) -> Any:
        """Get account associated with the user."""
        if not self.account:
            self.login()
            self.account = self.utility.account
        assert self.account
        return self.account

    def get_cost_reads(
        self,
        aggregate_type: AggregateType,
        period: Optional[int] = 1,
    ) -> list[CostRead]:
        """Get usage and cost data aggregated by month/day/hour."""
        reads = self._get_dated_data(aggregate_type, period=period)
        reads.sort(key=lambda x: x["startTime"])
        return [
            CostRead(
                start_time=read["startTime"],
                end_time=read["endTime"],
                consumption=read["usage"],
                provided_cost=read["amount"] or 0,
            ) for read in reads
        ]

    def _get_dated_data(
        self,
        aggregate_type: AggregateType,
        period: Optional[int] = 1,
    ) -> list[Any]:
        if aggregate_type == AggregateType.MONTH:
            return self.utility.get_usage_by_month()
        elif aggregate_type == AggregateType.DAY:
            return self.utility.get_usage_by_day(months=period)
        elif aggregate_type == AggregateType.HOUR:
            return self.utility.get_usage_by_hour(days=period)
        else:
            raise ValueError(f"aggregate_type {aggregate_type} is not valid")


if __name__ == '__main__':
    api = RockyMountainPower(
        'USERNAME',
        'PASSWORD',
    )

    errors: dict[str, str] = {}
    try:
        api.login()
        print("Logged in, trying to fetch forecasts")
        forecasts = api.get_forecast()
        print("Got forecasts")
        print(forecasts)
        print("Fetching cost reads")
        cost_reads = api.get_cost_reads(AggregateType.MONTH)
        print(cost_reads)

        cost_reads = api.get_cost_reads(AggregateType.DAY, 24)
        print(cost_reads)

        cost_reads = api.get_cost_reads(AggregateType.HOUR, 60)
        print(cost_reads)
    except InvalidAuth:
        errors["base"] = "invalid_auth"
    except CannotConnect:
        errors["base"] = "cannot_connect"
    except Exception as e:
        print(f"Unhandled exception: {e.__class__.__name__}: {e}")
    finally:
        api.end_session()

    if errors:
        print("Got errors")
        print(errors)
    else:
        print("No errors")
