"""Switch platform for EX-CommandStation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.helpers.device_registry import DeviceInfo

from .entity import EXCSEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .excs_client import EXCommandStationClient


from .commands import (
    CMD_TRACKS_OFF,
    CMD_TRACKS_ON,
    RESP_TRACKS_OFF,
    RESP_TRACKS_ON,
)
from .const import DOMAIN, LOGGER


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the EX-CommandStation switch platform."""
    client = hass.data[DOMAIN][entry.entry_id]

    # Add tracks power switch
    async_add_entities([EXCSTracksPowerSwitch(client)])


class EXCSTracksPowerSwitch(EXCSEntity, SwitchEntity):
    """Representation of the EX-CommandStation tracks power switch."""

    def __init__(self, client: EXCommandStationClient) -> None:
        """Initialize the switch."""
        super().__init__(client)
        self._attr_name = "Tracks Power"
        self._attr_unique_id = f"{client.host}_tracks_power"
        self.entity_description = SwitchEntityDescription(
            key="tracks_power",
            icon="mdi:power",
        )

    def _handle_push(self, message: str) -> None:
        """Handle incoming messages from the EX-CommandStation."""
        if message == RESP_TRACKS_ON:
            LOGGER.debug("Received tracks state ON")
            self._attr_is_on = True
            self._attr_available = True
            self.async_write_ha_state()
        elif message == RESP_TRACKS_OFF:
            LOGGER.debug("Received tracks state OFF")
            self._attr_is_on = False
            self._attr_available = True
            self.async_write_ha_state()

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the switch."""
        await self._client.send_command(CMD_TRACKS_ON)

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the switch."""
        await self._client.send_command(CMD_TRACKS_OFF)
