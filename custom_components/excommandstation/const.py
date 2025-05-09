"""Constants for the EX-CommandStation integration."""

from logging import Logger, getLogger
from typing import Final

LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "excommandstation"

# Deault port used in the EX-CommandStation
DEFAULT_PORT: Final = 2560

# Timeouts for various operations
CONNECTION_TIMEOUT: Final = 5.0
RESPONSE_TIMEOUT: Final = 5.0
HEARTBEAT_TIMEOUT: Final = 30.0
MAX_BACKOFF_TIME: Final = 60.0

# Minimum supported version of the EX-CommandStation
MIN_SUPPORTED_VERSION: Final[tuple[int, ...]] = (5, 4, 0)

# Dispatcher signals
SIGNAL_CONNECTED = "connected"
SIGNAL_DISCONNECTED = "disconnected"
SIGNAL_DATA_PUSHED = "data_pushed"
