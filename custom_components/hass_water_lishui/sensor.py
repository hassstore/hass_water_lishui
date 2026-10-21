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
from homeassistant.core import HomeAssistant
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

# Read-only platform: every entity reads the same coordinator snapshot, so there
# is no reason to serialise updates with a semaphore.
PARALLEL_UPDATES = 0

# billFlag: 0 = paid, anything else = unpaid. Keys are translated.
_BILL_STATES = ["paid", "unpaid"]

# Field semantics of one getFareList record:
#   fareValue   -> amount charged for the period (money, not volume)
#   balance     -> account balance
#   currDegree  -> current meter reading, lastDegree -> previous reading
#   billFlag    -> 0 when the bill has been paid
#   fareMonth / currCopyDate / lastCopyDate -> billing period and read dates
SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="latest_bill_amount",
        translation_key="latest_bill_amount",
        # MONETARY only allows SensorStateClass.TOTAL. A bill amount is a
        # per-period figure, so it is left without a state class on purpose:
        # HA then shows it as a value instead of a running sum.
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
        key="account_balance",
        translation_key="account_balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        suggested_display_precision=2,
        entity_registry_enabled_default=False,
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
        entity_registry_enabled_default=False,
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

# Sensor key -> field of the bill record it reports directly.
_VALUE_KEYS: dict[str, str] = {
    "latest_bill_amount": "fareValue",
    "account_balance": "balance",
    "latest_bill_status": "billFlag",
    "latest_meter_reading": "currDegree",
    "latest_previous_meter_reading": "lastDegree",
}


def _as_float(value: Any) -> float | None:
    """Convert an API value to float, or None when it is not numeric."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    # The bill history is a large, slowly changing blob and `updated_at` changes
    # on every poll; neither belongs in the recorder database. Both stay
    # available in the live state attributes.
    _unrecorded_attributes = frozenset({ATTR_HISTORY_BILLS, "updated_at"})

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
            # One device per water meter, keyed by the meter number so it
            # survives a reauth/reconfigure of the same meter.
            identifiers={(DOMAIN, card_no)},
            name=entry.title,
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
            flag = _as_float(latest.get("billFlag"))
            if flag is None:
                return None
            return "paid" if int(flag) == 0 else "unpaid"

        if key == "latest_usage":
            # The API only exposes meter readings, so usage is the delta
            # between this and the previous period.
            current = _as_float(latest.get("currDegree"))
            previous = _as_float(latest.get("lastDegree"))
            if current is None or previous is None:
                return None
            usage = current - previous
            # A negative delta means the meter was swapped or reset; report
            # unknown rather than corrupting the statistics.
            return usage if usage >= 0 else None

        value = latest.get(_VALUE_KEYS[key])
        return _as_float(value)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra state attributes."""
        latest = self.coordinator.data.latest
        flag = _as_float(latest.get("billFlag"))
        attrs: dict[str, Any] = {
            ATTR_FARE_MONTH: latest.get("fareMonth"),
            ATTR_CURR_COPY_DATE: latest.get("currCopyDate"),
            ATTR_LAST_COPY_DATE: latest.get("lastCopyDate"),
            ATTR_IS_PAID: None if flag is None else int(flag) == 0,
        }

        if self.entity_description.key == "latest_bill_amount":
            attrs["updated_at"] = self.coordinator.data.updated_at
            attrs[ATTR_HISTORY_BILLS] = self.coordinator.data.history

        return attrs
