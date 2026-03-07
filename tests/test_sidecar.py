"""Tests for the Rocky Mountain Power sidecar client and app."""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from custom_components.rocky_mountain_power.const import DEFAULT_SIDECAR_BASE_URL
from custom_components.rocky_mountain_power.client import RockyMountainPower
from custom_components.rocky_mountain_power.models import (
    AccountInfo,
    AggregateType,
    CostRead,
)
from sidecar.app import _SESSIONS, app


def test_sidecar_client_login_stores_session_metadata() -> None:
    """Test that the sidecar client stores session/login state."""
    api = RockyMountainPower(
        "user@example.com",
        "secret",
        DEFAULT_SIDECAR_BASE_URL,
        "token-123",
    )

    with patch.object(
        api,
        "_sidecar_request",
        return_value={
            "session_id": "session-1",
            "user_id": "customer-1",
            "active_account_number": "1234567890",
            "accounts": [
                {
                    "account_number": "1234567890",
                    "address": "123 Test St",
                    "nickname": "Test Home",
                    "status": "Active",
                    "is_business": False,
                    "customer_idn": 123,
                }
            ],
        },
    ) as mock_request:
        api.login()

    mock_request.assert_called_once()
    assert api.customer_id == "customer-1"
    assert api.account == {"accountNumber": "1234567890"}
    assert api.get_accounts() == [
        AccountInfo(
            account_number="1234567890",
            address="123 Test St",
            nickname="Test Home",
            status="Active",
            is_business=False,
            customer_idn=123,
        )
    ]


def test_sidecar_client_deserializes_cost_reads() -> None:
    """Test cost read deserialization from the sidecar."""
    api = RockyMountainPower("user@example.com", "secret", DEFAULT_SIDECAR_BASE_URL)
    api._session_id = "session-1"
    api.customer_id = "customer-1"
    api.account = {"accountNumber": "1234567890"}

    with patch.object(
        api,
        "_sidecar_request",
        return_value={
            "reads": [
                {
                    "start_time": "2024-01-01T00:00:00",
                    "end_time": "2024-01-01T00:59:59",
                    "consumption": 1.5,
                    "provided_cost": 0.15,
                }
            ]
        },
    ):
        reads = api.get_cost_reads(AggregateType.HOUR, 1)

    assert reads == [
        CostRead(
            start_time=datetime(2024, 1, 1, 0, 0, 0),
            end_time=datetime(2024, 1, 1, 0, 59, 59),
            consumption=1.5,
            provided_cost=0.15,
        )
    ]


def test_sidecar_health_endpoint() -> None:
    """Test the sidecar health endpoint."""
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_sidecar_login_and_end_session() -> None:
    """Test creating and closing a sidecar session."""
    _SESSIONS.clear()
    client = TestClient(app)

    mock_api = MagicMock()
    mock_api.customer_id = "customer-1"
    mock_api.account = {"accountNumber": "1234567890"}
    mock_api.get_accounts.return_value = [
        AccountInfo(
            account_number="1234567890",
            address="123 Test St",
            nickname="Test Home",
            status="Active",
            is_business=False,
            customer_idn=123,
        )
    ]

    with patch("sidecar.app.RockyMountainPower", return_value=mock_api):
        response = client.post(
            "/session/login",
            json={"username": "user@example.com", "password": "secret"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "customer-1"
    assert body["active_account_number"] == "1234567890"
    assert len(_SESSIONS) == 1

    session_id = body["session_id"]
    close_response = client.delete(f"/session/{session_id}")
    assert close_response.status_code == 200
    assert close_response.json() == {"closed": True}
    mock_api.end_session.assert_called_once()
    assert _SESSIONS == {}
