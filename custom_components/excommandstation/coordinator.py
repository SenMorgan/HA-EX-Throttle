"""Data update coordinator for EX-CommandStation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    DOMAIN,
    LOGGER,
    SIGNAL_CONNECTED,
    SIGNAL_DATA_PUSHED,
    SIGNAL_DISCONNECTED,
)
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

        # Register callbacks for connection and store unsubscribe functions
        self._unsub_callbacks = [
            self._client.connect_signal(SIGNAL_CONNECTED, self._on_connect),
            self._client.connect_signal(SIGNAL_DISCONNECTED, self._on_disconnect),
            self._client.connect_signal(SIGNAL_DATA_PUSHED, self._handle_push),
        ]

    async def _request_update(self) -> None:
        """Request an update of the locomotive state after reconnection."""
        try:
            await self._client.send_command(self._loco.get_status_cmd())
        except EXCSError as err:
            LOGGER.warning("Error requesting loco update after reconnection: %s", err)

    async def async_shutdown(self) -> None:
        """Unregister callbacks and clean up resources."""
        await super().async_shutdown()

        # Unsubscribe from all signals
        for unsub in self._unsub_callbacks:
            unsub()
        self._unsub_callbacks.clear()

    @callback
    def _on_connect(self) -> None:
        """Handle connection to the EX-CommandStation."""
        self.hass.async_create_task(self._request_update())

    @callback
    def _on_disconnect(self, exc: Exception) -> None:
        """Handle disconnection from the EX-CommandStation."""
        self.async_set_update_error(UpdateFailed(exc))

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
