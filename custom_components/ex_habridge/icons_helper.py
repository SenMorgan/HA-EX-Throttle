"""Function icon mapping for locomotive functions."""

from __future__ import annotations

from typing import Final

# Default icon for functions that don't match any keywords
DEFAULT_ICON: Final[str] = "cog-outline"

# Mapping of icons to lists of keywords
ICON_KEYWORDS_MAPPING: Final[dict[str, list[str]]] = {
    "account-voice": ["announcement"],
    "air-conditioner": ["conditioner", "air con"],
    "alert": ["emergency"],
    "bell-outline": ["bell"],
    "bomb": ["detinator"],
    "bulkhead-light": ["cabin", "interior"],
    "bullhorn-outline": ["horn", "horns"],
    "car-brake-hold": ["brake"],
    "car-light-high": ["headlight", "head light"],
    "car-shift-pattern": ["shift"],
    "door-sliding": ["doors"],
    "door": ["door"],
    "engine-outline": ["engine", "motor"],
    "fan": ["blower", "fan", "ventilator"],
    "fence": ["rail"],
    "fire": ["coal", "fire"],
    "lighthouse-on": ["beacon"],
    "lightning-bolt": ["flash"],
    "link-variant-off": ["uncouple"],
    "link-variant": ["coupler", "coupling"],
    "music": ["music"],
    "power-plug-outline": ["aux"],
    "smoke": ["smoke", "steam"],
    "speedometer-slow": ["creep", "slow", "shunt"],
    "speedometer": ["speed", "acceleration"],
    "track-light": ["inspection light", "inspection lights"],
    "transmission-tower": ["pantograph"],
    "turbine": ["compressor", "compressed"],
    "volume-high": ["sound", "volume", "loudspeaker"],
    "volume-off": ["mute"],
    "wall-sconce-flat": ["light", "taillight", "tail light"],
    "whistle-outline": ["whistle"],
    "wiper": ["wiper"],
}


def get_function_icon(function_label: str) -> str:
    """Get the MDI icon name for a function based on its label."""
    default_icon = DEFAULT_ICON
    label_lower = function_label.lower()

    for icon, keywords in ICON_KEYWORDS_MAPPING.items():
        if any(keyword in label_lower for keyword in keywords):
            return f"mdi:{icon}"

    return f"mdi:{default_icon}"
