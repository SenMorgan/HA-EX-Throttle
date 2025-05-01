"""Turnout class for EX-CommandStation."""

from __future__ import annotations

import re
from enum import Enum
from typing import Final

from .excs_exceptions import EXCSInvalidResponseError, EXCSValueError


class EXCSTurnoutConsts:
    """Constants for EX-CommandStation turnout."""

    # Commands
    CMD_LIST_TURNOUTS: Final[str] = "JT"
    CMD_GET_TURNOUT_DETAILS_FMT: Final[str] = "JT {id}"
    CMD_TOGGLE_TURNOUT_FMT: Final[str] = "T {id} {state}"

    # Regular expressions and corresponding prefixes for parsing responses
    RESP_STATE_PREFIX_FMT: Final[str] = "H {id}"
    RESP_STATE_REGEX: Final[re.Pattern] = re.compile(r"H\s+(?P<id>\d+)\s+(?P<state>\d)")

    RESP_LIST_PREFIX: Final[str] = "jT"
    RESP_LIST_REGEX: Final[re.Pattern] = re.compile(r"jT\s+(?P<ids>(?:\d+(?:\s+\d+)*))")

    RESP_DETAILS_PREFIX_FMT: Final[str] = "jT {id}"
    RESP_DETAILS_REGEX: Final[re.Pattern] = re.compile(
        r'jT\s+(?P<id>\d+)\s+(?P<state>[CTX])(?:\s+(?P<desc>"[^"]*"))?'
    )


class TurnoutState(Enum):
    """Enum representing turnout states."""

    CLOSED = "C"  # straight
    THROWN = "T"  # diverging

    @classmethod
    def from_char(cls, value: str) -> TurnoutState:
        """Convert a character value (C or T) to a TurnoutState enum."""
        for state in cls:
            if state.value == value:
                return state
        # If no match found, raise an error
        msg = (
            f"Invalid turnout state: {value}. Expected one of: {[s.value for s in cls]}"
        )
        raise EXCSValueError(msg)

    @classmethod
    def from_digit(cls, value: str) -> TurnoutState:
        """Convert a digit value (0 or 1) to a TurnoutState enum."""
        if value.isdigit():
            value_int = int(value)
            if value_int == 0:
                return cls.CLOSED
            if value_int == 1:
                return cls.THROWN

        msg = (
            f"Invalid turnout state value: {value_int}. "
            f"Expected 0 (CLOSED) or 1 (THROWN)."
        )
        raise EXCSValueError(msg)


class EXCSTurnout:
    """Representation of a turnout in the EX-CommandStation."""

    def __init__(self, turnout_id: int, state: str, description: str) -> None:
        """Initialize the turnout."""
        self.id = turnout_id
        self.description = description or f"Turnout {turnout_id}"

        # Normalize state to enum
        self.state = TurnoutState.from_char(state)

        # Prefix to find out the turnout state in incoming messages
        self.recv_prefix = EXCSTurnoutConsts.RESP_STATE_PREFIX_FMT.format(id=self.id)

    def __repr__(self) -> str:
        """Return a string representation of the turnout."""
        return (
            f"<EXCSTurnout id={self.id} "
            f"state={self.state.name} "
            f"description='{self.description}'>"
        )

    @classmethod
    def set_turnout_cmd(cls, turnout_id: int, state: TurnoutState) -> str:
        """Construct a command to set the turnout state."""
        return EXCSTurnoutConsts.CMD_TOGGLE_TURNOUT_FMT.format(
            id=turnout_id, state=state.value
        )

    @classmethod
    def parse_turnout_state(cls, message: str) -> tuple[int, TurnoutState]:
        """Parse the turnout state from a message."""
        match = EXCSTurnoutConsts.RESP_STATE_REGEX.match(message)
        if not match:
            msg = f"Invalid turnout state message: {message}"
            raise EXCSInvalidResponseError(msg)
        turnout_id = int(match.group("id"))

        # Here the state is expected to be a digit
        state = TurnoutState.from_digit(match.group("state"))
        return turnout_id, state

    @classmethod
    def parse_turnout_ids(cls, response: str) -> list[str]:
        """Parse turnout IDs from a list turnouts response."""
        # Check for empty turnout list
        if not response.removeprefix(EXCSTurnoutConsts.RESP_LIST_PREFIX):
            return []

        # Check for valid turnout list response
        if match := EXCSTurnoutConsts.RESP_LIST_REGEX.match(response):
            turnout_ids = match.group("ids")
            if turnout_ids:
                return turnout_ids.split()
            return []

        msg = f"Invalid response for turnout list: {response}"
        raise EXCSInvalidResponseError(msg)

    @classmethod
    def from_detail_response(cls, response: str) -> EXCSTurnout:
        """Create a turnout instance from a detail response."""
        if match := EXCSTurnoutConsts.RESP_DETAILS_REGEX.match(response):
            try:
                return cls(
                    turnout_id=int(match.group("id")),
                    state=match.group("state"),
                    description=match.group("desc").strip('"')
                    if match.group("desc")
                    else "",
                )
            except EXCSValueError as err:
                msg = f"Error parsing turnout detail: {err}"
                raise EXCSValueError(msg) from err

        msg = f"Invalid response for turnout detail: {response}"
        raise EXCSInvalidResponseError(msg)
