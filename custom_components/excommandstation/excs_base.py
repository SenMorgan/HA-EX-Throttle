"""Base client for EX-CommandStation with core connectivity functionality."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .const import (
    CONNECTION_TIMEOUT,
    DOMAIN,
    HEARTBEAT_TIMEOUT,
    LOGGER,
    MAX_BACKOFF_TIME,
    RESPONSE_TIMEOUT,
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
        LOGGER.debug(
            "Initializing EX-CommandStation client with host: %s, port: %s", host, port
        )
        self.host = host
        self.port = port
        self.connected = False
        self._hass = hass
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._listener_task = None
        self._connected_event = asyncio.Event()
        self._response_futures: dict[str, asyncio.Future[str]] = {}
        self._futures_lock = asyncio.Lock()

        # Flag to control the running state of the client and reconnection attempts
        self._running = True

    async def connect(self) -> None:
        """Connect to the EX-CommandStation."""
        LOGGER.debug("Connecting to EX-CommandStation on %s:%s", self.host, self.port)
        if self._listener_task is None or self._listener_task.done():
            self._listener_task = self._hass.async_create_background_task(
                self._listener_loop(), name="EXCS Listener"
            )

        # Wait for the connection to be established
        if not self._connected_event.is_set():
            await asyncio.wait_for(
                self._connected_event.wait(), timeout=CONNECTION_TIMEOUT
            )
            LOGGER.debug(
                "Connected to EX-CommandStation on %s:%s", self.host, self.port
            )

    async def disconnect(self) -> None:
        """Disconnect from the EX-CommandStation."""
        LOGGER.debug("Disconnecting from EX-CommandStation...")
        self._running = False

        # Cancel listener task
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._listener_task, timeout=2)

        self._listener_task = None
        LOGGER.debug("Disconnected from EX-CommandStation")

    def dispatch_signal(self, signal: str, *args: Any) -> None:
        """Dispatch a signal to all registered callbacks."""
        signal = f"{DOMAIN}_{self.host}_{signal}"
        async_dispatcher_send(self._hass, signal, *args)

    def register_signal_handler(
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
                self._connected_event.set()
                self.dispatch_signal(SIGNAL_CONNECTED)
            else:
                self._connected_event.clear()
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
        async with self._futures_lock:
            self._response_futures[expected_prefix] = future

        await self.send_command(command)

        # Wait for the response or timeout and remove the future from the dictionary
        try:
            response = await asyncio.wait_for(future, timeout=RESPONSE_TIMEOUT)
        finally:
            async with self._futures_lock:
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

    async def _listener_loop(self) -> None:
        """
        Run connection and listener loop for the EX-CommandStation.

        This loop will attempt to connect to the EX-CommandStation and
        handle incoming messages. If the connection is lost, it will
        attempt to reconnect with exponential backoff.
        """
        retries = 0  # Count the number of connection attempts

        while self._running:
            try:
                self._reader, self._writer = await asyncio.open_connection(
                    self.host, self.port
                )

                # Reset retries on successful connection
                retries = 0

                # Mark as connected and notify entities
                self._notify_connection_state(connected=True)

                # Handle the stream of data
                await self.handle_stream()

            except (asyncio.CancelledError, KeyboardInterrupt):
                LOGGER.info("Stopping listener loop due to cancellation")
                self._notify_connection_state(
                    connected=False, exc=EXCSConnectionError("Listener loop cancelled")
                )
                break
            except (OSError, TimeoutError) as e:
                LOGGER.warning("Connection failed or timed out: %s", e)
                self._notify_connection_state(connected=False, exc=e)

                # Attempt to reconnect with exponential backoff
                retries += 1
                backoff = min(2**retries, MAX_BACKOFF_TIME)
                LOGGER.warning(
                    "Reconnecting in %d seconds (attempt %d)", backoff, retries
                )
                await asyncio.sleep(backoff)

        LOGGER.info("Listener loop stopped")

    async def handle_stream(self) -> None:
        """Handle the stream of data from the EX-CommandStation."""
        if self._reader is None or self._writer is None:
            msg = "Reader or writer not initialized"
            LOGGER.error(msg)
            self._notify_connection_state(connected=False, exc=EXCSConnectionError(msg))
            raise EXCSConnectionError(msg)

        try:
            LOGGER.debug("Listening for incoming messages from EX-CommandStation")
            while not self._reader.at_eof():
                # Avoid blocking indefinitely: EX-CommandStation sends heartbeat
                # messages, so we can set a timeout for reading
                line = await asyncio.wait_for(
                    self._reader.readline(), timeout=HEARTBEAT_TIMEOUT
                )
                if not line:
                    LOGGER.warning("Connection closed by EX-CommandStation")
                    break

                message = line.decode("ascii").strip()
                self._parse_message(message)

            # Handle EOF
            msg = "Connection closed by EX-CommandStation"
            LOGGER.info(msg)
            self._notify_connection_state(
                connected=False,
                exc=EXCSConnectionError(msg),
            )
        except TimeoutError:
            msg = "Heartbeat timeout"
            LOGGER.warning(msg)
            self._notify_connection_state(connected=False, exc=EXCSConnectionError(msg))
            # Do not raise an exception to reconnect immediately
        except (OSError, UnicodeDecodeError) as err:
            LOGGER.exception("Error while reading stream")
            self._notify_connection_state(connected=False, exc=err)
            # Do not raise an exception to reconnect immediately
        finally:
            # Close writer
            if self._writer:
                with contextlib.suppress(OSError):
                    self._writer.close()
                    await self._writer.wait_closed()

            # Reset reader and writer
            self._writer = None
            self._reader = None
            LOGGER.debug("Stream closed")

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
                LOGGER.debug("Processing awaited response with prefix: '%s'", prefix)
                return True

        return False
