"""EX-CommandStation entity base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER
from .coordinator import LocoUpdateCoordinator

if TYPE_CHECKING:
    from .excs_client import EXCommandStationClient
    from .roster import RosterEntry


class EXCSEntity(Entity):
    """Base class for EX-CommandStation entities."""

    def __init__(self, client: EXCommandStationClient) -> None:
        """Initialize the entity."""
        self._client = client
        self._attr_has_entity_name = True
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client.host)},
            name="EX-CommandStation",
            manufacturer="DCC-EX",
            model="EX-CommandStation",
            sw_version=client.system_info.version,
        )
        # Initialize availability based on current connection state
        self._attr_available = client.connected

    def _handle_push(self, message: str) -> None:
        """Handle incoming messages from the EX-CommandStation."""
        # This method should be overridden in subclasses to handle specific messages
        raise NotImplementedError

    @callback
    def _on_connect(self) -> None:
        """Handle connection to the EX-CommandStation."""
        self._attr_available = True
        self.async_write_ha_state()

    @callback
    def _on_disconnect(self, exc: Exception) -> None:
        """Handle disconnection from the EX-CommandStation."""
        LOGGER.debug("Entity became unavailable due to: %s", exc)
        self._attr_available = False
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self._client.register_push_callback(self._handle_push)
        self._client.register_on_connect_callback(self._on_connect)
        self._client.register_on_disconnect_callback(self._on_disconnect)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self._client.unregister_push_callback(self._handle_push)
        self._client.unregister_on_connect_callback(self._on_connect)
        self._client.unregister_on_disconnect_callback(self._on_disconnect)


class EXCSRosterEntity(CoordinatorEntity[LocoUpdateCoordinator]):
    """Base class for EX-CommandStation roster entities."""

    def __init__(
        self,
        client: EXCommandStationClient,
        coordinator: LocoUpdateCoordinator,
        roster_entry: RosterEntry,
    ) -> None:
        """Initialize the roster entity."""
        super().__init__(coordinator)
        self._loco = roster_entry
        self._client = client
        self._attr_has_entity_name = True
        self._attr_should_poll = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{client.host}_loco_{roster_entry.id}")},
            name=roster_entry.description,
            manufacturer="DCC-EX",
            model=roster_entry.description,
            model_id=str(roster_entry.id),
            via_device=(DOMAIN, client.host),
        )
