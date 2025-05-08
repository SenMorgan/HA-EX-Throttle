"""EX-CommandStation Client for Home Assistant integration."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)

from .commands import (
    CMD_EXCS_SYS_INFO,
    RESP_EXCS_SYS_INFO_PREFIX,
    RESP_EXCS_SYS_INFO_REGEX,
    command_write_cv,
)
from .const import (
    DEFAULT_TIMEOUT,
    DOMAIN,
    LISTENER_TIMEOUT,
    LOGGER,
    MIN_SUPPORTED_VERSION,
    SIGNAL_CONNECTED,
    SIGNAL_DATA_PUSHED,
    SIGNAL_DISCONNECTED,
)
from .excs_exceptions import (
    EXCSConnectionError,
    EXCSError,
    EXCSInvalidResponseError,
    EXCSVersionError,
)
from .roster import RosterConsts, RosterEntry
from .turnout import EXCSTurnout, EXCSTurnoutConsts

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant, ServiceCall


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

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the EX-CommandStation client."""
        self.host = host
        self.port = port
        self.connected = False
        self.system_info = EXCSSystemInfo()
        self.turnouts: list[EXCSTurnout] = []
        self.roster_entries: list[RosterEntry] = []
        self._hass = hass
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
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
        # Fetch the list of roster entries
        await self._get_roster_entries()

    async def async_shutdown(self) -> None:
        """Shutdown the EX-CommandStation client."""
        LOGGER.debug("Shutting down EX-CommandStation client")
        try:
            await self.disconnect()
        except EXCSError:
            LOGGER.exception("Error during shutdown of EX-CommandStation client")

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

    async def handle_write_cv(self, call: ServiceCall) -> None:
        """Handle the write CV service call."""
        address = int(call.data["address"])
        cv = int(call.data["cv"])
        value = int(call.data["value"])
        command = command_write_cv(address, cv, value)
        LOGGER.debug("Writing CV: address=%d, cv=%d, value=%d", address, cv, value)
        await self.send_command(command)

    async def _get_turnouts_list(self) -> list[str]:
        """Get the list of turnout IDs from the EX-CommandStation."""
        try:
            response = await self.send_command_with_response(
                EXCSTurnoutConsts.CMD_LIST_TURNOUTS,
                EXCSTurnoutConsts.RESP_LIST_PREFIX,
            )
            return EXCSTurnout.parse_turnout_ids(response)
        except TimeoutError:
            msg = "Timeout waiting for turnout list response"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except EXCSError as err:
            LOGGER.error("Error getting turnout list: %s", err)
            raise
        except Exception:
            LOGGER.exception("Unexpected error while getting turnout list")
            raise

    async def _get_turnout_details(self, turnout_id: str) -> EXCSTurnout:
        """Get details for a specific turnout ID."""
        try:
            response = await self.send_command_with_response(
                EXCSTurnoutConsts.CMD_GET_TURNOUT_DETAILS_FMT.format(id=turnout_id),
                EXCSTurnoutConsts.RESP_DETAILS_PREFIX_FMT.format(id=turnout_id),
            )
            return EXCSTurnout.from_detail_response(response)
        except TimeoutError:
            msg = f"Timeout waiting for turnout details for ID {turnout_id}"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except EXCSError as err:
            LOGGER.error("Error getting turnout detail: %s", err)
            raise
        except Exception:
            LOGGER.exception(
                "Unexpected error while getting turnout details for ID %s", turnout_id
            )
            raise

    async def _get_turnouts(self) -> None:
        """Request the list of turnouts from the EX-CommandStation."""
        if not self.connected:
            raise EXCSConnectionError

        LOGGER.debug("Requesting list of turnouts from EX-CommandStation")

        # Clear existing turnouts
        self.turnouts.clear()

        # Get list of turnout IDs
        turnout_ids = await self._get_turnouts_list()

        if not turnout_ids:
            LOGGER.debug("No turnouts found")
            return

        LOGGER.debug("Found turnout IDs: %s", " ".join(turnout_ids))

        # Get details for each turnout ID
        for turnout_id in turnout_ids:
            turnout = await self._get_turnout_details(turnout_id)
            self.turnouts.append(turnout)
            # Print representation of the turnout
            LOGGER.debug("Turnout detail: %s", turnout)

    async def _get_roster_ids(self) -> list[str]:
        """Get the list of roster entry IDs from the EX-CommandStation."""
        try:
            response = await self.send_command_with_response(
                RosterConsts.CMD_LIST_ROSTER_ENTRIES,
                RosterConsts.RESP_LIST_PREFIX,
            )
            return RosterEntry.parse_roster_ids(response)
        except TimeoutError:
            msg = "Timeout waiting for roster list response"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except EXCSError as err:
            LOGGER.error("Error getting roster list: %s", err)
            raise
        except Exception:
            LOGGER.exception("Unexpected error while getting roster list")
            raise

    async def _get_roster_entry_details(self, roster_id: str) -> RosterEntry:
        """Get details for a specific roster entry ID."""
        try:
            response = await self.send_command_with_response(
                RosterConsts.CMD_GET_ROSTER_DETAILS_FMT.format(cab_id=roster_id),
                RosterConsts.RESP_DETAILS_PREFIX_FMT.format(cab_id=roster_id),
            )
            return RosterEntry.from_detail_response(response)
        except TimeoutError:
            msg = f"Timeout waiting for roster details for ID {roster_id}"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from None
        except EXCSError as err:
            LOGGER.error("Error getting roster detail: %s", err)
            raise
        except Exception:
            LOGGER.exception(
                "Unexpected error while getting roster details for ID %s", roster_id
            )
            raise

    async def _get_roster_entries(self) -> None:
        """Request the list of roster entries from the EX-CommandStation."""
        if not self.connected:
            raise EXCSConnectionError

        LOGGER.debug("Requesting list of roster entries from EX-CommandStation")

        # Clear existing roster entries
        self.roster_entries.clear()

        # Get list of roster entry IDs
        roster_ids = await self._get_roster_ids()

        if not roster_ids:
            LOGGER.debug("No roster entries found")
            return

        LOGGER.debug("Found roster entry IDs: %s", ",".join(roster_ids))

        # Get details for each roster entry ID
        for raw_roster_id in roster_ids:
            roster_id = raw_roster_id.strip()
            if not roster_id:
                LOGGER.warning("Empty roster ID found, skipping")
                continue

            # Get details for the roster entry
            entry = await self._get_roster_entry_details(roster_id)
            self.roster_entries.append(entry)

            # Print representation of the roster entry
            LOGGER.debug("Roster entry detail: %s", entry)

    async def _get_excs_system_info(self) -> None:
        """Request system information from the EX-CommandStation."""
        if not self.connected:
            raise EXCSConnectionError

        LOGGER.debug("Requesting EX-CommandStation system info")
        try:
            response = await self.send_command_with_response(
                CMD_EXCS_SYS_INFO, RESP_EXCS_SYS_INFO_PREFIX
            )
        except TimeoutError as err:
            msg = "Timeout waiting for system info response from EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from err
        except EXCSError as err:
            LOGGER.error("Error while getting system info: %s", err)
            raise
        except Exception:
            LOGGER.exception("Unexpected error while getting system info")
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
        self.dispatch_signal(SIGNAL_DATA_PUSHED, message)

    def _handle_future_response(self, message: str) -> bool:
        """Handle a response if it matches a registered future."""
        for prefix, future in self._response_futures.items():
            if message.startswith(prefix) and not future.done():
                future.set_result(message)
                LOGGER.debug("Future response set for prefix: %s", prefix)
                return True

        return False
