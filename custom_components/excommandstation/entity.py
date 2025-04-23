"""EX-CommandStation entity base class."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN

if TYPE_CHECKING:
    from .excs_client import EXCommandStationClient


class EXCSEntity(Entity):
    """Base class for EX-CommandStation entities."""

    _client: EXCommandStationClient
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_info: DeviceInfo | None = None

    def __init__(self, client: EXCommandStationClient) -> None:
        """Initialize the entity."""
        self._client = client
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

    def _handle_connection_state(self, connected: bool) -> None:  # noqa: FBT001
        """Handle connection state changes."""
        self._attr_available = connected
        self.async_write_ha_state()

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self._client.register_push_callback(self._handle_push)
        self._client.register_connection_callback(self._handle_connection_state)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self._client.unregister_push_callback(self._handle_push)
        self._client.unregister_connection_callback(self._handle_connection_state)
