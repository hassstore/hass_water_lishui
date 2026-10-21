"""Config flow for hass_water_lishui."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)
from homeassistant.util import dt as dt_util

from .client import (
    LishuiWaterApiError,
    LishuiWaterAuthError,
    LishuiWaterNoDataError,
)
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
            except LishuiWaterNoDataError:
                # Connected fine, but this meter/year has no bills: the user
                # most likely mistyped the meter number or the billing year.
                errors["base"] = "no_data"
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
            token = str(user_input[CONF_TOKEN]).strip()
            try:
                # An empty bill list only means "nothing billed for this
                # meter/year". The API answered, so the token is fine: refusing
                # here would trap the user in a reauth loop that can never finish.
                await async_validate_input(
                    self.hass,
                    {**reauth_entry.data, CONF_TOKEN: token},
                    require_data=False,
                )
            except LishuiWaterAuthError:
                errors["base"] = "invalid_auth"
            except LishuiWaterApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface anything else as unknown
                errors["base"] = "unknown"
            else:
                # The entry is reloaded by this flow method, so the integration
                # does not register an update listener (HA rejects the
                # combination of the two, see OptionsFlowWithReload).
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates={CONF_TOKEN: token}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            description_placeholders={"card_no": reauth_entry.data[CONF_CARD_NO]},
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change the billing year — the API answers per year, so this is a
        connection setting, not a preference."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if user_input is not None:
            year = str(user_input[CONF_YEAR]).strip()
            try:
                await async_validate_input(self.hass, {**entry.data, CONF_YEAR: year})
            except LishuiWaterAuthError:
                errors["base"] = "invalid_auth"
            except LishuiWaterNoDataError:
                # Almost always a typo in the year.
                errors["base"] = "no_data"
            except LishuiWaterApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - surface anything else as unknown
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_YEAR: year}
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_YEAR, default=str(entry.data.get(CONF_YEAR, ""))
                    ): str
                }
            ),
            description_placeholders={
                "card_no": entry.data.get(CONF_CARD_NO, "")
            },
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LishuiWaterOptionsFlow:
        """Return the options flow."""
        return LishuiWaterOptionsFlow()


class LishuiWaterOptionsFlow(OptionsFlowWithReload):
    """Handle options for hass_water_lishui.

    Options (poll interval) are read when the coordinator is built, so the
    entry has to be reloaded for a change to take effect. Inheriting
    ``OptionsFlowWithReload`` lets HA schedule that reload itself, which is why
    the integration no longer registers a config entry update listener.
    """

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
