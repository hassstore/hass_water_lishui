"""Config flow for hass_water_lishui."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.util import dt as dt_util

from .client import LishuiWaterApiError, LishuiWaterAuthError
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
from .coordinator import async_validate_input


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the user step schema, optionally pre-filling defaults."""
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_CARD_NO, default=defaults.get(CONF_CARD_NO, "")): str,
            # The API is queried per billing year; default to the current one
            # so the user only has to type the meter number.
            vol.Required(
                CONF_YEAR,
                default=str(defaults.get(CONF_YEAR) or dt_util.now().year),
            ): str,
            vol.Optional(CONF_TOKEN, default=defaults.get(CONF_TOKEN, "")): str,
        }
    )


class HassWaterLishuiConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for hass_water_lishui."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            data = {
                CONF_CARD_NO: str(user_input[CONF_CARD_NO]).strip(),
                CONF_YEAR: str(user_input[CONF_YEAR]).strip(),
                CONF_TOKEN: str(user_input.get(CONF_TOKEN, "")).strip(),
            }
            try:
                info = await async_validate_input(self.hass, data)
            except LishuiWaterAuthError:
                errors["base"] = "invalid_auth"
            except LishuiWaterApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface anything else as unknown
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(data[CONF_CARD_NO])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=info["title"], data=data)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        """Handle reauthentication when the token expires."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask the user for a fresh token and validate it."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            new_data = {
                **reauth_entry.data,
                CONF_TOKEN: str(user_input.get(CONF_TOKEN, "")).strip(),
            }
            try:
                await async_validate_input(self.hass, new_data)
            except LishuiWaterAuthError:
                errors["base"] = "invalid_auth"
            except LishuiWaterApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface anything else as unknown
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=new_data)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Optional(CONF_TOKEN, default=""): str}),
            description_placeholders={"card_no": reauth_entry.data[CONF_CARD_NO]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LishuiWaterOptionsFlow:
        """Return the options flow."""
        return LishuiWaterOptionsFlow()


class LishuiWaterOptionsFlow(OptionsFlow):
    """Handle options for hass_water_lishui."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_hours = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL.total_seconds() / 3600
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SCAN_INTERVAL, default=float(current_hours)
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_INTERVAL.total_seconds() / 3600,
                            max=MAX_SCAN_INTERVAL.total_seconds() / 3600,
                            step=0.5,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="h",
                        )
                    ),
                }
            ),
        )
