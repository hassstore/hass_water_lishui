"""Setup, entity, options and diagnostics tests for the Lishui water integration."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.icon import async_get_icons
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hass_water_lishui.client import LishuiWaterAuthError
from custom_components.hass_water_lishui.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.hass_water_lishui.sensor import SENSORS
from fixtures import DOMAIN, ENTRY_DATA, FARES

_FETCH = "custom_components.hass_water_lishui.client.LishuiWaterClient.async_fetch_fares"


def _entities(hass: HomeAssistant, entry: MockConfigEntry) -> dict[str, str]:
    registry = er.async_get(hass)
    return {
        item.unique_id.removeprefix(f"{entry.entry_id}_"): item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


def _entry(**kwargs) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id="123456",
        data=ENTRY_DATA,
        title="Lishui water 123456",
        **kwargs,
    )


async def test_setup_creates_sensors(hass: HomeAssistant) -> None:
    """Every declared sensor is created and reads the newest bill."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    entities = _entities(hass, entry)
    assert len(entities) == len(SENSORS)
    assert set(entities) == {description.key for description in SENSORS}

    assert float(hass.states.get(entities["latest_bill_amount"]).state) == 42.5
    assert float(hass.states.get(entities["latest_usage"]).state) == 34.5
    assert hass.states.get(entities["latest_bill_status"]).state == "paid"

    # Diagnostic-ish readings stay disabled by default (and are documented).
    registry = er.async_get(hass)
    assert registry.async_get(entities["latest_meter_reading"]).disabled_by is not None
    assert registry.async_get(entities["account_balance"]).disabled_by is not None

    # The newest bill's period is exposed as an attribute.
    assert (
        hass.states.get(entities["latest_bill_amount"]).attributes["fare_month"]
        == "2026-09"
    )


async def test_empty_bill_list_is_unknown_not_unavailable(hass: HomeAssistant) -> None:
    """No bill for that year means `unknown`, and the entry stays loaded."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=[]):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    entities = _entities(hass, entry)
    assert hass.states.get(entities["latest_bill_amount"]).state == "unknown"
    assert hass.states.get(entities["latest_usage"]).state == "unknown"


async def test_auth_failure_starts_reauth(hass: HomeAssistant) -> None:
    """An invalid token must surface as a reauth card, not a silent failure."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(_FETCH, side_effect=LishuiWaterAuthError("expired")):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is not ConfigEntryState.LOADED
    flows = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert [flow["context"]["source"] for flow in flows] == ["reauth"]


async def test_unload_entry(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert getattr(entry, "runtime_data", None) is None


async def test_options_flow_stores_and_reloads(hass: HomeAssistant) -> None:
    """Changing the poll interval is stored and the entry reloads itself."""
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == "form"
        assert result["step_id"] == "init"

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"scan_interval": 12.0}
        )
        await hass.async_block_till_done()

    assert result["type"] == "create_entry"
    assert entry.options["scan_interval"] == 12.0
    # OptionsFlowWithReload reloads the entry; no update listener is involved.
    assert entry.state is ConfigEntryState.LOADED


async def test_diagnostics_redact_token(hass: HomeAssistant) -> None:
    entry = _entry()
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    diag = await async_get_config_entry_diagnostics(hass, entry)
    dumped = str(diag)

    assert "old-token" not in dumped
    # The meter number identifies the household, so it is redacted too.
    assert "123456" not in dumped
    assert diag["entry"]["token_present"] is True
    assert diag["coordinator"]["latest_fare_month"] == "2026-09"
    assert diag["coordinator"]["history_records"] == 2


async def test_icons_are_translated(hass: HomeAssistant) -> None:
    """Icons come from icons.json, including per-state icons."""
    icons = await async_get_icons(hass, "entity", [DOMAIN])

    assert icons[DOMAIN]["sensor"]["latest_bill_status"]["state"]["paid"] == (
        "mdi:check-circle"
    )
    # Sensors whose device class already provides an icon are not overridden.
    assert "latest_usage" not in icons[DOMAIN]["sensor"]
    assert icons[DOMAIN]["sensor"]["account_balance"]["default"] == "mdi:wallet"
