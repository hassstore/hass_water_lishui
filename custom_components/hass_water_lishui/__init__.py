"""The hass_water_lishui integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import PLATFORMS
from .coordinator import LishuiWaterCoordinator

type LishuiWaterConfigEntry = ConfigEntry[LishuiWaterCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LishuiWaterConfigEntry) -> bool:
    """Set up hass_water_lishui from a config entry."""
    coordinator = LishuiWaterCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # No config entry update listener on purpose: option changes are reloaded by
    # OptionsFlowWithReload and reauth reloads the entry itself. Home Assistant
    # rejects update listeners combined with OptionsFlowWithReload.
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LishuiWaterConfigEntry) -> bool:
    """Unload a config entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    entry.runtime_data = None
    return True
