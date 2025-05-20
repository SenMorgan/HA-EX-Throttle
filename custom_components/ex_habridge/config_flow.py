"""Config flow for the EX-CommandStation integration."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_BASE, CONF_HOST, CONF_PORT, CONF_PROFILE_NAME
from slugify import slugify

from .const import DEFAULT_PORT, DOMAIN, LOGGER
from .excs_client import EXCommandStationClient
from .excs_exceptions import EXCSConnectionError, EXCSError, EXCSVersionError

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_PROFILE_NAME): str,
    }
)


class EXCommandStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for EX-CommandStation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        _errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            # Check if we already have this station configured
            unique_id = slugify(f"{host}:{port}")
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            # Attempt to connect to the EX-CommandStation and validate the configuration
            try:
                client = EXCommandStationClient(self.hass, host, port)
                await client.async_validate_config()

                # Use provided profile name or fallback to default
                return self.async_create_entry(
                    title=user_input.get(
                        CONF_PROFILE_NAME, f"EX-CommandStation on {host}"
                    ),
                    data=user_input,
                )
            except TimeoutError:
                LOGGER.error("Connection timeout")
                _errors[CONF_BASE] = "cannot_connect"
            except EXCSConnectionError as e:
                LOGGER.error("Connection error: %s", e)
                _errors[CONF_BASE] = "cannot_connect"
            except EXCSVersionError as e:
                LOGGER.error("Unsupported version: %s", e)
                _errors[CONF_BASE] = "unsupported_version"
            except EXCSError as e:
                LOGGER.error("Unknown error: %s", e)
                _errors[CONF_BASE] = "unknown"
            finally:
                await client.async_shutdown()

        # If no user input, show the form
        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=_errors,
        )
