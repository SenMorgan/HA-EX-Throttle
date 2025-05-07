"""
Custom integration to integrate EX-CommandStation with Home Assistant.

For more details about this integration, please refer to
https://github.com/SenMorgan/HA-CommandStation-EX
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady

from .const import DOMAIN
from .coordinator import LocoUpdateCoordinator
from .excs_client import (
    EXCommandStationClient,
    EXCSConnectionError,
    EXCSError,
    EXCSVersionError,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


PLATFORMS: list[Platform] = [
    # Platform.SENSOR,
    # Platform.BINARY_SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EX-CommandStation from a config entry."""
    host = entry.data[CONF_HOST]
    port = entry.data[CONF_PORT]

    client = EXCommandStationClient(host, port)

    try:
        await client.async_setup()
    except EXCSConnectionError as err:
        await client.async_shutdown()
        raise ConfigEntryNotReady from err
    except EXCSVersionError as err:
        await client.async_shutdown()
        raise ConfigEntryError from err
    except EXCSError as err:
        await client.async_shutdown()
        msg = f"Unexpected error: {err}"
        raise ConfigEntryError(msg) from err

    # Create coordinators for each locomotive
    coordinators = {}
    for loco in client.roster_entries:
        coordinator = LocoUpdateCoordinator(hass, client, loco)
        coordinators[loco.id] = coordinator

    # Store client and coordinators in hass data
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "client": client,
        "coordinators": coordinators,
    }

    # Load platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register services
    hass.services.async_register(DOMAIN, "write_cv", client.handle_write_cv)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    # Get data from hass.data
    data = hass.data[DOMAIN].get(entry.entry_id)
    if not data:
        return True

    client: EXCommandStationClient = data["client"]
    coordinators: dict[int, LocoUpdateCoordinator] = data["coordinators"]

    # Unregister services
    hass.services.async_remove(DOMAIN, "write_cv")

    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Shutdown coordinators
    for coordinator in coordinators.values():
        await coordinator.async_shutdown()

    # Disconnect client
    await client.async_shutdown()

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
