from .const import DOMAIN
from .coordinator import SkyLiteCoordinator
from .data_manager import ConstellationManager
import logging

PLATFORMS = ["image", "sensor"]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    """Set up Sky Lite from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # 1. Load static GeoJSON data from disk ONCE per Home Assistant session
    if "static_manager" not in hass.data[DOMAIN]:
        manager = ConstellationManager(hass)
        await manager.async_update_data()
        hass.data[DOMAIN]["static_manager"] = manager

    # 2. Fire up the Coordinator Brain and do the first math calculation
    coordinator = SkyLiteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    # 3. Store the Brain in HA's memory for the map and sensor to use
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 4. Forward the setup to the platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # 5. Listen for changes in the Configure menu
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Remove the Brain from memory when uninstalled
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok

async def update_listener(hass, entry):
    """Handle options update by forcing a seamless background reload."""
    await hass.config_entries.async_reload(entry.entry_id)
