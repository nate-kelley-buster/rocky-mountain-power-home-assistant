"""Support for Rocky Mountain Power sensors."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RockyMountainPowerCoordinator


@dataclass
class RockyMountainPowerEntityDescriptionMixin:
    """Mixin values for required keys."""

    value_fn: Callable[[dict], StateType]


@dataclass
class RockyMountainPowerEntityDescription(SensorEntityDescription, RockyMountainPowerEntityDescriptionMixin):
    """Class describing Rocky Mountain Power sensors entities."""


# suggested_display_precision=0 for forecast sensors since
# Rocky Mountain Power provides 0 decimal points for these.
FORECAST_SENSORS: tuple[RockyMountainPowerEntityDescription, ...] = (
    RockyMountainPowerEntityDescription(
        key="elec_forecasted_cost",
        name="Current bill forecasted cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("forecast", {}).get("forecasted_cost"),
    ),
    RockyMountainPowerEntityDescription(
        key="elec_forecasted_cost_low",
        name="Current bill forecasted cost low",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("forecast", {}).get("forecasted_cost_low"),
    ),
    RockyMountainPowerEntityDescription(
        key="elec_forecasted_cost_high",
        name="Current bill forecasted cost high",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        value_fn=lambda data: data.get("forecast", {}).get("forecasted_cost_high"),
    ),
)

BILLING_SENSORS: tuple[RockyMountainPowerEntityDescription, ...] = (
    RockyMountainPowerEntityDescription(
        key="current_balance",
        name="Current balance due",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("billing", {}).get("current_balance"),
    ),
    RockyMountainPowerEntityDescription(
        key="due_date",
        name="Payment due date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: data.get("billing", {}).get("due_date"),
    ),
    RockyMountainPowerEntityDescription(
        key="past_due_amount",
        name="Past due amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=2,
        value_fn=lambda data: data.get("billing", {}).get("past_due_amount"),
    ),
    RockyMountainPowerEntityDescription(
        key="last_payment_amount",
        name="Last payment amount",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="USD",
        suggested_display_precision=2,
        value_fn=lambda data: data.get("billing", {}).get("last_payment_amount"),
    ),
    RockyMountainPowerEntityDescription(
        key="last_payment_date",
        name="Last payment date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: data.get("billing", {}).get("last_payment_date"),
    ),
    RockyMountainPowerEntityDescription(
        key="next_statement_date",
        name="Next statement date",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data: data.get("billing", {}).get("next_statement_date"),
    ),
)

ALL_SENSORS = FORECAST_SENSORS + BILLING_SENSORS


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Rocky Mountain Power sensor."""

    coordinator: RockyMountainPowerCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[RockyMountainPowerSensor] = []

    for account_number, account_data in coordinator.data.items():
        nickname = account_data.get("nickname", account_number)
        device_id = f"rocky_mountain_power_{account_number}".replace(" ", "_")
        device = DeviceInfo(
            identifiers={(DOMAIN, device_id)},
            name=f"Rocky Mountain Power - {nickname}",
            manufacturer="Rocky Mountain Power",
            model="Electric Account",
            entry_type=DeviceEntryType.SERVICE,
        )
        for sensor in ALL_SENSORS:
            entities.append(
                RockyMountainPowerSensor(
                    coordinator,
                    sensor,
                    account_number,
                    device,
                    device_id,
                )
            )

    async_add_entities(entities)


class RockyMountainPowerSensor(CoordinatorEntity[RockyMountainPowerCoordinator], SensorEntity):
    """Representation of a Rocky Mountain Power sensor."""

    entity_description: RockyMountainPowerEntityDescription

    def __init__(
        self,
        coordinator: RockyMountainPowerCoordinator,
        description: RockyMountainPowerEntityDescription,
        account_number: str,
        device: DeviceInfo,
        device_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{device_id}_{description.key}"
        self._attr_device_info = device
        self.account_number = account_number

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        if self.coordinator.data and self.account_number in self.coordinator.data:
            return self.entity_description.value_fn(
                self.coordinator.data[self.account_number]
            )
        return None
