"""Command definitions for the ExCommandStation integration."""

import re
from typing import Final

# Regular expression for parsing EX-CommandStation system information
# https://dcc-ex.com/reference/software/command-summary-consolidated.html#s-request-the-dcc-ex-version-and-hardware-info-along-with-listing-defined-turnouts
RESP_EXCS_SYS_INFO_PREFIX: Final[str] = "<iDCC-EX"
RESP_EXCS_SYS_INFO_REGEX: Final[re.Pattern] = re.compile(
    # Response format per docs:
    #   <iDCCEX version / microprocessorType / MotorControllerType / buildNumber>
    # Response example per practice:
    #   <iDCC-EX V-5.4.8 / ESP32 / STANDARD_MOTOR_SHIELD G-c389fe9>
    r"<iDCC-EX V-(?P<version>\d+\.\d+\.\d+) / "
    r"(?P<microprocessor>[^/]+) / "
    r"(?P<motor_controller>[^ ]+) "
    r"(?P<build_number>G-[a-f0-9]+)>"
)

# Command and response constants
CMD_EXCS_SYS_INFO: Final[str] = "<s>"
CMD_TRACKS_ON: Final[str] = "<1>"
CMD_TRACKS_OFF: Final[str] = "<0>"
RESP_TRACKS_ON: Final[str] = "<p1>"
RESP_TRACKS_OFF: Final[str] = "<p0>"


def command_set_function(addr: int, func_num: int, value: int) -> str:
    """Set a locomotive function (e.g., headlights, sound) state."""
    return f"<F {addr} {func_num} {value}>"


def command_write_cv(addr: int, cv: int, value: int) -> str:
    """Write a value to a locomotive CV on Main track."""
    return f"<w {addr} {cv} {value}>"
