"""Exceptions for the EX-CommandStation integration."""

from homeassistant.exceptions import InvalidStateError


class EXCSError(InvalidStateError):
    """Base class for all exceptions raised by the EX-CommandStation integration."""


class EXCSConnectionError(EXCSError):
    """Exception to indicate a general connection error."""


class EXCSInvalidResponseError(EXCSError):
    """Exception to indicate an invalid response from the EX-CommandStation."""


class EXCSVersionError(EXCSError):
    """Exception to indicate an unsupported version of the EX-CommandStation."""


class EXCSValueError(EXCSError):
    """Exception to indicate an invalid value in the EX-CommandStation response."""


class EXCSArgumentError(EXCSError):
    """Exception to indicate an invalid argument in the EX-CommandStation command."""
