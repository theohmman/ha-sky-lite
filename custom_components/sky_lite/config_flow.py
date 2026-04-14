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
        # FIX: We return the handler WITHOUT passing the config_entry argument.
        # This resolves the TypeError.
        return SkyLiteOptionsFlowHandler()

class SkyLiteOptionsFlowHandler(config_entries.OptionsFlow):
    # FIX: We omit __init__ entirely. 
    # This avoids the "no setter" AttributeError for the config_entry property.

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        # Home Assistant's base class provides self.config_entry automatically.
        options = self.config_entry.options
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(CONF_UPDATE_INTERVAL, default=options.get(CONF_UPDATE_INTERVAL, 60)): selector.NumberSelector(
                    selector.NumberSelectorConfig(min=10, max=3600, step=1, mode="box")
                ),
                vol.Optional(CONF_INVERT_PLOT, default=options.get(CONF_INVERT_PLOT, False)): selector.BooleanSelector(),
                vol.Optional(CONF_SHOW_ECLIPTIC, default=options.get(CONF_SHOW_ECLIPTIC, True)): selector.BooleanSelector(),
                vol.Optional(CONF_SELECTED_BODIES, default=options.get(CONF_SELECTED_BODIES, DEFAULT_BODIES)): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[{"value": b, "label": b} for b in DEFAULT_BODIES],
                        multiple=True,
                        mode="list"
                    )
                ),
            })
        )