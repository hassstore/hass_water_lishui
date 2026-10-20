"""Data coordinator for hass_water_lishui."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .client import LishuiWaterApiError, LishuiWaterAuthError, LishuiWaterClient
from .const import (
    CONF_CARD_NO,
    CONF_SCAN_INTERVAL,
    CONF_TOKEN,
    CONF_YEAR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class LishuiWaterData:
    """Normalized water fee data."""

    latest: dict[str, Any]
    history: list[dict[str, Any]] = field(default_factory=list)
    updated_at: str = ""


class LishuiWaterCoordinator(DataUpdateCoordinator[LishuiWaterData]):
    """Coordinator for Lishui water billing data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the coordinator."""
        self.client = LishuiWaterClient(
            session=async_get_clientsession(hass),
            card_no=entry.data[CONF_CARD_NO],
            year=str(entry.data[CONF_YEAR]),
            token=str(entry.data.get(CONF_TOKEN, "")),
        )
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=self._resolve_scan_interval(entry),
        )

    @staticmethod
    def _resolve_scan_interval(entry: ConfigEntry) -> timedelta:
        """Resolve the poll interval from options with sane bounds."""
        try:
            hours = float(entry.options.get(CONF_SCAN_INTERVAL, 0))
        except (TypeError, ValueError):
            hours = 0.0
        interval = timedelta(hours=hours) if hours > 0 else DEFAULT_SCAN_INTERVAL
        return min(max(interval, MIN_SCAN_INTERVAL), MAX_SCAN_INTERVAL)

    async def _async_update_data(self) -> LishuiWaterData:
        """Fetch and normalize data."""
        try:
            items = await self.client.async_fetch_fares()
        except LishuiWaterAuthError as err:
            # Expired/invalid token -> let HA show the reauth card.
            raise ConfigEntryAuthFailed(str(err)) from err
        except LishuiWaterApiError as err:
            raise UpdateFailed(str(err)) from err

        if not items:
            raise UpdateFailed("No billing data returned")

        # Guard against malformed records: a non-dict entry would break the
        # sort below (and every sensor) for the whole update.
        records = [item for item in items if isinstance(item, dict)]
        if not records:
            raise UpdateFailed("Billing data has an unexpected format")

        sorted_items = sorted(
            records, key=lambda item: str(item.get("fareMonth", "")), reverse=True
        )
        return LishuiWaterData(
            latest=sorted_items[0],
            history=sorted_items[:12],
            updated_at=dt_util.now().isoformat(),
        )


async def async_validate_input(
    hass: HomeAssistant,
    user_input: dict[str, Any],
) -> dict[str, Any]:
    """Validate user input by calling the API once."""
    client = LishuiWaterClient(
        session=async_get_clientsession(hass),
        card_no=user_input[CONF_CARD_NO],
        year=str(user_input[CONF_YEAR]),
        token=str(user_input.get(CONF_TOKEN, "")),
    )
    fares = await client.async_fetch_fares()
    if not fares:
        raise LishuiWaterApiError("No billing data returned")
    return {"title": f"丽水水费 {user_input[CONF_CARD_NO]}"}
