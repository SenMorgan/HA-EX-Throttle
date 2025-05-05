"""Data update coordinator for EX-CommandStation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, LOGGER
from .excs_exceptions import EXCSError
from .roster import RosterEntry

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .excs_client import EXCommandStationClient


class LocoUpdateCoordinator(DataUpdateCoordinator[RosterEntry]):
    """Class to manage throttle updates for a locomotive."""

    def __init__(
        self, hass: HomeAssistant, client: EXCommandStationClient, loco: RosterEntry
    ) -> None:
        """Initialize the locomotive update coordinator."""
        super().__init__(
            hass,
            logger=LOGGER,
            name=f"{DOMAIN}_loco_{loco.id}",
            update_interval=None,  # Updates come from EXCommandStation push messages
            always_update=False,  # Do not update on every tick
        )
        self._client = client
        self._loco = loco

        # Register to receive push messages
        self._client.register_push_callback(self._handle_push)
        self._client.register_connection_callback(self._handle_connection_state)

    async def _request_update(self) -> None:
        """Request an update of the locomotive state after reconnection."""
        try:
            await self._client.send_command(self._loco.get_status_cmd())
        except EXCSError as err:
            LOGGER.warning("Error requesting loco update after reconnection: %s", err)

    @callback
    def _handle_connection_state(self, connected: bool) -> None:  # noqa: FBT001
        """Handle connection state changes."""
        if not connected:
            self.async_set_update_error(
                UpdateFailed(
                    f"Connection to EX-CommandStation lost for loco {self._loco.id}"
                )
            )
        else:
            # If reconnected, request a fresh update
            self.hass.async_create_task(self._request_update())

    @callback
    def _handle_push(self, message: str) -> None:
        """Process throttle messages for this locomotive."""
        if not message.startswith(self._loco.recv_prefix):
            # Ignore messages not related to this locomotive
            return

        try:
            # Process the message and update locomotive state
            self._loco.process_throttle_response(message)
            self.async_set_updated_data(self._loco)

        except EXCSError as err:
            LOGGER.error("Error parsing throttle response: %s", err)
