"""Base client for EX-CommandStation with core connectivity functionality."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .commands import CMD_EXCS_SYS_INFO
from .const import (
    DEFAULT_TIMEOUT,
    DOMAIN,
    LISTENER_TIMEOUT,
    LOGGER,
    SIGNAL_CONNECTED,
    SIGNAL_DATA_PUSHED,
    SIGNAL_DISCONNECTED,
)
from .excs_exceptions import EXCSConnectionError, EXCSInvalidResponseError

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant


class EXCSBaseClient:
    """Base client for EX-CommandStation with core connectivity functionality."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the EX-CommandStation base client."""
        self.host = host
        self.port = port
        self.connected = False
        self._hass = hass
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._listen_task = None
        self._listener_ready_event = asyncio.Event()
        self._response_futures: dict[str, asyncio.Future] = {}

    async def connect(self) -> None:
        """Connect to the EX-CommandStation."""
        LOGGER.debug("Connecting to EX-CommandStation at %s:%s", self.host, self.port)

        # Already connected
        if self.connected and self._reader is not None and self._writer is not None:
            return

        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            LOGGER.debug("Connected to EX-CommandStation, initializing listener...")
            # Mark as connected and notify entities
            self._notify_connection_state(connected=True)

            # Start the listener task
            if self._listen_task is None or self._listen_task.done():
                self._listen_task = asyncio.create_task(self._listen())
                LOGGER.debug("Listener task started")

            # Wait for the listener to be ready
            await asyncio.wait_for(
                self._listener_ready_event.wait(), timeout=DEFAULT_TIMEOUT
            )

        except TimeoutError as err:
            msg = "Timeout while connecting to EX-CommandStation"
            LOGGER.error(msg)
            self._notify_connection_state(connected=False, exc=err)
            raise EXCSConnectionError(msg) from None
        except OSError as err:
            msg = (
                f"Failed to connect to EX-CommandStation at {self.host}:{self.port}: "
                f"{err}"
            )
            self._notify_connection_state(connected=False, exc=err)
            raise EXCSConnectionError(msg) from err

        if self._reader is None or self._writer is None:
            msg = "Reader or writer not initialized properly"
            LOGGER.error(msg)
            self._notify_connection_state(connected=False, exc=EXCSConnectionError(msg))
            raise EXCSConnectionError(msg)

        LOGGER.debug("Successfully connected to EX-CommandStation")

    async def disconnect(self) -> None:
        """Disconnect from the EX-CommandStation."""
        LOGGER.debug("Disconnecting from EX-CommandStation")

        # Cancel listener task
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._listen_task, timeout=2)

        # Close writer
        if self._writer:
            with contextlib.suppress(OSError):
                self._writer.close()
                await self._writer.wait_closed()

        self._reader = None
        self._writer = None
        self._listen_task = None

        # Update state and notify entities
        self._notify_connection_state(
            connected=False, exc=EXCSConnectionError("Disconnected")
        )

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the EX-CommandStation with exponential backoff."""
        await self.disconnect()

        LOGGER.debug("Attempting to reconnect to EX-CommandStation...")
        retries = 0
        max_backoff = 30  # Maximum backoff interval in seconds

        while not self.connected:
            try:
                await self.connect()
                LOGGER.info(
                    "Reconnected to EX-CommandStation after %d attempts", retries + 1
                )

                # Send system info request to update entities states after reconnect
                await self.send_command(CMD_EXCS_SYS_INFO)

            except EXCSConnectionError as err:
                retries += 1
                backoff = min(2**retries, max_backoff)
                LOGGER.warning(
                    "Reconnect attempt %d failed: %s. Retrying in %d seconds",
                    retries,
                    err,
                    backoff,
                )
                await asyncio.sleep(backoff)

    def dispatch_signal(self, signal: str, *args: Any) -> None:
        """Dispatch a signal to all registered callbacks."""
        signal = f"{DOMAIN}_{self.host}_{signal}"
        async_dispatcher_send(self._hass, signal, *args)

    def connect_signal(
        self, signal: str, callback: Callable[..., Any]
    ) -> Callable[[], None]:
        """Connect a callback to a signal."""
        signal = f"{DOMAIN}_{self.host}_{signal}"
        return async_dispatcher_connect(self._hass, signal, callback)

    def _notify_connection_state(
        self, *, connected: bool, exc: Exception | None = None
    ) -> None:
        """Notify all registered callbacks of connection state change."""
        if connected != self.connected:
            self.connected = connected
            if connected:
                self.dispatch_signal(SIGNAL_CONNECTED)
            else:
                self.dispatch_signal(SIGNAL_DISCONNECTED, exc)

    async def send_command(self, command: str) -> None:
        """Send a command to the EX-CommandStation."""
        LOGGER.debug("Sending command: %s", command)
        if not self.connected or self._writer is None:
            msg = "Cannot send command: not connected to EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg)

        # Send the command to the EX-CommandStation
        try:
            self._writer.write((f"<{command}>\n").encode("ascii"))
            await self._writer.drain()
        except OSError as err:
            msg = f"Error sending command to EX-CommandStation: {err}"
            LOGGER.error(msg)
            self._notify_connection_state(connected=False, exc=err)
            raise EXCSConnectionError(msg) from err

    async def send_command_with_response(
        self, command: str, expected_prefix: str
    ) -> str:
        """Send a command and wait for a response with the expected prefix."""
        # Create a future to wait for the response and store it in the dictionary
        future = asyncio.get_running_loop().create_future()
        self._response_futures[expected_prefix] = future

        await self.send_command(command)

        # Wait for the response or timeout and remove the future from the dictionary
        try:
            response = await asyncio.wait_for(future, timeout=DEFAULT_TIMEOUT)
        finally:
            self._response_futures.pop(expected_prefix, None)

        # Check if the response starts with the expected prefix
        if not response.startswith(expected_prefix):
            msg = (
                f"Unexpected response from EX-CommandStation: {response}. "
                f"Expected prefix: {expected_prefix}"
            )
            LOGGER.error(msg)
            raise EXCSInvalidResponseError(msg)

        return response

    async def _listen(self) -> None:
        """Listen for incoming messages from the EX-CommandStation."""
        self._listener_ready_event.set()  # Notify that the listener task is ready
        LOGGER.debug("Listener started")

        try:
            while True:
                if not self.connected or self._reader is None:
                    LOGGER.warning("Listener task detected disconnection")
                    await self._reconnect()
                    continue

                try:
                    # Read a line from the EX-CommandStation
                    line = await asyncio.wait_for(
                        self._reader.readline(), timeout=LISTENER_TIMEOUT
                    )
                    if not line:
                        LOGGER.warning("Connection closed by EX-CommandStation")
                        await self._reconnect()
                        continue

                    message = line.decode("ascii").strip()
                    self._parse_message(message)

                except TimeoutError:
                    LOGGER.warning("Listener timeout, reconnecting...")
                    await self._reconnect()
                except OSError as err:
                    LOGGER.error("Error while reading from EX-CommandStation: %s", err)
                    await self._reconnect()
                except asyncio.CancelledError:
                    LOGGER.debug("Listener task cancelled")
                    break
        finally:
            self._listener_ready_event.clear()
            LOGGER.debug("Listener task cleanup complete")

    def _parse_message(self, message: str) -> None:
        """Parse incoming messages from the EX-CommandStation."""
        LOGGER.debug("Received message: %s", message)

        # Check if message start with "<" and ends with ">"
        if not (message.startswith("<") and message.endswith(">")):
            LOGGER.warning("Invalid message format from EX-CommandStation: %s", message)
            return

        # Remove the angle brackets
        message = message[1:-1]

        # Check if message is empty or indicates failure
        if message == "":
            LOGGER.warning("Empty message received from EX-CommandStation")
            return

        # Message was awaited via send_command_with_response()
        if self._handle_future_response(message):
            return

        # Message is a push update — notify subscribers
        self.dispatch_signal(SIGNAL_DATA_PUSHED, message)

    def _handle_future_response(self, message: str) -> bool:
        """Handle a response if it matches a registered future."""
        for prefix, future in self._response_futures.items():
            if message.startswith(prefix) and not future.done():
                future.set_result(message)
                LOGGER.debug("Future response set for prefix: %s", prefix)
                return True

        return False
