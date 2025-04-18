"""Switches for EX-CommandStation."""

import asyncio
import logging

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 5

SIGNAL_STATE_UPDATED = "dcc_ex_state_updated"

COMMAND_TRACKS_ON = "<1>"
COMMAND_TRACKS_OFF = "<0>"
COMMAND_STATE = "<s>"
RESPONSE_STATE_ON = "<p1>"
RESPONSE_STATE_OFF = "<p0>"


class DccExTrackPowerSwitch(SwitchEntity):
    """Representation of a DCC-EX track power switch."""

    def __init__(self, host, port, hass: HomeAssistant) -> None:
        """Initialize the switch."""
        super().__init__()
        self._host = host
        self._port = port
        self._hass = hass
        self._attr_name = "Track Power"
        self._attr_is_on = False
        self._reader_task = None

        # Add a unique ID
        self._attr_unique_id = f"dcc_ex_track_power_{host}_{port}"
        # Add device info
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"{host}:{port}")},
            name="EX‑CommandStation",
            manufacturer="DCC-EX",
            model="EX-CommandStation",
        )

    async def async_added_to_hass(self):
        """Register callbacks."""
        self.async_on_remove(
            async_dispatcher_connect(
                self._hass, SIGNAL_STATE_UPDATED, self._handle_state_update
            )
        )
        self._reader_task = self._hass.loop.create_task(self._reader_loop())

    async def async_will_remove_from_hass(self):
        """Unregister callbacks."""
        if self._reader_task:
            self._reader_task.cancel()

    async def _reader_loop(self):
        try:
            reader, writer = await asyncio.open_connection(self._host, self._port)
            writer.write((COMMAND_STATE + "\n").encode("ascii"))
            await writer.drain()

            while True:
                line = await reader.readline()
                if not line:
                    _LOGGER.debug("Connection closed by peer")
                    break
                decoded = line.decode("ascii", errors="ignore")
                _LOGGER.debug("Received line: %s", decoded)
                self._process_incoming(decoded)
        except asyncio.CancelledError:
            _LOGGER.debug("Reader task cancelled")
        except Exception:
            _LOGGER.exception("Error in reader loop")
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()
            _LOGGER.debug("Reader loop finished")

    def _process_incoming(self, data: str):
        """Process incoming data from the DCC-EX."""
        data = data.strip()
        _LOGGER.debug("Processing incoming data [%s]", data)

        if data == RESPONSE_STATE_ON:
            _LOGGER.info("Received state ON")
            self._attr_is_on = True
            async_dispatcher_send(self._hass, SIGNAL_STATE_UPDATED)
        elif data == RESPONSE_STATE_OFF:
            _LOGGER.info("Received state OFF")
            self._attr_is_on = False
            async_dispatcher_send(self._hass, SIGNAL_STATE_UPDATED)
        else:
            _LOGGER.debug("Unknown response: %s", data)

    @callback
    def _handle_state_update(self):
        self.async_schedule_update_ha_state()

    async def async_turn_on(self, **kwargs):
        """Turn the switch on."""
        await self._send(COMMAND_TRACKS_ON)

    async def async_turn_off(self, **kwargs):
        """Turn the switch off."""
        await self._send(COMMAND_TRACKS_OFF)

    async def _send(self, command: str):
        try:
            reader, writer = await asyncio.open_connection(self._host, self._port)
            writer.write((command + "\n").encode("ascii"))
            await writer.drain()
            writer.close()
            await writer.wait_closed()
        except Exception:
            _LOGGER.exception("Error while sending command: %s", command)
        finally:
            if writer:
                writer.close()
                await writer.wait_closed()

        _LOGGER.debug("Command sent: %s", command)
        _LOGGER.info("Command sent successfully: %s", command)


async def async_setup_entry(hass: HomeAssistant, config_entry, async_add_entities):
    """Set up EX-CommandStation switch from a config entry."""
    config = hass.data[DOMAIN][config_entry.entry_id]
    host = config["host"]
    port = config["port"]
    async_add_entities([DccExTrackPowerSwitch(host, port, hass)])
