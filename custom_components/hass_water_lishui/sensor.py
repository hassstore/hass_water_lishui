"""Sensor platform for hass_water_lishui."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfVolume
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LishuiWaterConfigEntry
from .const import (
    ATTR_CURR_COPY_DATE,
    ATTR_FARE_MONTH,
    ATTR_HISTORY_BILLS,
    ATTR_IS_PAID,
    ATTR_LAST_COPY_DATE,
    CONF_CARD_NO,
    DOMAIN,
)
from .coordinator import LishuiWaterCoordinator

# billFlag: 0 = paid, anything else = unpaid. Keyed for translation.
_BILL_STATES = ["paid", "unpaid"]

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="latest_balance",
        translation_key="latest_balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="latest_usage",
        translation_key="latest_usage",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="latest_bill_status",
        translation_key="latest_bill_status",
        device_class=SensorDeviceClass.ENUM,
        options=_BILL_STATES,
    ),
    SensorEntityDescription(
        key="latest_meter_reading",
        translation_key="latest_meter_reading",
        device_class=SensorDeviceClass.WATER,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=2,
    ),
    SensorEntityDescription(
        key="latest_previous_meter_reading",
        translation_key="latest_previous_meter_reading",
        device_class=SensorDeviceClass.WATER,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
    ),
)

# Maps a sensor key to the field in one bill record.
_VALUE_KEYS = {
    "latest_balance": "balance",
    "latest_usage": "fareValue",
    "latest_bill_status": "billFlag",
    "latest_meter_reading": "currDegree",
    "latest_previous_meter_reading": "lastDegree",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LishuiWaterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Lishui water sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        LishuiWaterSensor(coordinator, entry, description) for description in SENSORS
    )


class LishuiWaterSensor(CoordinatorEntity[LishuiWaterCoordinator], SensorEntity):
    """Representation of a Lishui water sensor."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: LishuiWaterCoordinator,
        entry: LishuiWaterConfigEntry,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        card_no = str(entry.data[CONF_CARD_NO])
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, card_no)},
            name=f"丽水水费 {card_no}",
            manufacturer="丽水市供排水有限责任公司",
            model="水费账单",
            serial_number=card_no,
        )

    @property
    def native_value(self) -> Any:
        """Return the sensor native value."""
        latest = self.coordinator.data.latest
        key = self.entity_description.key

        if key == "latest_bill_status":
            flag = latest.get(_VALUE_KEYS[key])
            if flag is None:
                return None
            return "paid" if int(flag) == 0 else "unpaid"

        value = latest.get(_VALUE_KEYS[key])
        if value is None:
            # Unknown beats a fabricated 0 — a missing reading must not
            # pollute long-term statistics.
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return value

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        latest = self.coordinator.data.latest
        attrs: dict[str, Any] = {
            ATTR_FARE_MONTH: latest.get("fareMonth"),
            ATTR_CURR_COPY_DATE: latest.get("currCopyDate"),
            ATTR_LAST_COPY_DATE: latest.get("lastCopyDate"),
            ATTR_IS_PAID: int(latest.get("billFlag", 1) or 0) == 0,
        }

        if self.entity_description.key == "latest_balance":
            attrs["updated_at"] = self.coordinator.data.updated_at
            attrs[ATTR_HISTORY_BILLS] = self.coordinator.data.history

        return attrs
