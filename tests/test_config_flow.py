"""Config flow tests for the Lishui water integration."""

from __future__ import annotations

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hass_water_lishui.client import (
    LishuiWaterApiError,
    LishuiWaterAuthError,
)
from fixtures import DOMAIN, ENTRY_DATA, FARES

_FETCH = "custom_components.hass_water_lishui.client.LishuiWaterClient.async_fetch_fares"


async def test_user_step_shows_form(hass) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_flow_creates_entry(hass) -> None:
    """A meter that returns bills creates one entry per meter number."""
    with patch(_FETCH, return_value=FARES):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"card_no": "123456", "year": "2026", "token": ""}
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["card_no"] == "123456"
    assert result["result"].unique_id == "123456"


async def test_unknown_error(hass) -> None:
    with patch(_FETCH, side_effect=RuntimeError("boom")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"card_no": "123456", "year": "2026", "token": ""}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


async def test_invalid_auth(hass) -> None:
    with patch(_FETCH, side_effect=LishuiWaterAuthError("bad token")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"card_no": "123456", "year": "2026", "token": ""}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_cannot_connect(hass) -> None:
    with patch(_FETCH, side_effect=LishuiWaterApiError("HTTP error")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"card_no": "123456", "year": "2026", "token": ""}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_empty_bill_list_reports_no_data(hass) -> None:
    """An empty list is "wrong meter/year", not "cannot connect"."""
    with patch(_FETCH, return_value=[]):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"card_no": "999999", "year": "2026", "token": ""}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_data"}


async def test_aborts_for_a_known_meter(hass) -> None:
    MockConfigEntry(
        domain=DOMAIN, unique_id="123456", data=ENTRY_DATA, title="丽水水费 123456"
    ).add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"card_no": "123456", "year": "2026", "token": ""}
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_token_and_reloads(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="123456", data=ENTRY_DATA, title="丽水水费 123456"
    )
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "new-token"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "new-token"
    assert entry.data["card_no"] == "123456"


async def test_reauth_keeps_the_form_on_bad_token(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="123456", data=ENTRY_DATA, title="丽水水费 123456"
    )
    entry.add_to_hass(hass)

    with patch(_FETCH, side_effect=LishuiWaterAuthError("bad token")):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "still-bad"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["token"] == "old-token"


async def test_reauth_is_not_blocked_by_an_empty_bill_list(hass) -> None:
    """An empty list proves the token works: reauth must be able to finish.

    Otherwise a meter with no bill for that year can never complete reauth and
    the user is stuck with a permanent reauth card.
    """
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="123456", data=ENTRY_DATA, title="丽水水费 123456"
    )
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=[]):
        result = await entry.start_reauth_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"token": "new-token"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"] == "new-token"


async def test_reconfigure_changes_the_billing_year(hass) -> None:
    """The billing year is a connection setting, so it is reconfigured."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="123456", data=ENTRY_DATA, title="丽水水费 123456"
    )
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=FARES):
        result = await entry.start_reconfigure_flow(hass)
        assert result["type"] is FlowResultType.FORM
        assert result["step_id"] == "reconfigure"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"year": "2027"}
        )
        await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert entry.data["year"] == "2027"
    assert entry.data["token"] == "old-token"


async def test_reconfigure_rejects_a_year_without_bills(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="123456", data=ENTRY_DATA, title="丽水水费 123456"
    )
    entry.add_to_hass(hass)

    with patch(_FETCH, return_value=[]):
        result = await entry.start_reconfigure_flow(hass)
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {"year": "2099"}
        )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_data"}
    assert entry.data["year"] == "2026"
