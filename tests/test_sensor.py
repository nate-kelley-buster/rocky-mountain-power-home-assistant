"""Tests for Rocky Mountain Power sensor entities."""
from datetime import date
from unittest.mock import patch

import pytest

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.rocky_mountain_power.const import (
    CONF_SIDECAR_API_TOKEN,
    CONF_SIDECAR_BASE_URL,
    DEFAULT_SIDECAR_BASE_URL,
    DOMAIN,
)
from custom_components.rocky_mountain_power.sensor import ALL_SENSORS

from pytest_homeassistant_custom_component.common import MockConfigEntry


MOCK_DATA = {
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
        data={
            CONF_USERNAME: "test@example.com",
            CONF_PASSWORD: "secret",
            CONF_SIDECAR_BASE_URL: DEFAULT_SIDECAR_BASE_URL,
            CONF_SIDECAR_API_TOKEN: "",
        },
        unique_id="test@example.com",
    )


async def _setup_integration(
    hass: HomeAssistant, entry: MockConfigEntry
) -> None:
    """Set up the integration with mock data."""
    entry.add_to_hass(hass)
    with patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        return_value=MOCK_DATA,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()


async def test_sensor_entities_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test that all expected sensor entities are created."""
    await _setup_integration(hass, mock_config_entry)

    entity_registry = er.async_get(hass)
    entities = [
        entry
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN
    ]
    assert len(entities) == len(ALL_SENSORS)


async def test_forecast_sensor_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test that forecast sensor values are correct."""
    await _setup_integration(hass, mock_config_entry)

    states = hass.states.async_all("sensor")
    rmp_states = {s.entity_id: s for s in states if DOMAIN in s.entity_id}

    forecasted = [s for eid, s in rmp_states.items() if "forecasted_cost" in eid and "low" not in eid and "high" not in eid]
    assert len(forecasted) == 1
    assert float(forecasted[0].state) == 170.0

    low = [s for eid, s in rmp_states.items() if "forecasted_cost_low" in eid]
    assert len(low) == 1
    assert float(low[0].state) == 144.0

    high = [s for eid, s in rmp_states.items() if "forecasted_cost_high" in eid]
    assert len(high) == 1
    assert float(high[0].state) == 195.0


async def test_billing_sensor_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test that billing sensor values are correct."""
    await _setup_integration(hass, mock_config_entry)

    states = hass.states.async_all("sensor")
    rmp_states = {s.entity_id: s for s in states if DOMAIN in s.entity_id}

    balance = [s for eid, s in rmp_states.items() if "current_balance" in eid]
    assert len(balance) == 1
    assert float(balance[0].state) == 115.59

    past_due = [s for eid, s in rmp_states.items() if "past_due" in eid]
    assert len(past_due) == 1
    assert float(past_due[0].state) == 0.0

    last_pay = [s for eid, s in rmp_states.items() if "last_payment_amount" in eid]
    assert len(last_pay) == 1
    assert float(last_pay[0].state) == 119.93


async def test_date_sensor_values(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test that date sensor values are correct."""
    await _setup_integration(hass, mock_config_entry)

    states = hass.states.async_all("sensor")
    rmp_states = {s.entity_id: s for s in states if DOMAIN in s.entity_id}

    due_date = [s for eid, s in rmp_states.items() if "due_date" in eid]
    assert len(due_date) == 1
    assert due_date[0].state == "2026-03-23"

    last_pay_date = [s for eid, s in rmp_states.items() if "last_payment_date" in eid]
    assert len(last_pay_date) == 1
    assert last_pay_date[0].state == "2026-02-20"

    next_stmt = [s for eid, s in rmp_states.items() if "next_statement_date" in eid]
    assert len(next_stmt) == 1
    assert next_stmt[0].state == "2026-03-30"


async def test_sensor_unique_ids(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test that each sensor has a unique ID."""
    await _setup_integration(hass, mock_config_entry)

    entity_registry = er.async_get(hass)
    unique_ids = [
        entry.unique_id
        for entry in entity_registry.entities.values()
        if entry.platform == DOMAIN
    ]
    assert len(unique_ids) == len(set(unique_ids))
    for uid in unique_ids:
        assert uid.startswith("rocky_mountain_power_1234567890_")


async def test_sensor_device_info(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    recorder_mock,
) -> None:
    """Test that sensors are grouped under the correct device."""
    await _setup_integration(hass, mock_config_entry)

    device_registry = dr.async_get(hass)
    devices = [
        device
        for device in device_registry.devices.values()
        if any(DOMAIN in identifier[0] for identifier in device.identifiers)
    ]
    assert len(devices) == 1
    device = devices[0]
    assert device.manufacturer == "Rocky Mountain Power"
    assert "Test Home" in device.name
