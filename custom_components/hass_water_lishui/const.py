"""Constants for hass_water_lishui integration."""

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "hass_water_lishui"
PLATFORMS: Final = [Platform.SENSOR]

CONF_CARD_NO: Final = "card_no"
CONF_YEAR: Final = "year"
CONF_TOKEN: Final = "token"
CONF_SCAN_INTERVAL: Final = "scan_interval"

DEFAULT_SCAN_INTERVAL: Final = timedelta(hours=6)
MIN_SCAN_INTERVAL: Final = timedelta(hours=1)
MAX_SCAN_INTERVAL: Final = timedelta(hours=48)

DEFAULT_API_BASE: Final = "http://wx.lswater.cn"
API_TIMEOUT: Final = 15

ATTR_HISTORY_BILLS: Final = "history_bills"
ATTR_IS_PAID: Final = "is_paid"
ATTR_FARE_MONTH: Final = "fare_month"
ATTR_CURR_COPY_DATE: Final = "curr_copy_date"
ATTR_LAST_COPY_DATE: Final = "last_copy_date"
