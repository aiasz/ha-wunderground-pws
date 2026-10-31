"""Binary sensor platform: station online / offline.

Author: Aiasz
Plan: PLAN.md F08 (data quality: stale-observation detection)
"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import ATTR_OBS_AGE_MIN, ATTR_STATION_ONLINE
from .coordinator import WundergroundConfigEntry
from .entity import WundergroundPWSEntity

PARALLEL_UPDATES = 0

STATION_ONLINE = BinarySensorEntityDescription(
    key="station_online",
    translation_key="station_online",
    device_class=BinarySensorDeviceClass.CONNECTIVITY,
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: WundergroundConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities([WundergroundPWSStationOnline(entry.runtime_data)])


class WundergroundPWSStationOnline(WundergroundPWSEntity, BinarySensorEntity):
    """``on`` while the station keeps reporting new observations."""

    entity_description = STATION_ONLINE

    def __init__(self, coordinator) -> None:
        """Initialise the sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.station_id}_{STATION_ONLINE.key}"

    @property
    def is_on(self) -> bool | None:
        """Whether the last observation is recent enough (``None`` = unknown)."""
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get(ATTR_STATION_ONLINE)

    @property
    def extra_state_attributes(self) -> dict[str, float | None]:
        """Age of the last observation in minutes."""
        data = self.coordinator.data or {}
        return {"observation_age_min": data.get(ATTR_OBS_AGE_MIN)}
