"""EX-CommandStation entity base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    LOGGER,
    SIGNAL_CONNECTED,
    SIGNAL_DATA_PUSHED,
    SIGNAL_DISCONNECTED,
)
from .coordinator import LocoUpdateCoordinator

if TYPE_CHECKING:
    from .excs_client import EXCommandStationClient
    from .roster import RosterEntry


class EXCSEntity(Entity):
    """Base class for EX-CommandStation entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, client: EXCommandStationClient) -> None:
        """Initialize the entity."""
        self._client = client
        self._attr_available = client.connected  # Available if client is connected
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client.host)},
            name="EX-CommandStation",
            manufacturer="DCC-EX",
            model="EX-CommandStation",
            sw_version=client.system_info.version,
            suggested_area="Train Layout",
        )

        # List to store signal unsubscribe callbacks
        self._unsub_callbacks = []

    @callback
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
        self._unsub_callbacks = [
            self._client.register_signal_handler(SIGNAL_CONNECTED, self._on_connect),
            self._client.register_signal_handler(
                SIGNAL_DISCONNECTED, self._on_disconnect
            ),
            self._client.register_signal_handler(SIGNAL_DATA_PUSHED, self._handle_push),
        ]

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        for unsub in self._unsub_callbacks:
            unsub()
        self._unsub_callbacks.clear()


class EXCSRosterEntity(CoordinatorEntity[LocoUpdateCoordinator]):
    """Base class for EX-CommandStation roster entities."""

    _attr_has_entity_name = True
    _attr_should_poll = False

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
        self._attr_available = client.connected  # Available if client is connected
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{client.host}_loco_{roster_entry.id}")},
            name=f"Loco {roster_entry.description or roster_entry.id}",
            manufacturer="DCC-EX",
            model=roster_entry.description or f"Locomotive {roster_entry.id}",
            model_id=str(roster_entry.id),
            via_device=(DOMAIN, client.host),
            suggested_area="Train Layout",
        )
