"""HTTP sidecar for Rocky Mountain Power Playwright scraping."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
from enum import Enum
import os
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException

from custom_components.rocky_mountain_power.client import RockyMountainPower
from custom_components.rocky_mountain_power.exceptions import CannotConnect, InvalidAuth
from custom_components.rocky_mountain_power.models import AggregateType

app = FastAPI(title="Rocky Mountain Power Sidecar")

_SESSIONS: dict[str, RockyMountainPower] = {}
_API_TOKEN = os.getenv("RMP_SIDECAR_API_TOKEN")


def _serialize(value: Any) -> Any:
    """Serialize dataclasses and datetime values into JSON-safe values."""
    if dataclasses.is_dataclass(value):
        return _serialize(dataclasses.asdict(value))
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_serialize(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _authorize(x_api_token: str | None) -> None:
    """Validate the optional sidecar API token."""
    if _API_TOKEN and x_api_token != _API_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid sidecar API token")


def _get_session(session_id: str) -> RockyMountainPower:
    """Return a stored scraping session."""
    session = _SESSIONS.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


def _resolve_aggregate_type(aggregate: str) -> AggregateType:
    """Convert an aggregate string into an AggregateType."""
    try:
        return AggregateType(aggregate)
    except ValueError as err:
        raise HTTPException(status_code=400, detail="Invalid aggregate type") from err


def _ensure_account_selected(api: RockyMountainPower, account_number: str | None) -> None:
    """Select the requested account when provided."""
    if account_number and not api.switch_account(account_number):
        raise HTTPException(status_code=404, detail="Account not found")


def _handle_upstream_error(err: Exception) -> None:
    """Translate scraper exceptions into HTTP errors."""
    if isinstance(err, InvalidAuth):
        raise HTTPException(status_code=401, detail=str(err) or "Invalid auth") from err
    if isinstance(err, CannotConnect):
        raise HTTPException(
            status_code=503, detail=str(err) or "Unable to connect upstream"
        ) from err
    raise HTTPException(status_code=500, detail=str(err) or "Unexpected error") from err


@app.get("/health")
def health() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.post("/session/login")
def login(
    payload: dict[str, Any],
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Create a new scraping session."""
    _authorize(x_api_token)
    api = RockyMountainPower(payload["username"], payload["password"])
    try:
        api.login()
        session_id = uuid4().hex
        _SESSIONS[session_id] = api
        accounts = api.get_accounts()
        active_account_number = api.account.get("accountNumber")
        return {
            "session_id": session_id,
            "user_id": api.customer_id,
            "accounts": _serialize(accounts),
            "active_account_number": active_account_number,
        }
    except Exception as err:  # noqa: BLE001
        api.end_session()
        _handle_upstream_error(err)


@app.delete("/session/{session_id}")
def end_session(
    session_id: str,
    x_api_token: str | None = Header(default=None),
) -> dict[str, bool]:
    """Close a scraping session."""
    _authorize(x_api_token)
    api = _SESSIONS.pop(session_id, None)
    if api is not None:
        api.end_session()
    return {"closed": True}


@app.get("/session/{session_id}/accounts")
def get_accounts(
    session_id: str,
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return all discovered accounts for the session."""
    _authorize(x_api_token)
    api = _get_session(session_id)
    try:
        accounts = api.get_accounts()
        return {
            "accounts": _serialize(accounts),
            "active_account_number": api.account.get("accountNumber"),
        }
    except Exception as err:  # noqa: BLE001
        _handle_upstream_error(err)


@app.post("/session/{session_id}/account/select")
def select_account(
    session_id: str,
    payload: dict[str, Any],
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Select the current account for subsequent requests."""
    _authorize(x_api_token)
    api = _get_session(session_id)
    account_number = payload.get("account_number")
    if not account_number:
        raise HTTPException(status_code=400, detail="account_number is required")
    try:
        if not api.switch_account(account_number):
            raise HTTPException(status_code=404, detail="Account not found")
        return {"selected_account_number": api.account.get("accountNumber")}
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        _handle_upstream_error(err)


@app.get("/session/{session_id}/forecast")
def get_forecast(
    session_id: str,
    account_number: str | None = None,
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return forecast data for an account."""
    _authorize(x_api_token)
    api = _get_session(session_id)
    try:
        _ensure_account_selected(api, account_number)
        return {"forecasts": _serialize(api.get_forecast())}
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        _handle_upstream_error(err)


@app.get("/session/{session_id}/billing")
def get_billing(
    session_id: str,
    account_number: str | None = None,
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return billing data for an account."""
    _authorize(x_api_token)
    api = _get_session(session_id)
    try:
        _ensure_account_selected(api, account_number)
        return {"billing": _serialize(api.get_billing_info())}
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        _handle_upstream_error(err)


@app.get("/session/{session_id}/cost-reads")
def get_cost_reads(
    session_id: str,
    aggregate: str,
    account_number: str | None = None,
    period: int = 1,
    x_api_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """Return cost reads for an account."""
    _authorize(x_api_token)
    api = _get_session(session_id)
    try:
        _ensure_account_selected(api, account_number)
        reads = api.get_cost_reads(_resolve_aggregate_type(aggregate), period)
        return {"reads": _serialize(reads)}
    except HTTPException:
        raise
    except Exception as err:  # noqa: BLE001
        _handle_upstream_error(err)
