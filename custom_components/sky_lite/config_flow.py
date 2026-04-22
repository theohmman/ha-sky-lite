from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol
from .const import *

class SkyLiteConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 2

    async def async_step_user(self, user_input=None):
        if self._async_current_entries(): 
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None: 
            return self.async_create_entry(title="Sky Lite", data=user_input)

        return self.async_show_form(
            step_id="user", 
            data_schema=vol.Schema({
                vol.Required("latitude", default=self.hass.config.latitude): vol.Coerce(float),
                vol.Required("longitude", default=self.hass.config.longitude): vol.Coerce(float),
                vol.Optional("elevation", default=self.hass.config.elevation): vol.Coerce(float),
            })
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry): 
        # FIX: Removed config_entry from the parentheses
        return SkyLiteOptionsFlowHandler()


class SkyLiteOptionsFlowHandler(config_entries.OptionsFlow):
    
    # FIX: The __init__ method has been completely removed
    
    async def async_step_init(self, user_input=None):
        if user_input is not None: 
            return self.async_create_entry(title="", data=user_input)

        # Home Assistant automatically populates self.config_entry natively
        options = self.config_entry.options

        return self.async_show_form(
            step_id="init", 
            data_schema=vol.Schema({
                # Theme & Aesthetics (Auto added, Boolean removed)
                vol.Optional(CONF_THEME_MODE, default=options.get(CONF_THEME_MODE, "system")): selector.SelectSelector(selector.SelectSelectorConfig(options=["system", "auto", "light", "dark", "red"], mode="dropdown", translation_key="theme_mode")),
                
                # Plot Orientation
                vol.Optional(CONF_SHOW_COMPASS, default=options.get(CONF_SHOW_COMPASS, True)): selector.BooleanSelector(),
                vol.Optional(CONF_INVERT_PLOT, default=options.get(CONF_INVERT_PLOT, False)): selector.BooleanSelector(),
                

                # Constellation Controls
                vol.Optional(CONF_SHOW_CONSTELLATIONS, default=options.get(CONF_SHOW_CONSTELLATIONS, False)): selector.BooleanSelector(),
                vol.Optional(CONF_SHOW_CONST_LABELS, default=options.get(CONF_SHOW_CONST_LABELS, False)): selector.BooleanSelector(),
                
                # Celestial Bodies
                vol.Optional(CONF_SELECTED_BODIES, default=options.get(CONF_SELECTED_BODIES, DEFAULT_BODIES)): selector.SelectSelector(selector.SelectSelectorConfig(options=[{"value": b, "label": b} for b in DEFAULT_BODIES], multiple=True, mode="list")),
            })
        )