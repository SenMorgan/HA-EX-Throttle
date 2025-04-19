"""Command definitions for the ExCommandStation integration."""

from typing import Final

# Command and response constants
CMD_STATE: Final[str] = "<s>"
CMD_TRACKS_ON: Final[str] = "<1>"
CMD_TRACKS_OFF: Final[str] = "<0>"
RESP_TRACKS_ON: Final[str] = "<p1>"
RESP_TRACKS_OFF: Final[str] = "<p0>"
