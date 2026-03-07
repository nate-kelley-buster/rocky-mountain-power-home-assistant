"""Config flow for Rocky Mountain Power integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback

from .const import (
    CONF_SIDECAR_API_TOKEN,
    CONF_SIDECAR_BASE_URL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_SIDECAR_BASE_URL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .client import RockyMountainPower
from .exceptions import CannotConnect, InvalidAuth

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(
            CONF_SIDECAR_BASE_URL, default=DEFAULT_SIDECAR_BASE_URL
        ): str,
        vol.Optional(CONF_SIDECAR_API_TOKEN, default=""): str,
    }
)


def _validate_login(login_data: dict[str, str]) -> dict[str, str]:
    """Validate login data and return any errors."""
    api = RockyMountainPower(
        login_data[CONF_USERNAME],
        login_data[CONF_PASSWORD],
        login_data[CONF_SIDECAR_BASE_URL],
        login_data.get(CONF_SIDECAR_API_TOKEN) or None,
    )
    errors: dict[str, str] = {}
    try:
        api.login()
    except InvalidAuth:
        errors["base"] = "invalid_auth"
    except CannotConnect:
        errors["base"] = "cannot_connect"
    finally:
        api.end_session()
    return errors


class RockyMountainPowerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RockyMountainPower."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry,
    ) -> RockyMountainPowerOptionsFlow:
        """Get the options flow handler."""
        return RockyMountainPowerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME])
            self._abort_if_unique_id_configured()

            errors = await self.hass.async_add_executor_job(_validate_login, user_input)
            if not errors:
                return self._async_create_entry(user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

    @callback
    def _async_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create the config entry."""
        return self.async_create_entry(
            title=f"Rocky Mountain Power ({data[CONF_USERNAME]})",
            data=data,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle configuration by re-auth."""
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): self._get_reauth_entry().data[CONF_USERNAME],
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(
                        CONF_SIDECAR_BASE_URL,
                        default=self._get_reauth_entry().data.get(
                            CONF_SIDECAR_BASE_URL, DEFAULT_SIDECAR_BASE_URL
                        ),
                    ): str,
                    vol.Optional(
                        CONF_SIDECAR_API_TOKEN,
                        default=self._get_reauth_entry().data.get(
                            CONF_SIDECAR_API_TOKEN, ""
                        ),
                    ): str,
                }
            ),
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            data = {**reauth_entry.data, **user_input}
            errors = await self.hass.async_add_executor_job(_validate_login, data)
            if not errors:
                return self.async_update_reload_and_abort(reauth_entry, data=data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): reauth_entry.data[CONF_USERNAME],
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(
                        CONF_SIDECAR_BASE_URL,
                        default=reauth_entry.data.get(
                            CONF_SIDECAR_BASE_URL, DEFAULT_SIDECAR_BASE_URL
                        ),
                    ): str,
                    vol.Optional(
                        CONF_SIDECAR_API_TOKEN,
                        default=reauth_entry.data.get(CONF_SIDECAR_API_TOKEN, ""),
                    ): str,
                }
            ),
            errors=errors,
        )


class RockyMountainPowerOptionsFlow(OptionsFlow):
    """Handle options for Rocky Mountain Power."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage integration options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL, default=current
                    ): vol.In({1: "1 hour", 2: "2 hours", 4: "4 hours", 6: "6 hours", 8: "8 hours", 12: "12 hours", 24: "24 hours"}),
                }
            ),
        )
