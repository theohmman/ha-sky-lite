from .const import DOMAIN
from .coordinator import SkyLiteCoordinator
import logging

PLATFORMS = ["image", "sensor"]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry):
    """Set up Sky Lite from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # 1. Fire up the Coordinator Brain and do the first math calculation
    coordinator = SkyLiteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    
    # 2. Store the Brain in HA's memory for the map and sensor to use
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # 3. Forward the setup to the platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # 4. Listen for changes in the Configure menu
    entry.async_on_unload(entry.add_update_listener(update_listener))
    
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        # Remove the Brain from memory when uninstalled
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok

async def update_listener(hass, entry):
    """Handle options update by forcing a seamless background reload."""
    await hass.config_entries.async_reload(entry.entry_id)