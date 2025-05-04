"""Roster entry class for EX-CommandStation."""

from __future__ import annotations

import re
from enum import Enum
from typing import Final

from .excs_exceptions import EXCSInvalidResponseError, EXCSValueError


class EXCSRosterConsts:
    """Constants for EX-CommandStation roster."""

    # From RCN-212, see: https://dcc-ex.com/reference/software/command-summary-consolidated.html#f-cab-funct-state-turn-loco-decoder-functions-on-or-off
    MAX_SUPPORTED_FUNCTION: Final[int] = 68

    # Commands
    CMD_LIST_ROSTER_ENTRIES: Final[str] = "JR"
    CMD_GET_ROSTER_DETAILS_FMT: Final[str] = "JR {cab_id}"
    CMD_GET_LOCO_STATE_FMT: Final[str] = "t {cab_id}"
    CMD_SET_LOCO_SPEED_FMT: Final[str] = "t {cab_id} {speed} {direction}"
    CMD_TOGGLE_LOCO_FUNCTION_FMT: Final[str] = "F {cab_id} {function_id} {state}"

    # Regular expressions and corresponding prefixes for parsing responses
    RESP_LIST_PREFIX: Final[str] = "jR"
    RESP_LIST_REGEX: Final[re.Pattern] = re.compile(
        r"jR\s+(?P<ids>(?:\d+(?:\s+\d+)*))?"
    )

    RESP_DETAILS_PREFIX_FMT: Final[str] = "jR {cab_id}"
    RESP_DETAILS_REGEX: Final[re.Pattern] = re.compile(
        r'jR\s+(?P<id>\d+)\s+"(?P<desc>[^"]*)"\s+"(?P<functions>[^"]*)"'
    )

    RESP_THROTTLE_PREFIX_FMT: Final[str] = "l {cab_id}"
    RESP_THROTTLE_REGEX: Final[re.Pattern] = re.compile(
        r"l\s+(?P<cab>\d+)\s+(?P<reg>\d+)\s+(?P<speed_byte>\d+)\s+(?P<function_map>\d+)"
    )


class RosterDirection(Enum):
    """Enum representing loco direction."""

    REVERSE = 0
    FORWARD = 1


class EXCSLocoFunctionCmd(Enum):
    """Enum representing loco function commands."""

    ON = 1
    OFF = 0


class EXCSLocoFunction:
    """Representation of a locomotive function."""

    # Prefix for momentary functions
    MOMENTARY_FUNCTION_PREFIX: Final[str] = "*"

    def __init__(self, function_id: int, label: str) -> None:
        """Initialize the function."""
        self.id = function_id
        self.state = False

        # Check if the function is momentary and format the label accordingly
        self.is_momentary = label.startswith(self.MOMENTARY_FUNCTION_PREFIX)
        formatted_label = label[1:] if self.is_momentary else label
        self.label = formatted_label or f"Function {self.id}"


class EXCSRosterEntry:
    """Representation of a roster entry (locomotive) in the EX-CommandStation."""

    def __init__(self, loco_id: int, description: str, functions_str: str = "") -> None:
        """Initialize the roster entry."""
        self.id = loco_id
        self.description = description or f"Locomotive {loco_id}"
        self.functions: dict[int, EXCSLocoFunction] = {}
        self.speed = 0
        self.direction = RosterDirection.FORWARD
        self.emergency_stop = False

        # Prefix to find out loco state in incoming messages
        self.recv_prefix = EXCSRosterConsts.RESP_THROTTLE_PREFIX_FMT.format(
            cab_id=self.id
        )

        # Parse functions from the functions string
        if functions_str:
            self._parse_functions(functions_str)

    def __repr__(self) -> str:
        """Return a string representation of the roster entry."""
        return (
            f"<EXCSRosterEntry id={self.id} "
            f"description='{self.description}' "
            f"speed={self.speed} "
            f"direction={self.direction.name} "
            f"num_functions={len(self.functions)}>"
        )

    def toggle_function_cmd(self, function_id: int, state: EXCSLocoFunctionCmd) -> str:
        """Construct a command to set the function state."""
        return EXCSRosterConsts.CMD_TOGGLE_LOCO_FUNCTION_FMT.format(
            cab_id=self.id, function_id=function_id, state=state.value
        )

    def _parse_functions(self, functions_str: str) -> None:
        """Parse functions from a functions string."""
        if not functions_str:
            return

        function_labels = functions_str.split("/")

        for function_id, label in enumerate(function_labels):
            if function_id > EXCSRosterConsts.MAX_SUPPORTED_FUNCTION:
                break  # No need to parse beyond the supported range

            if not label:
                continue  # Skip empty labels (e.g., from double slashes)

            # Create the function object and add it to the functions dictionary
            self.functions[function_id] = EXCSLocoFunction(function_id, label)

    def _parse_speed_byte(self, speed_byte: int) -> None:
        """
        Parse the speed byte from the throttle response and update variables.

        The speed byte is an 8-bit integer with the following bit structure:
        - Bit 0: Emergency stop (1 = emergency stop, 0 = normal operation)
        - Bits 1-6: Speed (0-127)
        - Bit 7: Direction (0 = reverse, 1 = forward)
        """
        self.emergency_stop = bool(speed_byte & 0x01)
        self.speed = speed_byte & 0x7E
        self.direction = RosterDirection((speed_byte >> 7) & 1)

    def process_throttle_response(self, message: str) -> None:
        """Update the roster entry from a throttle response."""
        match = EXCSRosterConsts.RESP_THROTTLE_REGEX.match(message)
        if not match:
            msg = f"Invalid throttle response: {message}"
            raise EXCSInvalidResponseError(msg)

        cab_id = int(match.group("cab"))
        speed_byte = int(match.group("speed_byte"))
        function_map = int(match.group("function_map"))

        # Check if the cab ID matches the roster entry ID
        if cab_id != self.id:
            msg = f"Cab ID {cab_id} does not match roster entry ID {self.id}"
            raise EXCSValueError(msg)

        # Parse speed byte and update speed, direction, and emergency stop state
        self._parse_speed_byte(speed_byte)

        # Update only known functions using the function bitmap
        for i in self.functions:
            # Extract the bit: 1 = ON, 0 = OFF
            self.functions[i].state = bool((function_map >> i) & 1)

    @classmethod
    def parse_roster_ids(cls, response: str) -> list[str]:
        """Parse roster IDs from a list roster response."""
        # Check for empty roster list
        if not response.removeprefix(EXCSRosterConsts.RESP_LIST_PREFIX):
            return []

        # Check for valid roster list response
        if match := EXCSRosterConsts.RESP_LIST_REGEX.match(response):
            roster_ids = match.group("ids")
            if roster_ids:
                return roster_ids.split()
            return []

        msg = f"Invalid response for roster list: {response}"
        raise EXCSInvalidResponseError(msg)

    @classmethod
    def from_detail_response(cls, response: str) -> EXCSRosterEntry:
        """Create a roster entry instance from a detail response."""
        if match := EXCSRosterConsts.RESP_DETAILS_REGEX.match(response):
            try:
                return cls(
                    loco_id=int(match.group("id")),
                    description=match.group("desc"),
                    functions_str=match.group("functions"),
                )
            except EXCSValueError as err:
                msg = f"Error parsing roster detail: {err}"
                raise EXCSValueError(msg) from err

        msg = f"Invalid roster details response: {response}"
        raise EXCSInvalidResponseError(msg)
