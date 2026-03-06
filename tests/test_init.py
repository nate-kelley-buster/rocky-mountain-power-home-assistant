"""Tests for Rocky Mountain Power integration setup and teardown."""
from datetime import date
from unittest.mock import patch

import pytest

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.rocky_mountain_power.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


def _mock_coordinator_data():
    """Return mock data matching the coordinator's output format."""
    return {
        "1234567890": {
            "nickname": "Test Home",
            "forecast": {
                "forecasted_cost": 170.0,
                "forecasted_cost_low": 144.0,
                "forecasted_cost_high": 195.0,
            },
            "billing": {
                "current_balance": 115.59,
                "due_date": date(2026, 3, 23),
                "past_due_amount": 0.0,
                "last_payment_amount": 119.93,
                "last_payment_date": date(2026, 2, 20),
                "next_statement_date": date(2026, 3, 30),
            },
        }
    }


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this module."""
    yield


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Create a mock config entry."""
    return MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
        unique_id="test@example.com",
    )


async def test_setup_entry_success(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test successful setup of a config entry."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        return_value=_mock_coordinator_data(),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert mock_config_entry.runtime_data is not None


async def test_setup_entry_auth_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test setup failure due to invalid credentials triggers reauth."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        side_effect=ConfigEntryAuthFailed("Invalid credentials"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_connection_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test setup failure due to connection issues retries later."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        side_effect=UpdateFailed("Connection failed"),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_unload_entry(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test unloading a config entry."""
    mock_config_entry.add_to_hass(hass)

    with patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        return_value=_mock_coordinator_data(),
    ):
        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.LOADED

    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
