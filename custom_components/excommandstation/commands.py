"""Command definitions for the ExCommandStation integration."""

from typing import Final

# Command and response constants
CMD_STATE: Final[str] = "<s>"
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
