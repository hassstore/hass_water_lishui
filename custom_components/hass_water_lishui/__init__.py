"""The hass_water_lishui integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import PLATFORMS
from .coordinator import LishuiWaterCoordinator

type LishuiWaterConfigEntry = ConfigEntry[LishuiWaterCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LishuiWaterConfigEntry) -> bool:
    """Set up hass_water_lishui from a config entry."""
    coordinator = LishuiWaterCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_entry_updated))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LishuiWaterConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


@callback
def _async_entry_updated(hass: HomeAssistant, entry: LishuiWaterConfigEntry) -> None:
    """Reload the entry when its options change."""
    hass.async_create_task(hass.config_entries.async_reload(entry.entry_id))
