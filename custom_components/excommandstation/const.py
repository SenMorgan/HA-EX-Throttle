"""Constants for the EX‑CommandStation integration."""

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "excommandstation"
DEFAULT_PORT: Final = 2560

# Command and response constants
CMD_STATE: Final[str] = "<s>"
CMD_TRACKS_ON: Final[str] = "<1>"
CMD_TRACKS_OFF: Final[str] = "<0>"
RESP_STATE_ON: Final[str] = "<p1>"
RESP_STATE_OFF: Final[str] = "<p0>"
