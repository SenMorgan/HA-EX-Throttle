"""EX-CommandStation Client for Home Assistant integration."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .commands import command_set_function, command_write_cv
from .const import LOGGER

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import ServiceCall


class EXCommandStationError(Exception):
    """Base class for all exceptions raised by the EX-CommandStation integration."""


class EXCommandStationConnectionError(EXCommandStationError):
    """Exception to indicate a general connection error."""


class EXCommandStationClient:
    """Client for communicating with the EX-CommandStation."""

    def __init__(self, host: str, port: int) -> None:
        """Initialize the EX-CommandStation client."""
        self.host = host
        self.port = port
        self._reader = None
        self._writer = None
        self._callbacks = set()
        self._listen_task = None
        self.connected = False

    def register_callback(self, callback: Callable) -> None:
        """Register a callback to be called when a message is received."""
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable) -> None:
        """Unregister a callback."""
        self._callbacks.discard(callback)

    async def connect(self) -> None:
        """Connect to the EX-CommandStation."""
        LOGGER.debug("Connecting to EX-CommandStation at %s:%s", self.host, self.port)
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            LOGGER.debug("Connected to EX-CommandStation")
            self.connected = True
            self._listen_task = asyncio.create_task(self._listen())
        except OSError as e:
            msg = f"Failed to connect to EX-CommandStation at {self.host}:{self.port}: {e}"
            raise EXCommandStationConnectionError(msg) from e

    async def disconnect(self) -> None:
        """Disconnect from the EX-CommandStation."""
        LOGGER.debug("Disconnecting from EX-CommandStation")
        if self._writer:
            self._writer.close()
            await self._writer.wait_closed()
        if self._listen_task:
            self._listen_task.cancel()
        self.connected = False

    async def send_command(self, command: str) -> None:
        """Send a command to the EX-CommandStation."""
        LOGGER.debug("Sending command: %s", command)
        if not self.connected:
            LOGGER.warning("Not connected to EX-CommandStation")
            return
        if self._writer is None:
            LOGGER.warning("Can't send command, not connected")
            return
        self._writer.write((command + "\r\n").encode("ascii"))
        await self._writer.drain()

    async def handle_send_function(self, call: ServiceCall) -> None:
        """Handle the send function service call."""
        address = int(call.data["address"])
        func = int(call.data["function"])
        value = int(call.data["state"])  # Convert boolean state to int
        command = command_set_function(address, func, value)
        LOGGER.debug(
            "Sending function: address=%d, function=%d, value=%d", address, func, value
        )
        await self.send_command(command)

    async def handle_write_cv(self, call: ServiceCall) -> None:
        """Handle the write CV service call."""
        address = int(call.data["address"])
        cv = int(call.data["cv"])
        value = int(call.data["value"])
        command = command_write_cv(address, cv, value)
        LOGGER.debug("Writing CV: address=%d, cv=%d, value=%d", address, cv, value)
        await self.send_command(command)

    async def _listen(self) -> None:
        """Listen for incoming messages from the EX-CommandStation."""
        LOGGER.debug("Starting listener task")
        try:
            while True:
                if not self.connected or self._reader is None:
                    # If the connection is closed, break the loop
                    LOGGER.warning("Listener task cancelled, not connected")
                    break
                # Read a line from the EX-CommandStation
                line = await self._reader.readline()
                if not line:
                    LOGGER.warning("No data received, breaking listener loop")
                    break
                message = line.decode("ascii").strip()
                LOGGER.debug("Received: %s", message)
                self._notify(message)
        except asyncio.CancelledError:
            LOGGER.debug("Listener task cancelled")
        except OSError as e:
            LOGGER.exception("Error while reading from EX-CommandStation: %s", e)
        finally:
            await self.disconnect()
            LOGGER.info(
                "Disconnected from EX-CommandStation at %s:%s", self.host, self.port
            )

    def _notify(self, message: str) -> None:
        """Notify all registered callbacks with the received message."""
        for cb in self._callbacks:
            cb(message)
