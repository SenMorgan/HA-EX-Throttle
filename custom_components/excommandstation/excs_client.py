"""EX-CommandStation Client for Home Assistant integration."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .commands import (
    CMD_EXCS_SYS_INFO,
    RESP_EXCS_SYS_INFO_PREFIX,
    RESP_EXCS_SYS_INFO_REGEX,
    command_set_function,
    command_write_cv,
)
from .const import DEFAULT_TIMEOUT, LISTENER_TIMEOUT, LOGGER, MIN_SUPPORTED_VERSION
from .excs_exceptions import (
    EXCSConnectionError,
    EXCSError,
    EXCSInvalidResponseError,
    EXCSValueError,
    EXCSVersionError,
)
from .turnout import EXCSTurnout, EXCSTurnoutConsts

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import ServiceCall


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
        self.turnouts: list[EXCSTurnout] = []
        self._reader = None
        self._writer = None
        self._push_callbacks = set()
        self._connection_callbacks = set()
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
        # Fetch the list of turnouts
        await self._get_turnouts()

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

        except TimeoutError:
            msg = "Timeout while connecting to EX-CommandStation"
            LOGGER.error(msg)
            self._notify_connection_state(connected=False)
            raise EXCSConnectionError(msg) from None
        except OSError as err:
            msg = (
                f"Failed to connect to EX-CommandStation at {self.host}:{self.port}: "
                f"{err}"
            )
            self._notify_connection_state(connected=False)
            raise EXCSConnectionError(msg) from err

        if self._reader is None or self._writer is None:
            msg = "Reader or writer not initialized properly"
            LOGGER.error(msg)
            self._notify_connection_state(connected=False)
            raise EXCSConnectionError(msg)

        LOGGER.debug("Successfully connected to EX-CommandStation")

    async def disconnect(self) -> None:
        """Disconnect from the EX-CommandStation."""
        # Cancel listener task
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(self._listen_task, timeout=2)

        # Close writer
        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except OSError as err:
                LOGGER.debug("Error closing writer: %s", err)

        self._reader = None
        self._writer = None
        self._listen_task = None

        # Update state and notify entities
        self._notify_connection_state(connected=False)
        LOGGER.debug("Disconnected from EX-CommandStation")

    async def _reconnect(self) -> None:
        """Attempt to reconnect to the EX-CommandStation with exponential backoff."""
        # If we were previously connected, clean up
        if self._writer:
            with contextlib.suppress(OSError):
                self._writer.close()
                await self._writer.wait_closed()

        self._writer = None
        self._reader = None
        self._notify_connection_state(connected=False)

        LOGGER.info("Connection to EX-CommandStation lost, attempting to reconnect")
        retries = 0

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
                backoff = min(2**retries, 30)  # Exponential backoff, max 30 seconds
                LOGGER.warning(
                    "Reconnect attempt %d failed: %s. Retrying in %d seconds",
                    retries,
                    err,
                    backoff,
                )
                await asyncio.sleep(backoff)

    def register_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Register a callback to be called when the connection state changes."""
        self._connection_callbacks.add(callback)

        # Immediately notify of current state if connected
        if callback and self.connected:
            callback(self.connected)

    def unregister_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Unregister a connection state callback."""
        self._connection_callbacks.discard(callback)

    def _notify_connection_state(self, *, connected: bool) -> None:
        """Notify all registered callbacks of connection state change."""
        if connected != self.connected:
            self.connected = connected
            for callback in self._connection_callbacks:
                callback(connected=connected)

    def register_push_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback to be called when a push message is received."""
        self._push_callbacks.add(callback)

    def unregister_push_callback(self, callback: Callable[[str], None]) -> None:
        """Unregister a push message callback."""
        self._push_callbacks.discard(callback)

    async def send_command(self, command: str) -> None:
        """Send a command to the EX-CommandStation."""
        LOGGER.debug("Sending command: %s", command)
        if not self.connected or self._writer is None:
            msg = "Cannot send command: not connected to EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg)

        # Send the command to the EX-CommandStation
        self._writer.write((f"<{command}>\r\n").encode("ascii"))
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

    async def _get_turnouts(self) -> None:
        """Request the list of turnouts from the EX-CommandStation."""
        if not self.connected:
            raise EXCSConnectionError

        LOGGER.debug("Requesting list of turnouts from EX-CommandStation")
        try:
            response = await self.send_command_with_response(
                EXCSTurnoutConsts.CMD_LIST_TURNOUTS,
                EXCSTurnoutConsts.RESP_PREFIX,
            )
        except TimeoutError:
            msg = "Timeout waiting for turnout list response from EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except EXCSError as err:
            LOGGER.error("Error while getting turnout list: %s", err)
            raise

        # Handle the turnout list response here
        if match := EXCSTurnoutConsts.RESP_LIST_REGEX.match(response):
            turnout_ids = match.group("ids")
            if turnout_ids:
                LOGGER.info("Turnout IDs: %s", turnout_ids)
            else:
                LOGGER.info("No turnouts found")
                return
        else:
            msg = f"Invalid response from EX-CommandStation on turnout list: {response}"
            LOGGER.error(msg)
            raise EXCSInvalidResponseError(msg)

        # Send command to get detailed information about each turnout
        for turnout_id in turnout_ids.split():
            try:
                response = await self.send_command_with_response(
                    f"{EXCSTurnoutConsts.CMD_LIST_TURNOUTS} {turnout_id}>",
                    EXCSTurnoutConsts.RESP_PREFIX,
                )
            except TimeoutError:
                msg = f"Timeout waiting for turnout details from EX-CommandStation for ID {turnout_id}"
                LOGGER.error(msg)
                raise EXCSConnectionError(msg) from None
            except EXCSError as err:
                LOGGER.error("Error while getting turnout detail: %s", err)
                raise

            # Handle the turnout detail response here
            if match := EXCSTurnoutConsts.RESP_DETAILS_REGEX.match(response):
                try:
                    turnout = EXCSTurnout(
                        turnout_id=int(match.group("id")),
                        state=match.group("state"),
                        description=match.group("desc").strip('"'),
                    )
                    # Add the turnout to the list
                    self.turnouts.append(turnout)
                    # Print representation of the turnout
                    LOGGER.debug("Turnout detail: %s", turnout)
                except EXCSValueError as err:
                    LOGGER.error("Error parsing turnout detail: %s", err)
                    raise
            else:
                msg = f"Invalid response from EX-CommandStation on turnout detail: {response}"
                LOGGER.error(msg)
                raise EXCSInvalidResponseError(msg)

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
        self._notify(message)

    def _handle_future_response(self, message: str) -> bool:
        """Handle a response if it matches a registered future."""
        for prefix, future in self._response_futures.items():
            if message.startswith(prefix) and not future.done():
                future.set_result(message)
                LOGGER.debug("Future response set for prefix: %s", prefix)
                return True

        return False

    def _notify(self, message: str) -> None:
        """Notify all registered callbacks with the received message."""
        for cb in self._push_callbacks:
            try:
                cb(message)
            except EXCSError as err:
                LOGGER.error("Error notifying callback: %s", err)
