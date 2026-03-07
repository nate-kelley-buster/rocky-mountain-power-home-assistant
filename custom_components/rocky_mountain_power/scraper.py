"""Playwright browser automation for the Rocky Mountain Power website."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

import arrow

from .exceptions import CannotConnect, InvalidAuth

try:
    from playwright.sync_api import (
        Browser,
        BrowserContext,
        Page,
        TimeoutError as PlaywrightTimeout,
        sync_playwright,
    )
except ImportError:
    Browser = Any
    BrowserContext = Any
    Page = Any
    sync_playwright = None

    class PlaywrightTimeout(Exception):
        """Fallback timeout error when Playwright is unavailable."""


_LOGGER = logging.getLogger(__name__)


def _parse_interval_time(read_date: str, read_time: str, tz: str = "America/Denver") -> datetime:
    """Parse readDate and readTime into a datetime.

    Handles readTime '24:00' as end-of-day (midnight of next day) per
    common utility conventions, not start-of-day.
    """
    if read_time.strip() == "24:00":
        base = datetime.fromisoformat(f"{read_date}T00:00:00")
        end_of_day = base + timedelta(days=1)
        return arrow.get(end_of_day, tz).datetime
    time_str = read_time.replace("24", "00")
    return arrow.get(
        datetime.fromisoformat(f"{read_date}T{time_str}:00"),
        tz,
    ).datetime


def _parse_dollar(value: str | None) -> float | None:
    """Parse a dollar string like '$123.45' or '1,234.56' to float."""
    if not value:
        return None
    cleaned = value.strip().lstrip("$").replace(",", "")
    if not cleaned:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_iso_datetime(value: str | None) -> datetime | None:
    """Parse an ISO-8601 datetime string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


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
    "period_dropdown": [
        "mat-select[aria-label*='period']",
        "mat-select[aria-label*='Period']",
        "[aria-label*='period']",
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

    def __init__(self) -> None:
        self.user_id: str | None = None
        self.account: dict = {}
        self.accounts: list[dict] = []
        self.forecast: dict = {}
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

    def _on_response(self, response) -> None:
        """Capture XHR JSON responses."""
        if "json" in (response.headers.get("content-type", "")):
            try:
                try:
                    data = response.json()
                    self.xhrs[response.url] = json.dumps(data)
                except Exception:
                    self.xhrs[response.url] = response.text()
            except Exception as err:
                _LOGGER.debug("Failed to capture XHR response for %s: %s", response.url, err)

    def on_quit(self, *args, **kwargs) -> None:
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

    def init_browser(self) -> None:
        """Launch a headless Chromium browser."""
        if sync_playwright is None:
            raise CannotConnect(
                "Playwright is not installed in this environment. "
                "Use the Rocky Mountain Power sidecar service instead."
            )
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self._page.on("response", self._on_response)

    def _dismiss_overlays(self) -> None:
        """Dismiss common overlays/dialogs that block interaction."""
        page = self._page
        selectors = [
            "button:has-text('Close')",
            "button:has-text('No thanks')",
            "button:has-text('Maybe later')",
            "button:has-text('Remind me later')",
            "mat-dialog-container button:has-text('Close')",
            "mat-dialog-container button:has-text('Cancel')",
        ]
        for selector in selectors:
            try:
                btn = page.query_selector(selector)
                if btn and btn.is_visible():
                    _LOGGER.debug("Dismissing overlay with selector: %s", selector)
                    btn.click()
                    page.wait_for_timeout(500)
            except Exception:
                pass

    def login(self, username: str, password: str) -> dict[str, str]:
        """Navigate to the RMP login page, authenticate, and capture account data."""
        self.init_browser()
        page = self._page

        page.goto(self.LOGIN_URL)
        try:
            page.wait_for_function("document.title === 'Sign in'", timeout=30000)
        except PlaywrightTimeout as err:
            _LOGGER.error("Timed out waiting for login page to load")
            raise CannotConnect from err

        cookie_btn = self._query_selector_with_fallback(_SELECTORS["cookie_banner_btn"])
        if cookie_btn and cookie_btn.is_visible():
            cookie_btn.click()

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

        user_me_url = "https://csapps.rockymountainpower.net/api/user/me"
        account_list_url = "https://csapps.rockymountainpower.net/api/self-service/getAccountList"
        self._wait_for_xhr(user_me_url, timeout=15000)
        self._wait_for_xhr(account_list_url, timeout=15000)

        self._dismiss_overlays()

        if user_me_url not in self.xhrs or account_list_url not in self.xhrs:
            _LOGGER.error("Login succeeded but critical API responses were not captured")
            raise CannotConnect

        me = json.loads(self.xhrs[user_me_url])
        self.user_id = me["id"]
        accounts_data = json.loads(self.xhrs[account_list_url])

        if "getAccountListResponseBody" not in accounts_data:
            _LOGGER.error("Unexpected account list response: %s", json.dumps(accounts_data))
            raise CannotConnect("Account list response missing expected data")

        self.accounts = accounts_data["getAccountListResponseBody"]["accountList"]["webAccount"]
        self.account = self.accounts[0]
        return self.xhrs

    def switch_account(self, nickname: str) -> bool:
        """Switch to a different account using the account picker dropdown."""
        page = self._page
        picker = self._query_selector_with_fallback(_SELECTORS["account_picker"])
        if not picker:
            _LOGGER.warning("Account picker not found on page")
            return False

        picker.click()
        page.wait_for_timeout(1000)

        options = self._query_selector_all_with_fallback(_SELECTORS["dropdown_option"])
        for opt in options:
            text = opt.evaluate("el => el.textContent.trim()")
            if nickname in text:
                opt.click()
                acct_info_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"
                self.xhrs.clear()
                self._wait_for_xhr(acct_info_url, timeout=10000)
                return True

        _LOGGER.warning("Account '%s' not found in picker options", nickname)
        page.keyboard.press("Escape")
        return False

    def goto_energy_usage(self) -> None:
        """Navigate to the energy usage page."""
        page = self._page
        page.goto("https://csapps.rockymountainpower.net/secure/my-account/energy-usage")
        try:
            page.wait_for_function("document.title === 'Energy usage'", timeout=30000)
        except PlaywrightTimeout as err:
            _LOGGER.error("Timed out waiting for energy usage page")
            raise CannotConnect from err

    def goto_billing(self) -> None:
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
        """Get billing info from the account info XHR."""
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getAccountInfo"

        if xhr_url not in self.xhrs:
            self.goto_billing()
            self._wait_for_xhr(xhr_url, timeout=10000)

        if xhr_url in self.xhrs:
            details = json.loads(self.xhrs[xhr_url])
            return details.get("getAccountInfoResponseBody", {}).get("accountInfo", {})
        return None

    def get_forecast(self) -> dict:
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

    def _select_usage_option(
        self,
        labels: list[str] | None = None,
        fallback_index: int | None = None,
        prefer_last: bool = False,
    ) -> None:
        """Click the period dropdown and select an option by label or index."""
        page = self._page

        period_dropdown = self._query_selector_with_fallback(
            _SELECTORS.get("period_dropdown", [])
        )
        if not period_dropdown:
            for _ in range(40):
                dropdowns = self._query_selector_all_with_fallback(
                    _SELECTORS["usage_dropdown"]
                )
                if len(dropdowns) >= 2:
                    last_dropdown = dropdowns[-1]
                    try:
                        text = last_dropdown.inner_text().lower()
                        if "active" not in text and "business" not in text:
                            break
                    except Exception:
                        pass
                page.wait_for_timeout(500)

            if dropdowns:
                period_dropdown = dropdowns[-1]

        if not period_dropdown:
            _LOGGER.warning("No period dropdown found")
            return

        self._dismiss_overlays()

        period_dropdown.click()
        page.wait_for_timeout(1000)
        options = self._query_selector_all_with_fallback(_SELECTORS["usage_option"])
        if not options:
            _LOGGER.warning("No usage options found in dropdown")
            return

        if labels:
            matches = []
            for i, opt in enumerate(options):
                try:
                    text = (opt.evaluate("el => el.textContent?.trim() ?? ''") or "").lower()
                    _LOGGER.debug("Option %d: '%s'", i, text)
                    if any(label.lower() in text for label in labels):
                        matches.append(i)
                except Exception:
                    continue
            if matches:
                idx = matches[-1] if prefer_last else matches[0]
                options[idx].click()
                return

        if fallback_index is not None:
            idx = fallback_index if fallback_index >= 0 else len(options) + fallback_index
            if 0 <= idx < len(options):
                options[idx].click()
                return

        _LOGGER.warning(
            "Could not select usage option: no label match and fallback_index not set"
        )

    def _click_previous_button(self) -> bool:
        """Click the PREVIOUS button to go back one period."""
        prev_btn = self._query_selector_with_fallback(_SELECTORS["prev_button"])
        if not prev_btn:
            return False
        try:
            prev_btn.click()
            return True
        except Exception:
            _LOGGER.debug("Failed to click PREVIOUS button", exc_info=True)
            return False

    def get_usage_by_month(self) -> list[dict]:
        """Get monthly usage data from the energy usage page."""
        xhr_url = "https://csapps.rockymountainpower.net/api/account/getUsageHistoryAndGraphDataV1"
        self.goto_energy_usage()
        self._select_usage_option(
            labels=["One Month", "Month", "Monthly", "1 Month", "12 Months"],
            fallback_index=0,
        )
        self._wait_for_xhr(xhr_url)

        details = json.loads(self.xhrs.get(xhr_url, "{}"))
        usage: list[dict] = []
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

    def get_usage_by_day(self, months: int = 1) -> list[dict]:
        """Get daily usage data, paginating back the specified number of months."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getUsageForDateRange"
        self.goto_energy_usage()
        self._select_usage_option(
            labels=["One Day", "Daily"],
            fallback_index=2,
        )
        self._wait_for_xhr(xhr_url)

        usage: list[dict] = []
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

    def get_usage_by_interval(self, days: int = 1) -> list[dict]:
        """Get interval usage data (hourly or 15-minute), paginating back the specified number of days."""
        xhr_url = "https://csapps.rockymountainpower.net/api/energy-usage/getIntervalUsageForDate"
        self.goto_energy_usage()
        self._select_usage_option(
            labels=["One Day", "Hourly", "Interval"],
            fallback_index=-1,
            prefer_last=True,
        )
        self._wait_for_xhr(xhr_url)

        usage: list[dict] = []
        while days > 0:
            if xhr_url not in self.xhrs:
                break
            details = json.loads(self.xhrs[xhr_url])
            entries = (
                details
                .get("getIntervalUsageForDateResponseBody", {})
                .get("response", {})
                .get("intervalDataResponse", [])
            )
            interval = self._detect_interval(entries)
            for d in entries:
                end_time = _parse_interval_time(
                    d["readDate"], d["readTime"], self.TZ
                )
                start_time = end_time - interval
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

    @staticmethod
    def _detect_interval(entries: list[dict]) -> timedelta:
        """Detect the read interval from consecutive entries.

        Compares the first two readTime values to determine whether the meter
        reports at 15-minute or 1-hour (or other) granularity. Falls back to
        1 hour when there are fewer than two entries.
        """
        if len(entries) < 2:
            return timedelta(hours=1)

        tz = RockyMountainPowerUtility.TZ
        t1 = _parse_interval_time(entries[0]["readDate"], entries[0]["readTime"], tz)
        t2 = _parse_interval_time(entries[1]["readDate"], entries[1]["readTime"], tz)
        diff = t2 - t1

        if diff.total_seconds() > 0:
            return diff
        return timedelta(hours=1)
