"""Diagnostics support for hass_water_lishui.

The config entry holds the WeChat mini-program token, which is equivalent to a
session cookie for the billing portal, and the meter number, which identifies
the household. Both are redacted here; the shape and status of the data is what
is needed for troubleshooting.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import LishuiWaterConfigEntry
from .const import CONF_CARD_NO, CONF_TOKEN, CONF_YEAR

TO_REDACT = {CONF_TOKEN, CONF_CARD_NO}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LishuiWaterConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = getattr(entry, "runtime_data", None)
    data = coordinator.data if coordinator is not None else None

    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "has_unique_id": bool(entry.unique_id),
            "token_present": bool(entry.data.get(CONF_TOKEN)),
        },
        "options": dict(entry.options),
        "coordinator": {
            "last_update_success": (
                coordinator.last_update_success if coordinator is not None else None
            ),
            "update_interval_s": (
                coordinator.update_interval.total_seconds()
                if coordinator is not None and coordinator.update_interval
                else None
            ),
            "updated_at": data.updated_at if data is not None else None,
            "latest_fare_month": (
                data.latest.get("fareMonth") if data is not None else None
            ),
            "history_records": len(data.history) if data is not None else None,
            "year": entry.data.get(CONF_YEAR),
        },
    }
