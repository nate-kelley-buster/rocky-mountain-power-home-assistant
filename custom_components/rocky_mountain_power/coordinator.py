"""Coordinator to handle Rocky Mountain Power connections."""
from datetime import timedelta
import json
import logging
from typing import Any, cast

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
    statistics_during_period,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, UnitOfEnergy
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.unit_conversion import EnergyConverter

from .const import CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL, DOMAIN
from .rocky_mountain_power import (
    AggregateType,
    CannotConnect,
    CostRead,
    InvalidAuth,
    RockyMountainPower,
)

_LOGGER = logging.getLogger(__name__)

type RMPConfigEntry = ConfigEntry[RockyMountainPowerCoordinator]


class RockyMountainPowerCoordinator(DataUpdateCoordinator[dict[str, dict]]):
    """Handle fetching Rocky Mountain Power data, updating sensors and inserting statistics."""

    config_entry: RMPConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: RMPConfigEntry,
    ) -> None:
        """Initialize the data handler."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Rocky Mountain Power",
            update_interval=timedelta(
                hours=config_entry.options.get(
                    CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                )
            ),
        )
        self.api = RockyMountainPower(
            config_entry.data[CONF_USERNAME],
            config_entry.data[CONF_PASSWORD],
        )

        # Force periodic updates even when no sensors are registered (e.g.,
        # accounts with no forecast data). Statistics insertion needs the
        # coordinator to keep polling regardless of listener count.
        @callback
        def _dummy_listener() -> None:
            pass

        self.async_add_listener(_dummy_listener)

    async def _async_update_data(
        self,
    ) -> dict[str, dict]:
        """Fetch data from API endpoint.

        Returns a dict keyed by account_number, each containing:
            - "nickname": account display name
            - "forecast": forecast fields dict or empty dict
            - "billing": billing fields dict or empty dict
        """
        try:
            await self.hass.async_add_executor_job(self.api.login)
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except CannotConnect as err:
            raise UpdateFailed(f"Error during login: {err}") from err

        result: dict[str, dict] = {}

        try:
            accounts = await self.hass.async_add_executor_job(self.api.get_accounts)
            active_accounts = [a for a in accounts if a.status == "Active"]
            _LOGGER.debug("Discovered %d accounts (%d active)", len(accounts), len(active_accounts))

            for acct in active_accounts:
                acct_num = acct.account_number
                nickname = acct.nickname or acct.address or acct_num
                _LOGGER.debug("Fetching data for account %s (%s)", acct_num, nickname)

                switched = await self.hass.async_add_executor_job(self.api.switch_account, nickname)
                if not switched:
                    _LOGGER.warning("Failed to switch to account %s (%s), skipping", acct_num, nickname)
                    continue

                self.api.account = next(
                    (a for a in self.api.utility.accounts if a["accountNumber"] == acct_num),
                    self.api.account,
                )

                result[acct_num] = {
                    "nickname": nickname,
                    "forecast": {},
                    "billing": {},
                }

                try:
                    forecasts = await self.hass.async_add_executor_job(self.api.get_forecast)
                    for forecast in forecasts:
                        result[acct_num]["forecast"] = {
                            "forecasted_cost": forecast.forecasted_cost,
                            "forecasted_cost_low": forecast.forecasted_cost_low,
                            "forecasted_cost_high": forecast.forecasted_cost_high,
                        }
                except (CannotConnect, json.JSONDecodeError, KeyError, ValueError) as err:
                    _LOGGER.warning("Failed to fetch forecast for %s: %s", acct_num, err)

                try:
                    billing = await self.hass.async_add_executor_job(self.api.get_billing_info)
                    if billing:
                        result[acct_num]["billing"] = {
                            "current_balance": billing.current_balance,
                            "due_date": billing.due_date,
                            "past_due_amount": billing.past_due_amount,
                            "last_payment_amount": billing.last_payment_amount,
                            "last_payment_date": billing.last_payment_date,
                            "next_statement_date": billing.next_statement_date,
                        }
                except (CannotConnect, json.JSONDecodeError, KeyError, ValueError) as err:
                    _LOGGER.warning("Failed to fetch billing for %s: %s", acct_num, err)

                try:
                    await self._insert_statistics()
                except (CannotConnect, json.JSONDecodeError, KeyError, ValueError) as err:
                    _LOGGER.warning("Failed to insert statistics for %s: %s", acct_num, err)

            _LOGGER.debug("Updating sensor data: %s", result)

        finally:
            await self.hass.async_add_executor_job(self.api.end_session)

        if not result:
            raise UpdateFailed("No data received from any account")

        return result

    async def _insert_statistics(self) -> None:
        """Insert Rocky Mountain Power statistics."""
        account = await self.hass.async_add_executor_job(self.api.get_account)
        id_prefix = (
            f"elec_{account.uuid}"
            .replace("-", "_")
            .replace(" ", "_")
        )
        cost_statistic_id = f"{DOMAIN}:{id_prefix}_energy_cost"
        consumption_statistic_id = f"{DOMAIN}:{id_prefix}_energy_consumption"
        _LOGGER.debug(
            "Updating Statistics for %s and %s",
            cost_statistic_id,
            consumption_statistic_id,
        )

        last_stat = await get_instance(self.hass).async_add_executor_job(
            get_last_statistics, self.hass, 1, consumption_statistic_id, True, set()
        )
        if not last_stat:
            _LOGGER.debug("Updating statistic for the first time")
            cost_reads = await self._async_get_all_cost_reads()
            cost_sum = 0.0
            consumption_sum = 0.0
            last_stats_time = None
        else:
            cost_reads = await self._async_get_recent_cost_reads()
            if not cost_reads:
                _LOGGER.debug("No recent usage/cost data. Skipping update")
                return
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                cost_reads[0].start_time,
                None,
                {cost_statistic_id, consumption_statistic_id},
                "hour",
                None,
                {"sum"},
            )
            if (
                cost_statistic_id not in stats
                or not stats[cost_statistic_id]
                or consumption_statistic_id not in stats
                or not stats[consumption_statistic_id]
            ):
                _LOGGER.debug("Previous statistics not found, starting fresh")
                cost_sum = 0.0
                consumption_sum = 0.0
                last_stats_time = None
            else:
                cost_sum = cast(float, stats[cost_statistic_id][0]["sum"])
                consumption_sum = cast(float, stats[consumption_statistic_id][0]["sum"])
                last_stats_time = stats[cost_statistic_id][0]["start"]

        cost_statistics = []
        consumption_statistics = []

        for cost_read in cost_reads:
            start = cost_read.start_time
            if last_stats_time is not None and start.timestamp() <= last_stats_time:
                continue
            cost_sum += cost_read.provided_cost
            consumption_sum += cost_read.consumption

            cost_statistics.append(
                StatisticData(
                    start=start, state=cost_read.provided_cost, sum=cost_sum
                )
            )
            consumption_statistics.append(
                StatisticData(
                    start=start, state=cost_read.consumption, sum=consumption_sum
                )
            )

        name_prefix = f"Rocky Mountain Power elec {account.uuid}"
        cost_metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{name_prefix} cost",
            source=DOMAIN,
            statistic_id=cost_statistic_id,
            unit_class=None,
            unit_of_measurement=None,
        )
        consumption_metadata = StatisticMetaData(
            mean_type=StatisticMeanType.NONE,
            has_sum=True,
            name=f"{name_prefix} consumption",
            source=DOMAIN,
            statistic_id=consumption_statistic_id,
            unit_class=EnergyConverter.UNIT_CLASS,
            unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        )

        async_add_external_statistics(self.hass, cost_metadata, cost_statistics)
        async_add_external_statistics(
            self.hass, consumption_metadata, consumption_statistics
        )

    async def _async_get_all_cost_reads(self) -> list[CostRead]:
        """Get all cost reads since account activation at different resolutions.

        Fetches month, day, and hour granularity data. Deduplicates overlapping
        time periods by keeping the finest granularity available for each start time.
        """
        cost_reads = []
        cost_reads.extend(await self.hass.async_add_executor_job(self.api.get_cost_reads, AggregateType.MONTH))
        cost_reads.extend(await self.hass.async_add_executor_job(self.api.get_cost_reads, AggregateType.DAY, 24))
        cost_reads.extend(await self.hass.async_add_executor_job(self.api.get_cost_reads, AggregateType.HOUR, 60))
        return self._deduplicate_cost_reads(cost_reads)

    async def _async_get_recent_cost_reads(self) -> list[CostRead]:
        """Get hourly reads within the past 7 days to allow corrections in data from utilities."""
        cost_reads = await self.hass.async_add_executor_job(self.api.get_cost_reads, AggregateType.HOUR, 7)
        return cost_reads

    @staticmethod
    def _deduplicate_cost_reads(cost_reads: list[CostRead]) -> list[CostRead]:
        """Remove duplicate cost reads, keeping the finest granularity for each start time.

        When fetching at multiple resolutions (month/day/hour), time periods can overlap.
        We keep only one entry per start_time, preferring shorter duration (finer granularity).
        """
        by_start: dict[float, CostRead] = {}
        for read in cost_reads:
            ts = read.start_time.timestamp()
            existing = by_start.get(ts)
            if existing is None:
                by_start[ts] = read
            else:
                existing_duration = (existing.end_time - existing.start_time).total_seconds()
                new_duration = (read.end_time - read.start_time).total_seconds()
                if new_duration < existing_duration:
                    by_start[ts] = read
        result = list(by_start.values())
        result.sort(key=lambda r: r.start_time)
        return result
