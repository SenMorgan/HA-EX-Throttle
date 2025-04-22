"""EX-CommandStation Client for Home Assistant integration."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.exceptions import InvalidStateError

from .commands import (
    CMD_EXCS_SYS_INFO,
    RESP_EXCS_SYS_INFO_PREFIX,
    RESP_EXCS_SYS_INFO_REGEX,
    command_set_function,
    command_write_cv,
)
from .const import DEFAULT_TIMEOUT, LOGGER, MIN_SUPPORTED_VERSION

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import ServiceCall


class EXCSError(InvalidStateError):
    """Base class for all exceptions raised by the EX-CommandStation integration."""


class EXCSConnectionError(EXCSError):
    """Exception to indicate a general connection error."""


class EXCSInvalidResponseError(EXCSError):
    """Exception to indicate an invalid response from the EX-CommandStation."""


class EXCSVersionError(EXCSError):
    """Exception to indicate an unsupported version of the EX-CommandStation."""


@dataclass
class EXCSSystemInfo:
    """
    Data class to hold system information of the EX-CommandStation.

    See: https://dcc-ex.com/reference/software/command-summary-consolidated.html#s-request-the-dcc-ex-version-and-hardware-info-along-with-listing-defined-turnouts
    """

    version: str = ""
    processor_type: str = ""
    motor_controller: str = ""
    build_number: str = ""
    version_parsed: tuple[int, ...] = field(default_factory=tuple)


class EXCommandStationClient:
    """Client for communicating with the EX-CommandStation."""

    def __init__(self, host: str, port: int) -> None:
        """Initialize the EX-CommandStation client."""
        self.host = host
        self.port = port
        self.connected = False
        self.system_info = EXCSSystemInfo()
        self._reader = None
        self._writer = None
        self._callbacks = set()
        self._listen_task = None
        self._listener_ready_event = asyncio.Event()
        self._response_futures: dict[str, asyncio.Future] = {}

    @classmethod
    def parse_version(cls, version_str: str) -> tuple[int, ...]:
        """Parse a version string into a tuple of integers."""
        return tuple(int(part) for part in version_str.split("."))

    async def async_setup(self) -> None:
        """Set up the EX-CommandStation client."""
        LOGGER.debug("Setting up EX-CommandStation client")
        if not self.connected:
            await self.connect()

        # Fetch EX-CommandStation system info and validate version
        await self._get_excs_system_info()
        await self._validate_excs_version()

    async def connect(self) -> None:
        """Connect to the EX-CommandStation."""
        LOGGER.debug("Connecting to EX-CommandStation at %s:%s", self.host, self.port)
        try:
            self._reader, self._writer = await asyncio.open_connection(
                self.host, self.port
            )
            LOGGER.debug("Connected to EX-CommandStation, initializing listener...")
            self.connected = True

            # Start the listener task
            if not self._listen_task:
                self._listen_task = asyncio.create_task(self._listen())
                LOGGER.debug("Listener task started")

            # Wait for the listener to be ready
            await asyncio.wait_for(
                self._listener_ready_event.wait(), timeout=DEFAULT_TIMEOUT
            )

        except TimeoutError:
            msg = "Timeout while connecting to EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except OSError as err:
            msg = (
                f"Failed to connect to EX-CommandStation at {self.host}:{self.port}: "
                f"{err}"
            )
            raise EXCSConnectionError(msg) from err

        if self._reader is None or self._writer is None:
            msg = "Reader or writer not initialized properly"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg)

        LOGGER.debug("Successfully connected to EX-CommandStation")

    async def disconnect(self) -> None:
        """Disconnect from the EX-CommandStation."""
        self.connected = False  # Mark as disconnected first to signal the listener loop

        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                LOGGER.warning("Waiting for listener task to finish")
                await asyncio.wait_for(self._listen_task, timeout=2)

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError as err:
                # Handle potential errors during writer close
                LOGGER.debug("Error closing writer: %s", err)

        LOGGER.debug("Disconnected from EX-CommandStation")

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the EX-CommandStation."""
        if self._writer:
            with contextlib.suppress(OSError):
                self._writer.close()
                await self._writer.wait_closed()
        self._writer = None
        self._reader = None
        self.connected = False

        LOGGER.debug("Attempting to reconnect to EX-CommandStation")
        retries = 0
        while not self.connected:
            try:
                await self.connect()
                LOGGER.info(
                    "Reconnected to EX-CommandStation after %d retries", retries
                )
                # Send system info request to update entities states after reconnect
                await self.send_command(CMD_EXCS_SYS_INFO)
            except EXCSConnectionError as err:
                retries += 1
                LOGGER.warning("Reconnect attempt %d failed: %s", retries, err)
                await asyncio.sleep(min(2**retries, 30))  # Exponential backoff

    def register_callback(self, callback: Callable) -> None:
        """Register a callback to be called when a message is received."""
        self._callbacks.add(callback)

    def unregister_callback(self, callback: Callable) -> None:
        """Unregister a callback."""
        self._callbacks.discard(callback)

    async def send_command(self, command: str) -> None:
        """Send a command to the EX-CommandStation."""
        LOGGER.debug("Sending command: %s", command)
        if not self.connected or self._writer is None:
            msg = "Cannot send command: not connected to EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg)

        # Send the command to the EX-CommandStation
        self._writer.write((command + "\r\n").encode("ascii"))
        await self._writer.drain()

    async def send_command_with_response(
        self, command: str, expected_prefix: str
    ) -> str:
        """Send a command and wait for a response with the expected prefix."""
        # Create a future to wait for the response and store it in the dictionary
        future = asyncio.get_running_loop().create_future()
        self._response_futures[expected_prefix] = future

        await self.send_command(command)

        # Wait for the response or timeout and remove the future from the dictionary
        response = await asyncio.wait_for(future, timeout=DEFAULT_TIMEOUT)
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

    async def handle_set_loco_function(self, call: ServiceCall) -> None:
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

    async def _get_excs_system_info(self) -> None:
        """Request system information from the EX-CommandStation."""
        if not self.connected:
            raise EXCSConnectionError

        LOGGER.debug("Requesting EX-CommandStation system info")
        try:
            response = await self.send_command_with_response(
                CMD_EXCS_SYS_INFO, RESP_EXCS_SYS_INFO_PREFIX
            )
        except TimeoutError:
            msg = "Timeout waiting for system info response from EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except EXCSError as err:
            LOGGER.error("Error while getting system info: %s", err)
            raise

        # Parse the response and extract system information
        if match := RESP_EXCS_SYS_INFO_REGEX.match(response):
            self.system_info.version = match.group("version")
            self.system_info.version_parsed = self.parse_version(match.group("version"))
            self.system_info.processor_type = match.group("microprocessor")
            self.system_info.motor_controller = match.group("motor_controller")
            self.system_info.build_number = match.group("build_number") or "unknown"

            LOGGER.info(
                "EX-CommandStation version: %s, processor: %s, motor controller: %s",
                self.system_info.version,
                self.system_info.processor_type,
                self.system_info.motor_controller,
            )
        else:
            msg = f"Invalid response from EX-CommandStation on system info: {response}"
            LOGGER.error(msg)
            raise EXCSInvalidResponseError(msg)

    async def _validate_excs_version(self) -> None:
        """Check the version of the EX-CommandStation."""
        # Check if the version is parsed
        if not self.system_info.version_parsed:
            msg = "EX-CommandStation version has not been retrieved yet"
            LOGGER.error(msg)
            raise EXCSVersionError(msg)

        # Check if the version is supported
        if self.system_info.version_parsed < MIN_SUPPORTED_VERSION:
            min_ver_str = ".".join(str(x) for x in MIN_SUPPORTED_VERSION)
            msg = (
                f"Unsupported EX-CommandStation version: {self.system_info.version}. "
                f"Min supported: {min_ver_str}"
            )
            LOGGER.error(msg)
            raise EXCSVersionError(msg)

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
                    line = await self._reader.readline()
                    if not line:
                        LOGGER.warning("Connection closed by EX-CommandStation")
                        await self._reconnect()
                        continue

                    message = line.decode("ascii").strip()
                    LOGGER.debug("Received message: %s", message)

                    # Message was awaited via send_command_with_response()
                    if await self._handle_future_response(message):
                        continue

                    # Message is a push update — notify subscribers
                    self._notify(message)

                except OSError as err:
                    LOGGER.error("Error while reading from EX-CommandStation: %s", err)
                    await self._reconnect()
                except asyncio.CancelledError:
                    LOGGER.debug("Listener task cancelled")
                    break
        finally:
            self._listener_ready_event.clear()
            LOGGER.debug("Listener task cleanup complete")

    async def _handle_future_response(self, message: str) -> bool:
        """Handle a response if it matches a registered future."""
        for prefix, future in self._response_futures.items():
            if message.startswith(prefix) and not future.done():
                future.set_result(message)
                LOGGER.debug("Future response set for prefix: %s", prefix)
                return True

        return False

    def _notify(self, message: str) -> None:
        """Notify all registered callbacks with the received message."""
        for cb in self._callbacks:
            cb(message)
