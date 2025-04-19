"""Switch platform for EX-CommandStation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.helpers.device_registry import DeviceInfo

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .excs_client import EXCommandStationClient


from .const import (
    CMD_TRACKS_OFF,
    CMD_TRACKS_ON,
    DOMAIN,
    LOGGER,
    RESP_STATE_OFF,
    RESP_STATE_ON,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the EX-CommandStation switch platform."""
    client = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([EXCSTracksPowerSwitch(client)])


class EXCSTracksPowerSwitch(SwitchEntity):
    """Representation of the EX-CommandStation tracks power switch."""

    def __init__(self, client: EXCommandStationClient) -> None:
        """Initialize the switch."""
        super().__init__()
        self._client = client
        self._attr_is_on = False
        self._attr_unique_id = f"{client.host}_tracks_power"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client.host)},
            name="EX-CommandStation",
            manufacturer="DCC-EX",
            model="EX-CommandStation",
        )
        self.entity_description = SwitchEntityDescription(
            key="tracks_power",
            name="Tracks Power",
            icon="mdi:power",
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        self._client.register_callback(self._handle_push)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister callbacks."""
        self._client.unregister_callback(self._handle_push)

    def _handle_push(self, message: str) -> None:
        """Handle incoming messages from the EX-CommandStation."""
        if RESP_STATE_ON in message:
            LOGGER.debug("Received tracks state ON")
            self._attr_is_on = True
            self.async_write_ha_state()
        elif RESP_STATE_OFF in message:
            LOGGER.debug("Received tracks state OFF")
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the switch."""
        await self._client.send_command(CMD_TRACKS_ON)

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the switch."""
        await self._client.send_command(CMD_TRACKS_OFF)
