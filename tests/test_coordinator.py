"""Tests for the Rocky Mountain Power coordinator."""
from datetime import date, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.rocky_mountain_power.const import DOMAIN
from custom_components.rocky_mountain_power.coordinator import (
    RockyMountainPowerCoordinator,
)
from custom_components.rocky_mountain_power.rocky_mountain_power import (
    AccountInfo,
    CannotConnect,
    CostRead,
    InvalidAuth,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this module."""
    yield


@pytest.fixture
def mock_config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """Create and register a mock config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def coordinator(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> RockyMountainPowerCoordinator:
    """Create a coordinator instance with mocked API."""
    coord = RockyMountainPowerCoordinator(hass, mock_config_entry)
    coord.api = MagicMock()
    return coord


def _make_account_info(
    account_number: str = "1234567890",
    nickname: str = "Test Home",
    status: str = "Active",
) -> AccountInfo:
    """Create an AccountInfo for testing."""
    return AccountInfo(
        account_number=account_number,
        address="123 Test St",
        nickname=nickname,
        status=status,
        is_business=False,
        customer_idn=12345,
    )


async def test_update_raises_auth_failed_on_invalid_auth(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test that InvalidAuth during login raises ConfigEntryAuthFailed."""
    coordinator.api.login.side_effect = InvalidAuth("bad creds")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_update_raises_update_failed_on_cannot_connect(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test that CannotConnect during login raises UpdateFailed."""
    coordinator.api.login.side_effect = CannotConnect("no connection")

    with pytest.raises(UpdateFailed, match="Error during login"):
        await coordinator._async_update_data()


async def test_update_raises_update_failed_when_no_data(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test that empty results raise UpdateFailed."""
    coordinator.api.login.return_value = None
    coordinator.api.get_accounts.return_value = []

    with pytest.raises(UpdateFailed, match="No data received"):
        await coordinator._async_update_data()


async def test_update_success_single_account(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test successful data fetch for a single account."""
    acct = _make_account_info()
    coordinator.api.login.return_value = None
    coordinator.api.get_accounts.return_value = [acct]
    coordinator.api.switch_account.return_value = True
    coordinator.api.utility.accounts = [{"accountNumber": "1234567890"}]
    coordinator.api.account = {"accountNumber": "1234567890"}

    mock_forecast = MagicMock()
    mock_forecast.forecasted_cost = 170.0
    mock_forecast.forecasted_cost_low = 144.0
    mock_forecast.forecasted_cost_high = 195.0
    coordinator.api.get_forecast.return_value = [mock_forecast]

    mock_billing = MagicMock()
    mock_billing.current_balance = 115.59
    mock_billing.due_date = date(2026, 3, 23)
    mock_billing.past_due_amount = 0.0
    mock_billing.last_payment_amount = 119.93
    mock_billing.last_payment_date = date(2026, 2, 20)
    mock_billing.next_statement_date = date(2026, 3, 30)
    coordinator.api.get_billing_info.return_value = mock_billing

    mock_account = MagicMock()
    mock_account.uuid = "1234567890"
    mock_account.utility_account_id = "user-123"
    coordinator.api.get_account.return_value = mock_account
    coordinator.api.get_cost_reads.return_value = []

    with patch.object(coordinator, "_insert_statistics", new_callable=AsyncMock):
        result = await coordinator._async_update_data()

    assert "1234567890" in result
    assert result["1234567890"]["forecast"]["forecasted_cost"] == 170.0
    assert result["1234567890"]["billing"]["current_balance"] == 115.59
    assert result["1234567890"]["nickname"] == "Test Home"


async def test_update_skips_inactive_accounts(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test that inactive accounts are filtered out."""
    active = _make_account_info(account_number="111", status="Active")
    inactive = _make_account_info(account_number="222", status="Closed")

    coordinator.api.login.return_value = None
    coordinator.api.get_accounts.return_value = [active, inactive]
    coordinator.api.switch_account.return_value = True
    coordinator.api.utility.accounts = [{"accountNumber": "111"}]
    coordinator.api.account = {"accountNumber": "111"}
    coordinator.api.get_forecast.return_value = []
    coordinator.api.get_billing_info.return_value = None

    mock_account = MagicMock()
    mock_account.uuid = "111"
    coordinator.api.get_account.return_value = mock_account
    coordinator.api.get_cost_reads.return_value = []

    with patch.object(coordinator, "_insert_statistics", new_callable=AsyncMock):
        result = await coordinator._async_update_data()

    assert "111" in result
    assert "222" not in result


async def test_update_handles_failed_account_switch(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test that a failed account switch skips the account gracefully."""
    acct = _make_account_info()
    coordinator.api.login.return_value = None
    coordinator.api.get_accounts.return_value = [acct]
    coordinator.api.switch_account.return_value = False

    with pytest.raises(UpdateFailed, match="No data received"):
        await coordinator._async_update_data()


async def test_update_always_ends_session(
    coordinator: RockyMountainPowerCoordinator,
) -> None:
    """Test that the browser session is always cleaned up."""
    coordinator.api.login.return_value = None
    coordinator.api.get_accounts.side_effect = Exception("unexpected")

    with pytest.raises(Exception, match="unexpected"):
        await coordinator._async_update_data()

    coordinator.api.end_session.assert_called_once()


async def test_deduplicate_cost_reads() -> None:
    """Test that cost reads are deduplicated keeping finest granularity."""
    hourly = CostRead(
        start_time=datetime(2024, 1, 1, 0, 0),
        end_time=datetime(2024, 1, 1, 0, 59, 59),
        consumption=1.5,
        provided_cost=0.15,
    )
    daily = CostRead(
        start_time=datetime(2024, 1, 1, 0, 0),
        end_time=datetime(2024, 1, 1, 23, 59, 59),
        consumption=30.0,
        provided_cost=3.00,
    )

    result = RockyMountainPowerCoordinator._deduplicate_cost_reads([daily, hourly])
    assert len(result) == 1
    assert result[0].consumption == 1.5


async def test_deduplicate_preserves_non_overlapping() -> None:
    """Test that non-overlapping reads are all preserved."""
    read1 = CostRead(
        start_time=datetime(2024, 1, 1, 0, 0),
        end_time=datetime(2024, 1, 1, 0, 59, 59),
        consumption=1.0,
        provided_cost=0.10,
    )
    read2 = CostRead(
        start_time=datetime(2024, 1, 1, 1, 0),
        end_time=datetime(2024, 1, 1, 1, 59, 59),
        consumption=2.0,
        provided_cost=0.20,
    )

    result = RockyMountainPowerCoordinator._deduplicate_cost_reads([read1, read2])
    assert len(result) == 2
    assert result[0].start_time < result[1].start_time
