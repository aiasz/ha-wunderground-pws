"""Shared entity base for the Wunderground PWS platforms.

Author: Aiasz
Plan: PLAN.md B14 (no hard-coded version strings), M1 (translated names)
"""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION_WU, DOMAIN, WU_DASHBOARD_URL
from .coordinator import WundergroundPWSCoordinator


def build_device_info(station_id: str) -> DeviceInfo:
    """Device shared by all entities of one station."""
    return DeviceInfo(
        identifiers={(DOMAIN, station_id)},
        name=f"Wunderground PWS {station_id}",
        manufacturer="Aiasz",
        model="Weather Underground PWS",
        configuration_url=WU_DASHBOARD_URL.format(station_id=station_id),
    )


class WundergroundPWSEntity(CoordinatorEntity[WundergroundPWSCoordinator]):
    """Base class: device info, naming and attribution in one place."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION_WU

    def __init__(self, coordinator: WundergroundPWSCoordinator) -> None:
        """Attach to the station device."""
        super().__init__(coordinator)
        self._attr_device_info = build_device_info(coordinator.station_id)
