"""Switch platform for EX-CommandStation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription

from .entity import EXCSEntity
from .turnout import EXCSTurnout, TurnoutState

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

    # Add turnout switches
    if client.turnouts:
        turnout_switches = [
            EXCSTurnoutSwitch(client, turnout) for turnout in client.turnouts
        ]
        async_add_entities(turnout_switches)


class EXCSTurnoutSwitch(EXCSEntity, SwitchEntity):
    """Representation of a turnout switch."""

    def __init__(self, client: EXCommandStationClient, turnout: EXCSTurnout) -> None:
        """Initialize the switch."""
        super().__init__(client)
        self._turnout = turnout
        self._attr_name = turnout.description
        self.entity_description = SwitchEntityDescription(
            key=f"turnout_{turnout.id}",
            icon="mdi:source-branch",
        )
        self._attr_unique_id = f"{client.host}_{self.entity_description.key}"
        # Assuming THROWN means the switch is on
        self._attr_is_on = turnout.state == TurnoutState.THROWN

    def _handle_push(self, message: str) -> None:
        """Handle incoming messages from the EX-CommandStation."""
        if message.startswith(self._turnout.recv_prefix):
            turnout_id, state = EXCSTurnout.parse_turnout_state(message)
            if turnout_id == self._turnout.id:  # Double-check the turnout ID
                LOGGER.debug("Turnout %d %s", turnout_id, state.name)
                # Update the state of the switch
                self._attr_is_on = state == TurnoutState.THROWN
                self.async_write_ha_state()

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the switch (set turnout to THROWN)."""
        await self._client.send_command(
            EXCSTurnout.toggle_turnout_cmd(self._turnout.id, TurnoutState.THROWN)
        )

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the switch (set turnout to CLOSED)."""
        await self._client.send_command(
            EXCSTurnout.toggle_turnout_cmd(self._turnout.id, TurnoutState.CLOSED)
        )


class EXCSTracksPowerSwitch(EXCSEntity, SwitchEntity):
    """Representation of the EX-CommandStation tracks power switch."""

    def __init__(self, client: EXCommandStationClient) -> None:
        """Initialize the switch."""
        super().__init__(client)
        self._attr_name = "Tracks Power"
        self.entity_description = SwitchEntityDescription(
            key="tracks_power",
            icon="mdi:power",
        )
        self._attr_unique_id = f"{client.host}_{self.entity_description.key}"

    def _handle_push(self, message: str) -> None:
        """Handle incoming messages from the EX-CommandStation."""
        if message == RESP_TRACKS_ON:
            LOGGER.debug("Tracks power ON")
            self._attr_is_on = True
            self.async_write_ha_state()
        elif message == RESP_TRACKS_OFF:
            LOGGER.debug("Tracks power OFF")
            self._attr_is_on = False
            self.async_write_ha_state()

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the switch."""
        await self._client.send_command(CMD_TRACKS_ON)

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the switch."""
        await self._client.send_command(CMD_TRACKS_OFF)
