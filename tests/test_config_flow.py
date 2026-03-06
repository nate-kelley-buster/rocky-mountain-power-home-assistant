"""Tests for the Rocky Mountain Power config flow."""
from unittest.mock import patch

import pytest

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.rocky_mountain_power.const import DOMAIN

from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable custom integrations for all tests in this module."""
    yield


async def test_user_flow_success(hass: HomeAssistant, recorder_mock) -> None:
    """Test a successful user config flow."""
    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={},
    ), patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Rocky Mountain Power (test@example.com)"
    assert result["data"] == {
        CONF_USERNAME: "test@example.com",
        CONF_PASSWORD: "secret",
    }


async def test_user_flow_invalid_auth(hass: HomeAssistant, recorder_mock) -> None:
    """Test user flow with invalid credentials."""
    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={"base": "invalid_auth"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(hass: HomeAssistant, recorder_mock) -> None:
    """Test user flow when service is unreachable."""
    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={"base": "cannot_connect"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_duplicate_entry(hass: HomeAssistant, recorder_mock) -> None:
    """Test that duplicate accounts are rejected."""
    existing = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
        unique_id="test@example.com",
    )
    existing.add_to_hass(hass)

    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_error_then_success(hass: HomeAssistant, recorder_mock) -> None:
    """Test recovery after an initial error."""
    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={"base": "invalid_auth"},
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "wrong"},
        )
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_auth"}

    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={},
    ), patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "correct"},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_reauth_flow_success(hass: HomeAssistant, recorder_mock) -> None:
    """Test a successful reauth flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "old_pass"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={},
    ), patch(
        "custom_components.rocky_mountain_power.coordinator.RockyMountainPowerCoordinator._async_update_data",
        return_value={},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "new_pass"},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new_pass"


async def test_reauth_flow_invalid_auth(hass: HomeAssistant, recorder_mock) -> None:
    """Test reauth flow with wrong password."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "old_pass"},
        unique_id="test@example.com",
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)

    with patch(
        "custom_components.rocky_mountain_power.config_flow._validate_login",
        return_value={"base": "invalid_auth"},
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {CONF_USERNAME: "test@example.com", CONF_PASSWORD: "still_wrong"},
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
