"""Constants for the EX-CommandStation integration."""

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "excommandstation"
DEFAULT_PORT: Final = 2560
DEFAULT_TIMEOUT: Final = 5.0
MIN_SUPPORTED_VERSION: Final[tuple[int, ...]] = (5, 4, 0)
