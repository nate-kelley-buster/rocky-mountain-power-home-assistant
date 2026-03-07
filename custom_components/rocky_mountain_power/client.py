"""High-level Rocky Mountain Power client with sidecar and local Playwright support."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .exceptions import CannotConnect, InvalidAuth
from .models import (
    Account,
    AccountInfo,
    AggregateType,
    BillingInfo,
    CostRead,
    Customer,
    Forecast,
)
from .scraper import RockyMountainPowerUtility, _parse_iso_datetime

_LOGGER = logging.getLogger(__name__)


class RockyMountainPower:
    """Class that can get historical and forecasted usage/cost from Rocky Mountain Power."""

    def __init__(
        self,
        username: str,
        password: str,
        sidecar_base_url: str | None = None,
    ) -> None:
        """Initialize."""
        self._username: str = username
        self._password: str = password
        self._sidecar_base_url = sidecar_base_url.rstrip("/") if sidecar_base_url else None
        self._session_id: str | None = None
        self._accounts_cache: list[dict[str, Any]] = []
        self.account: dict = {}
        self.customer_id: str | None = None
        self.utility: RockyMountainPowerUtility | None = (
            None if self._sidecar_base_url else RockyMountainPowerUtility()
        )

    @property
    def _uses_sidecar(self) -> bool:
        """Return True when configured to use an external sidecar service."""
        return self._sidecar_base_url is not None

    def _sidecar_headers(self) -> dict[str, str]:
        """Build sidecar request headers."""
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _sidecar_request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Call the sidecar API and return JSON."""
        if not self._sidecar_base_url:
            raise CannotConnect("Sidecar base URL is not configured")

        url = f"{self._sidecar_base_url}{path}"
        if query:
            query_string = urlencode(
                {key: value for key, value in query.items() if value is not None}
            )
            if query_string:
                url = f"{url}?{query_string}"

        data = None
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")

        request = Request(url, data=data, method=method, headers=self._sidecar_headers())
        try:
            with urlopen(request, timeout=60) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else {}
        except HTTPError as err:
            detail = err.reason
            try:
                error_body = err.read().decode("utf-8")
                parsed = json.loads(error_body) if error_body else {}
                detail = (
                    parsed.get("detail")
                    or parsed.get("error")
                    or parsed.get("message")
                    or detail
                )
            except Exception:
                pass
            if err.code == 401:
                raise InvalidAuth(detail) from err
            raise CannotConnect(detail) from err
        except (URLError, TimeoutError) as err:
            raise CannotConnect(str(err)) from err

    def _ensure_logged_in(self) -> None:
        """Ensure the client has an active session."""
        if self._uses_sidecar:
            if not self._session_id:
                self.login()
            return

        if self.utility is None:
            self.utility = RockyMountainPowerUtility()
        if self.utility.user_id is None:
            self.login()

    def _get_current_account_number(self) -> str:
        """Return the currently selected account number."""
        account_number = self.account.get("accountNumber")
        if account_number:
            return account_number

        if self._uses_sidecar and self._accounts_cache:
            account_number = self._accounts_cache[0]["account_number"]
            self.account = {"accountNumber": account_number}
            return account_number

        account = self._get_account()
        return account["accountNumber"]

    def _deserialize_account(self, payload: dict[str, Any]) -> Account:
        """Deserialize an account payload from the sidecar."""
        customer_payload = payload.get("customer", {})
        return Account(
            customer=Customer(uuid=customer_payload.get("uuid", self.customer_id or "")),
            uuid=payload["uuid"],
            utility_account_id=payload["utility_account_id"],
        )

    def _deserialize_forecast(self, payload: dict[str, Any]) -> Forecast:
        """Deserialize a forecast payload from the sidecar."""
        return Forecast(
            account=self._deserialize_account(payload["account"]),
            start_date=date.fromisoformat(payload["start_date"][:10]) if payload.get("start_date") else date.today(),
            end_date=date.fromisoformat(payload["end_date"][:10]) if payload.get("end_date") else date.today(),
            current_date=date.fromisoformat(payload["current_date"][:10]) if payload.get("current_date") else date.today(),
            forecasted_cost=float(payload.get("forecasted_cost", 0)),
            forecasted_cost_low=float(payload.get("forecasted_cost_low", 0)),
            forecasted_cost_high=float(payload.get("forecasted_cost_high", 0)),
        )

    def _deserialize_billing(self, payload: dict[str, Any]) -> BillingInfo:
        """Deserialize a billing payload from the sidecar."""
        due_date = (
            date.fromisoformat(payload["due_date"])
            if payload.get("due_date")
            else None
        )
        last_payment_date = (
            date.fromisoformat(payload["last_payment_date"])
            if payload.get("last_payment_date")
            else None
        )
        next_statement_date = (
            date.fromisoformat(payload["next_statement_date"])
            if payload.get("next_statement_date")
            else None
        )
        return BillingInfo(
            account=self._deserialize_account(payload["account"]),
            current_balance=float(payload.get("current_balance", 0)),
            due_date=due_date,
            past_due_amount=float(payload.get("past_due_amount", 0)),
            last_payment_amount=float(payload.get("last_payment_amount", 0)),
            last_payment_date=last_payment_date,
            next_statement_date=next_statement_date,
            enrolled_payment_program=payload.get("enrolled_payment_program"),
        )

    def _deserialize_cost_read(self, payload: dict[str, Any]) -> CostRead:
        """Deserialize a cost read payload from the sidecar."""
        start_time = _parse_iso_datetime(payload["start_time"])
        end_time = _parse_iso_datetime(payload["end_time"])
        if start_time is None or end_time is None:
            raise ValueError("Cost read payload contained invalid datetimes")
        return CostRead(
            start_time=start_time,
            end_time=end_time,
            consumption=float(payload.get("consumption", 0)),
            provided_cost=float(payload.get("provided_cost", 0)),
        )

    def login(self) -> None:
        """Login to the utility website."""
        if self._uses_sidecar:
            payload = self._sidecar_request(
                "POST",
                "/session/login",
                payload={"username": self._username, "password": self._password},
            )
            self._session_id = payload["session_id"]
            self.customer_id = payload["user_id"]
            self._accounts_cache = payload.get("accounts", [])
            active_account_number = payload.get("active_account_number")
            if active_account_number:
                self.account = {"accountNumber": active_account_number}
            elif self._accounts_cache:
                self.account = {
                    "accountNumber": self._accounts_cache[0]["account_number"]
                }
            return

        if self.utility is None:
            self.utility = RockyMountainPowerUtility()
        self.utility.login(self._username, self._password)
        if not self.account:
            self.account = self.utility.account
        if not self.customer_id:
            self.customer_id = self.utility.user_id

    def end_session(self) -> None:
        """Close the browser and clean up resources."""
        if self._uses_sidecar:
            if self._session_id:
                try:
                    self._sidecar_request(
                        "DELETE", f"/session/{self._session_id}"
                    )
                except CannotConnect:
                    _LOGGER.debug("Failed to close sidecar session", exc_info=True)
            self._session_id = None
            self._accounts_cache = []
            return

        if self.utility is not None:
            self.utility.on_quit()

    def get_accounts(self) -> list[AccountInfo]:
        """Get all accounts for the signed in user."""
        if self._uses_sidecar:
            self._ensure_logged_in()
            if self._accounts_cache:
                return [AccountInfo(**acct) for acct in self._accounts_cache]
            if self._session_id is None:
                raise CannotConnect("No active sidecar session")
            payload = self._sidecar_request("GET", f"/session/{self._session_id}/accounts")
            self._accounts_cache = payload.get("accounts", [])
            return [AccountInfo(**acct) for acct in self._accounts_cache]

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
        if self._uses_sidecar:
            account_number = self._get_current_account_number()
            return Account(
                customer=Customer(uuid=self.customer_id or ""),
                uuid=account_number,
                utility_account_id=self.customer_id or "",
            )

        account = self._get_account()
        return Account(
            customer=Customer(uuid=self.customer_id),
            uuid=account["accountNumber"],
            utility_account_id=self.customer_id,
        )

    def get_forecast(self) -> list[Forecast]:
        """Get current and forecasted usage and cost for the current monthly bill."""
        if self._uses_sidecar:
            self._ensure_logged_in()
            if self._session_id is None:
                raise CannotConnect("No active sidecar session")
            payload = self._sidecar_request(
                "GET",
                f"/session/{self._session_id}/forecast",
                query={"account_number": self._get_current_account_number()},
            )
            return [
                self._deserialize_forecast(item)
                for item in payload.get("forecasts", [])
            ]

        forecasts: list[Forecast] = []
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
                    start_date=date.fromisoformat(forecast["startDateForAMIAcctView"]),
                    end_date=date.fromisoformat(forecast["endDateForAMIAcctView"]),
                    current_date=date.today(),
                    forecasted_cost=float(forecast.get("projectedCost", 0)),
                    forecasted_cost_low=float(forecast.get("projectedCostLow", 0)),
                    forecasted_cost_high=float(forecast.get("projectedCostHigh", 0)),
                )
            )
        return forecasts

    def get_billing_info(self) -> BillingInfo | None:
        """Get billing and payment info for the active account."""
        if self._uses_sidecar:
            self._ensure_logged_in()
            if self._session_id is None:
                raise CannotConnect("No active sidecar session")
            payload = self._sidecar_request(
                "GET",
                f"/session/{self._session_id}/billing",
                query={"account_number": self._get_current_account_number()},
            )
            billing_payload = payload.get("billing")
            if billing_payload is None:
                return None
            return self._deserialize_billing(billing_payload)

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
        if self._uses_sidecar:
            self._ensure_logged_in()
            match = next(
                (
                    acct
                    for acct in self._accounts_cache
                    if acct["account_number"] == nickname or acct["nickname"] == nickname
                ),
                None,
            )
            if match is None:
                return False
            if self._session_id is None:
                raise CannotConnect("No active sidecar session")
            self._sidecar_request(
                "POST",
                f"/session/{self._session_id}/account/select",
                payload={"account_number": match["account_number"]},
            )
            self.account = {"accountNumber": match["account_number"]}
            return True

        match = next(
            (
                acct
                for acct in self.utility.accounts
                if acct.get("accountNumber") == nickname
                or acct.get("accountNickname", "").strip() == nickname
            ),
            None,
        )
        switch_target = (
            match.get("accountNickname", "").strip()
            if match is not None
            else nickname
        )
        switched = self.utility.switch_account(switch_target)
        if switched and match is not None:
            self.account = match
        return switched

    def _get_account(self) -> dict:
        """Get account associated with the user, logging in if needed."""
        if not self.account:
            self.login()
            if not self._uses_sidecar:
                self.account = self.utility.account
        if not self.account:
            raise CannotConnect("No account data available after login")
        return self.account

    def get_cost_reads(
        self,
        aggregate_type: AggregateType,
        period: int | None = 1,
    ) -> list[CostRead]:
        """Get usage and cost data aggregated by month/day/hour."""
        if self._uses_sidecar:
            self._ensure_logged_in()
            if self._session_id is None:
                raise CannotConnect("No active sidecar session")
            payload = self._sidecar_request(
                "GET",
                f"/session/{self._session_id}/cost-reads",
                query={
                    "account_number": self._get_current_account_number(),
                    "aggregate": aggregate_type.value,
                    "period": period,
                },
            )
            reads = [
                self._deserialize_cost_read(item)
                for item in payload.get("reads", [])
            ]
            reads.sort(key=lambda read: read.start_time)
            return reads

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
        period: int | None = 1,
    ) -> list[dict]:
        """Dispatch to the correct usage method based on aggregate type."""
        if aggregate_type == AggregateType.MONTH:
            return self.utility.get_usage_by_month()
        elif aggregate_type == AggregateType.DAY:
            return self.utility.get_usage_by_day(months=period)
        elif aggregate_type == AggregateType.HOUR:
            return self.utility.get_usage_by_interval(days=period)
        else:
            raise ValueError(f"aggregate_type {aggregate_type} is not valid")
