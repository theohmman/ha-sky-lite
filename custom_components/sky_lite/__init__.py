from .const import DOMAIN

async def async_setup_entry(hass, entry):
    """Set up Sky Lite from a config entry."""
    # We change 'setup' to 'setups' and wrap "sensor" in brackets []
    await hass.config_entries.async_forward_entry_setups(entry, ["sensor"])
    return True

async def async_unload_entry(hass, entry):
    """Unload a config entry."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")