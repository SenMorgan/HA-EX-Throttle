"""EX-CommandStation Client with configuration and data retrieval capabilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .commands import (
    CMD_EXCS_SYS_INFO,
    RESP_EXCS_SYS_INFO_PREFIX,
    RESP_EXCS_SYS_INFO_REGEX,
    RESP_TRACKS_OFF,
    RESP_TRACKS_ON,
)
from .const import LOGGER, MIN_SUPPORTED_VERSION, SIGNAL_DATA_PUSHED
from .excs_base import EXCSBaseClient
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

    from homeassistant.core import HomeAssistant


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


class EXCSConfigClient(EXCSBaseClient):
    """EX-CommandStation Client with configuration and data retrieval capabilities."""

    def __init__(self, hass: HomeAssistant, host: str, port: int) -> None:
        """Initialize the configuration client."""
        super().__init__(hass, host, port)
        self.system_info = EXCSSystemInfo()
        self.turnouts: list[EXCSTurnout] = []
        self.roster_entries: list[RosterEntry] = []
        self.initial_tracks_state: bool = False

    @classmethod
    def parse_version(cls, version_str: str) -> tuple[int, ...]:
        """Parse a version string into a tuple of integers."""
        return tuple(int(part) for part in version_str.split("."))

    async def _crate_initial_tracks_state_handler(self) -> None:
        """Create a one-time signal handler for the initial tracks state."""
        unsub_callback: Callable[..., Any]

        def one_time_track_state_handler(message: str) -> None:
            """Handle the initial tracks state message."""
            nonlocal unsub_callback

            if message == RESP_TRACKS_ON:
                LOGGER.debug("Initial tracks state: ON")
                self.initial_tracks_state = True
                unsub_callback()
            elif message == RESP_TRACKS_OFF:
                LOGGER.debug("Initial tracks state: OFF")
                self.initial_tracks_state = False
                unsub_callback()

        # Register a one-time signal handler for the initial track state
        unsub_callback = self.register_signal_handler(
            SIGNAL_DATA_PUSHED, one_time_track_state_handler
        )
        self.register_signal_handler(SIGNAL_DATA_PUSHED, one_time_track_state_handler)

    async def get_excs_system_info(self) -> None:
        """Request system information from the EX-CommandStation."""
        if not self.connected:
            msg = "Not connected to EX-CommandStation"
            raise EXCSConnectionError(msg)

        # Create a one-time signal handler for the initial tracks state
        await self._crate_initial_tracks_state_handler()

        LOGGER.debug("Requesting EX-CommandStation system info")
        try:
            response = await self.await_command_response(
                CMD_EXCS_SYS_INFO, RESP_EXCS_SYS_INFO_PREFIX
            )
        except TimeoutError as err:
            msg = "Timeout waiting for system info response from EX-CommandStation"
            LOGGER.error(msg)
            raise EXCSConnectionError(msg) from err
        except EXCSError:
            LOGGER.exception("Error while getting system info: %s")
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

    async def validate_excs_version(self) -> None:
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

    async def get_turnouts(self) -> None:
        """Request the list of turnouts from the EX-CommandStation."""
        if not self.connected:
            msg = "Not connected to EX-CommandStation"
            raise EXCSConnectionError(msg)

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

    async def _get_turnouts_list(self) -> list[str]:
        """Get the list of turnout IDs from the EX-CommandStation."""
        try:
            response = await self.await_command_response(
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
            response = await self.await_command_response(
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

    async def get_roster_entries(self) -> None:
        """Request the list of roster entries from the EX-CommandStation."""
        if not self.connected:
            msg = "Not connected to EX-CommandStation"
            raise EXCSConnectionError(msg)

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

    async def _get_roster_ids(self) -> list[str]:
        """Get the list of roster entry IDs from the EX-CommandStation."""
        try:
            response = await self.await_command_response(
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
            response = await self.await_command_response(
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
