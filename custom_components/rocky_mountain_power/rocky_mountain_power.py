"""Implementation of Rocky Mountain Power API using Playwright."""
import dataclasses
import json
import logging
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Optional

import arrow
from playwright.sync_api import sync_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeout

_LOGGER = logging.getLogger(__name__)


def _parse_dollar(value: str) -> float | None:
    """Parse a dollar string like '$123.45' or '1,234.56' to float."""
    if not value:
        return None
    cleaned = value.strip().lstrip("$").replace(",", "")
    try:
        return float(cleaned) or None
    except ValueError:
        return None


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
    due_date: Optional[date]
    past_due_amount: float
    last_payment_amount: float
    last_payment_date: Optional[date]
    next_statement_date: Optional[date]
    enrolled_payment_program: Optional[str]


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


# CSS selectors with fallbacks for resilience against RMP site redesigns.
_SELECTORS = {
    "cookie_banner_btn": [
        "wcss-cookie-banner>aside>button",
        "wcss-cookie-banner button",
        "button[class*='cookie']",
    ],
    "login_iframe": [
        "iframe#loginframe",
        "iframe[src*='login']",
    ],
    "account_picker": [
        "wcss-account-picker mat-select",
        "mat-select[aria-label*='account']",
        "[class*='account-picker'] mat-select",
    ],
    "dropdown_option": [
        "mat-option",
        ".mat-option",
    ],
    "usage_dropdown": [
        "div.mat-form-field-infix",
        ".mat-form-field-infix",
    ],
    "usage_option": [
        ".mat-option",
        "mat-option",
    ],
    "prev_button": [
        "button.link:has-text('PREVIOUS')",
        "button:has-text('PREVIOUS')",
        "button:has-text('Previous')",
    ],
}


