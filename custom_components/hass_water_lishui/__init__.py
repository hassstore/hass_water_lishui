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
    # Options (poll interval) are read when the coordinator is built, so the
    # entry has to be reloaded for a change to take effect.
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LishuiWaterConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(
    hass: HomeAssistant, entry: LishuiWaterConfigEntry
) -> None:
    """Reload the entry after its options changed."""
    await hass.config_entries.async_reload(entry.entry_id)
