"""Config flow for the EX‑CommandStation integration."""

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_BASE, CONF_HOST, CONF_PORT, CONF_PROFILE_NAME
from slugify import slugify

from .const import DEFAULT_PORT, DOMAIN, LOGGER
from .excs_client import (
    EXCommandStationClient,
    EXCSConnectionError,
    EXCSError,
    EXCSVersionError,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_PROFILE_NAME): str,
    }
)


class EXCommandStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for EX‑CommandStation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        _errors = {}
        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            try:
                client = EXCommandStationClient(host=host, port=port)
                await client.async_setup()
                await client.disconnect()
            except EXCSConnectionError as e:
                LOGGER.error("Connection error: %s", e)
                _errors[CONF_BASE] = "cannot_connect"
            except EXCSVersionError as e:
                LOGGER.error("Unsupported version: %s", e)
                _errors[CONF_BASE] = "unsupported_version"
            except EXCSError as e:
                LOGGER.error("Unexpected error: %s", e)
                _errors[CONF_BASE] = "unknown"
            else:
                # If the connection is successful, proceed to create the entry
                LOGGER.info("Successfully connected to %s:%s", host, port)
                # Check if we already have this station configured
                unique_id = slugify(f"{host}:{port}")
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                # If the user provided a profile name, use it; otherwise, use the default
                title = (
                    user_input[CONF_PROFILE_NAME]
                    if user_input.get(CONF_PROFILE_NAME)
                    else f"EX-CommandStation on {host}"
                )
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

        # If no user input, show the form
        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
            errors=_errors,
        )