class RockyMountainPowerUtility:
    """Browser automation for the Rocky Mountain Power website."""

    LOGIN_URL = "https://csapps.rockymountainpower.net/idm/login"
    TZ = "America/Denver"

    def __init__(self):
        self.user_id = None
        self.account = {}
        self.accounts: list[dict] = []
        self.forecast = {}
        self.xhrs: dict[str, str] = {}
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None

    def _query_selector_with_fallback(self, selectors: list[str]) -> Any | None:
        """Try multiple CSS selectors, returning the first match."""
        page = self._page
        for selector in selectors:
            el = page.query_selector(selector)
            if el:
                return el
        _LOGGER.debug("No element found for selectors: %s", selectors)
        return None

    def _query_selector_all_with_fallback(self, selectors: list[str]) -> list:
        """Try multiple CSS selectors, returning results from the first that matches."""
        page = self._page
        for selector in selectors:
            els = page.query_selector_all(selector)
            if els:
                return els
        _LOGGER.debug("No elements found for selectors: %s", selectors)
        return []

    def _on_response(self, response):
        """Capture XHR JSON responses."""
        if "json" in (response.headers.get("content-type", "")):
            try:
                self.xhrs[response.url] = response.text()
            except Exception:
                _LOGGER.debug("Failed to capture XHR response for %s", response.url)

    def on_quit(self, *args, **kwargs):
        """Close the browser and clean up resources."""
        try:
            if self._context:
                self._context.close()
            if self._browser:
                self._browser.close()
            if self._playwright:
                self._playwright.stop()
        except Exception:
            _LOGGER.debug("Error during browser cleanup", exc_info=True)
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    def init_browser(self):
        """Launch a headless Chromium browser."""
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.on("response", self._on_response)

    def login(self, username, password):
        """Navigate to the RMP login page, authenticate, and capture account data."""
        self.init_browser()
        page = self._page

        page.goto(self.LOGIN_URL)
        try:
            page.wait_for_function("document.title === 'Sign in'", timeout=30000)
        except PlaywrightTimeout as err:
            _LOGGER.error("Timed out waiting for login page to load")
            raise CannotConnect from err

        # Dismiss cookie banner if present
        cookie_btn = self._query_selector_with_fallback(_SELECTORS["cookie_banner_btn"])
        if cookie_btn and cookie_btn.is_visible():
            cookie_btn.click()

        # Wait for and switch to login iframe
        iframe_el = None
        for selector in _SELECTORS["login_iframe"]:
            try:
                iframe_el = page.wait_for_selector(selector, timeout=15000)
                if iframe_el:
                    break
            except PlaywrightTimeout:
                continue
        if not iframe_el:
            _LOGGER.error("Login iframe not found with any known selector")
            raise CannotConnect
        frame = iframe_el.content_frame()

        frame.fill("input#signInName", username)
        frame.fill("input#password", password)
        frame.click("button#next")

        try:
            page.wait_for_function("document.title === 'My account'", timeout=30000)
        except PlaywrightTimeout as err:
            _LOGGER.error("Login failed — did not reach 'My account' page")
            raise InvalidAuth from err

        # Wait for critical XHRs to be captured
        user_me_url = "https://csapps.rockymountainpower.net/api/user/me"
        account_list_url = "https://csapps.rockymountainpower.net/api/self-service/getAccountList"
        self._wait_for_xhr(user_me_url, timeout=15000)
        self._wait_for_xhr(account_list_url, timeout=15000)

        if user_me_url not in self.xhrs or account_list_url not in self.xhrs:
            _LOGGER.error("Login succeeded but critical API responses were not captured")
            raise CannotConnect

        me = json.loads(self.xhrs[user_me_url])
        self.user_id = me["id"]
        accounts_data = json.loads(self.xhrs[account_list_url])
        self.accounts = accounts_data["getAccountListResponseBody"]["accountList"]["webAccount"]
        self.account = self.accounts[0]
        return self.xhrs

    def switch_account(self, nickname: str) -> bool:
        """Switch to a different account using the account picker dropdown.

        Args:
            nickname: The account nickname to switch to (from getAccountList).

        Returns:
            True if successfully switched, False if account not found.
        """
        page = self._page
        picker = self._query_selector_with_fallback(_SELECTORS["account_picker"])
        if not picker:
            _LOGGER.warning("Account picker not found on page")
            return False

        # Open the dropdown
        picker.click()
        page.wait_for_timeout(1000)

        # Find and click the matching option
        options = self._query_selector_all_with_fallback(_SELECTORS["dropdown_option"])
        for opt in options:
            text = opt.evaluate("el => el.textContent.trim()")
            if nickname in text:
                opt.click()
                # Wait for account data to reload via XHR
                acct_info_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"
                self.xhrs.clear()
                self._wait_for_xhr(acct_info_url, timeout=10000)
                return True

        # Close dropdown if we didn't find a match
        _LOGGER.warning("Account '%s' not found in picker options", nickname)
        page.keyboard.press("Escape")
        return False

    def goto_energy_usage(self):
        """Navigate to the energy usage page."""
        page = self._page
        page.goto("https://csapps.rockymountainpower.net/secure/my-account/energy-usage")
        try:
            page.wait_for_function("document.title === 'Energy usage'", timeout=30000)
        except PlaywrightTimeout as err:
            _LOGGER.error("Timed out waiting for energy usage page")
            raise CannotConnect from err

    def goto_billing(self):
        """Navigate to the billing & payment history page."""
        page = self._page
        page.goto("https://csapps.rockymountainpower.net/secure/my-account/billing-payment-history")
        try:
            page.wait_for_function(
                "document.title === 'Billing & payment history'",
                timeout=30000,
            )
        except PlaywrightTimeout as err:
            _LOGGER.error("Timed out waiting for billing page")
            raise CannotConnect from err

    def get_billing_info(self) -> dict | None:
        """Get billing info from the account info XHR (captured during login/navigation)."""
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"

        # The billing page triggers getAccountInfo if we haven't captured it yet
        if xhr_url not in self.xhrs:
            self.goto_billing()
            self._wait_for_xhr(xhr_url, timeout=10000)

        if xhr_url in self.xhrs:
            details = json.loads(self.xhrs[xhr_url])
            return details.get("getAccountInfoResponseBody", {}).get("accountInfo", {})
        return None

    def get_forecast(self):
        """Navigate to the energy usage page and capture the forecast XHR."""
        self.goto_energy_usage()
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getMeterType"
        self._wait_for_xhr(xhr_url, timeout=15000)

        if xhr_url in self.xhrs:
            details = json.loads(self.xhrs[xhr_url])
            self.forecast = details.get("getMeterTypeResponseBody", {})

        return self.forecast

    def _wait_for_xhr(self, xhr_url: str, timeout: int = 30000) -> bool:
        """Wait for a specific XHR URL to appear in captured responses."""
        page = self._page
        interval = 500
        elapsed = 0
        while xhr_url not in self.xhrs and elapsed < timeout:
            page.wait_for_timeout(interval)
            elapsed += interval
        if xhr_url not in self.xhrs:
            _LOGGER.debug("XHR not captured within %dms: %s", timeout, xhr_url)
        return xhr_url in self.xhrs

    def _select_usage_option(self, option_index: int):
        """Click the usage dropdown and select an option by index."""
        page = self._page
        dropdowns = self._query_selector_all_with_fallback(_SELECTORS["usage_dropdown"])
        if len(dropdowns) <= 3:
            _LOGGER.warning(
                "Expected at least 4 usage dropdowns, found %d", len(dropdowns)
            )
            return
        dropdowns[3].click()
        page.wait_for_timeout(500)
        options = self._query_selector_all_with_fallback(_SELECTORS["usage_option"])
        if not options:
            _LOGGER.warning("No usage options found in dropdown")
            return
        # Clamp index to valid range
        idx = option_index if option_index >= 0 else len(options) + option_index
        if idx < 0 or idx >= len(options):
            _LOGGER.warning("Usage option index %d out of range (0-%d)", option_index, len(options) - 1)
            return
        options[idx].click()

    def _click_previous_button(self) -> bool:
        """Click the PREVIOUS button to go back one period. Returns False if not found."""
        prev_btn = self._query_selector_with_fallback(_SELECTORS["prev_button"])
        if not prev_btn:
            return False
        try:
            prev_btn.click()
            return True
        except Exception:
            _LOGGER.debug("Failed to click PREVIOUS button", exc_info=True)
            return False

    def get_usage_by_month(self):
        """Get monthly usage data from the energy usage page."""
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        self.goto_energy_usage()
        self._select_usage_option(0)
        self._wait_for_xhr(xhr_url)

        details = json.loads(self.xhrs.get(xhr_url, "{}"))
        usage = []
        for d in details.get("getUsageHistoryAndGraphDataV1ResponseBody", {}).get("usageHistory", {}).get("usageHistoryLineItem", []):
            end_date = d.get("usagePeriodEndDate")
            if not end_date:
                _LOGGER.debug("Skipping monthly entry with no usagePeriodEndDate")
                continue
            end_time = arrow.get(datetime.fromisoformat(end_date), self.TZ).datetime
            try:
                start_time = end_time - timedelta(days=int(d["elapsedDays"]))
            except (KeyError, ValueError):
                start_time = end_time.replace(day=1)
            amount = _parse_dollar(d.get("invoiceAmount", ""))
            usage.append({
                "startTime": start_time,
                "endTime": end_time - timedelta(seconds=1),
                "usage": float(d.get("kwhUsageQuantity", 0)),
                "amount": amount,
            })
        return usage

    def get_usage_by_day(self, months=1):
        """Get daily usage data, paginating back the specified number of months."""
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
                end_date = d.get("usagePeriodEndDate")
                if not end_date:
                    continue
                end_time = arrow.get(datetime.fromisoformat(end_date), self.TZ).datetime
                start_time = end_time - timedelta(days=1)
                amount = _parse_dollar(d.get("dollerAmount", ""))
                usage.append({
                    "startTime": start_time,
                    "endTime": end_time - timedelta(seconds=1),
                    "usage": float(d.get("kwhUsageQuantity", 0)),
                    "amount": amount,
                })
            months -= 1
            if months > 0:
                self.xhrs.pop(xhr_url, None)
                if not self._click_previous_button():
                    break
                if not self._wait_for_xhr(xhr_url):
                    break
        return usage

    def download_daily_usage(self):
        """Download Green Button data from the energy usage page."""
        self.goto_energy_usage()
        page = self._page
        dropdowns = self._query_selector_all_with_fallback(_SELECTORS["usage_dropdown"])
        if len(dropdowns) <= 3:
            _LOGGER.warning("Could not find usage dropdown for Green Button download")
            return None
        dropdowns[3].click()
        page.wait_for_timeout(500)
        options = self._query_selector_all_with_fallback(_SELECTORS["usage_option"])
        if not options:
            _LOGGER.warning("No usage options found for Green Button download")
            return None
        options[-1].click()

        with page.expect_download() as download_info:
            page.click("text=DOWNLOAD GREEN BUTTON DATA")
        download = download_info.value
        path = download.path()
        with open(path, "r") as file:
            return file.read()

    def get_usage_by_hour(self, days=1):
        """Get hourly usage data, paginating back the specified number of days."""
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
                if not self._click_previous_button():
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
        """Close the browser and clean up resources."""
        self.utility.on_quit()

    def get_accounts(self) -> list[AccountInfo]:
        """Get all accounts for the signed in user."""
        return [
            AccountInfo(
                account_number=acct["accountNumber"],
                address=acct.get("mailingAddressLine1", "").strip(),
                nickname=acct.get("accountNickname", "").strip(),
                status=acct.get("status", "Unknown"),
                is_business=acct.get("isBusiness", False),
                customer_idn=acct.get("customer", {}).get("idn", 0),
            )
            for acct in self.utility.accounts
        ]

    def get_account(self) -> Account:
        """Get the active account for the signed in user."""
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

    def get_billing_info(self) -> Optional[BillingInfo]:
        """Get billing and payment info for the active account."""
        info = self.utility.get_billing_info()
        if info is None:
            return None

        due_date = None
        if info.get("currentDueAmountDueDate"):
            try:
                due_date = date.fromisoformat(info["currentDueAmountDueDate"])
            except (ValueError, TypeError):
                pass

        last_payment_date = None
        if info.get("lastPaymentDate"):
            try:
                last_payment_date = date.fromisoformat(info["lastPaymentDate"])
            except (ValueError, TypeError):
                pass

        next_statement_date = None
        if info.get("nextStatementDate"):
            try:
                next_statement_date = date.fromisoformat(info["nextStatementDate"])
            except (ValueError, TypeError):
                pass

        return BillingInfo(
            account=Account(
                customer=Customer(uuid=self.customer_id),
                uuid=self.account["accountNumber"],
                utility_account_id=self.customer_id,
            ),
            current_balance=float(info.get("totalDueAmount", 0)),
            due_date=due_date,
            past_due_amount=float(info.get("pastDueAmount", 0)),
            last_payment_amount=float(info.get("lastPaymentAmount", 0)),
            last_payment_date=last_payment_date,
            next_statement_date=next_statement_date,
            enrolled_payment_program=info.get("enrolledPaymentProgram"),
        )

    def switch_account(self, nickname: str) -> bool:
        """Switch the active account on the RMP site."""
        return self.utility.switch_account(nickname)

    def _get_account(self) -> dict:
        """Get account associated with the user."""
        if not self.account:
            self.login()
            self.account = self.utility.account
        if not self.account:
            raise CannotConnect("No account data available after login")
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
