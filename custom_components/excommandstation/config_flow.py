"""Config flow for the EX‑CommandStation integration."""

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.const import CONF_BASE, CONF_HOST, CONF_PORT, CONF_PROFILE_NAME

from .const import DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_PROFILE_NAME): str,
    }
)


class EXCommandStationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EX‑CommandStation."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a flow initiated by the user."""
        errors = {}
        if user_input is not None:
            # Check if we already have this station configured
            unique_id = f"{user_input[CONF_HOST]}:{user_input[CONF_PORT]}"
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            error = await self._validate_connection(user_input)
            if error is None:
                # If the connection is successful, proceed to create the entry
                title = (
                    user_input[CONF_PROFILE_NAME]
                    if user_input.get(CONF_PROFILE_NAME)
                    else f"EX-CommandStation on {user_input[CONF_HOST]}"
                )
                return self.async_create_entry(
                    title=title,
                    data=user_input,
                )

            # If the connection fails, show an error message
            errors[CONF_BASE] = error
            return self.async_show_form(
                step_id="user",
                data_schema=self.add_suggested_values_to_schema(
                    USER_SCHEMA, user_input
                ),
                errors=errors,
            )

        # If no user input, show the form
        return self.async_show_form(
            step_id="user",
            data_schema=USER_SCHEMA,
        )

    async def _validate_connection(self, user_input: dict[str, Any]) -> str | None:
        """Validate the connection to the EX-CommandStation."""

        host = user_input[CONF_HOST]
        port = user_input[CONF_PORT]

        # Check if the host is reachable
        try:
            reader, writer = await asyncio.open_connection(host, port)
            writer.close()
            await writer.wait_closed()
        except OSError as e:
            _LOGGER.error("Cannot connect to %s:%s - %s", host, port, e)
            return "cannot_connect"

        # If the connection is successful, return None
        _LOGGER.info("Successfully connected to %s:%s", host, port)
        return None
