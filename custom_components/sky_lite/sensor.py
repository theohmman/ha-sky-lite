import logging
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, CONF_SELECTED_BODIES, DEFAULT_BODIES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    # Grab the centralized Brain we stored in memory during __init__.py setup
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([SkyLiteLegendSensor(coordinator, config_entry)], False)

class SkyLiteLegendSensor(CoordinatorEntity, SensorEntity):
    
    # This acts as the shield against database bloat
    _unrecorded_attributes = frozenset({"celestial_bodies"})
    
    def __init__(self, coordinator, entry):
        # Pass the coordinator to the base class
        super().__init__(coordinator)
        self.entry = entry
        self._attr_name = "Sky Lite Legend"
        self._attr_unique_id = f"sky_lite_legend_{entry.entry_id}"
        self._attributes = {"celestial_bodies": {}}
        self._update_attributes()

    @property
    def extra_state_attributes(self):
        return self._attributes

    @property
    def state(self):
        """State is just the number of visible bodies."""
        return len(self._attributes.get("celestial_bodies", {}))

    def _handle_coordinator_update(self) -> None:
        """Fires automatically when the Brain pushes new data."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self):
        """Format the Brain's data for the Markdown table."""
        if not self.coordinator.data:
            return

        data = {}
        bodies_data = self.coordinator.data.get("bodies", {})
        
        for name in self.entry.options.get(CONF_SELECTED_BODIES, DEFAULT_BODIES):
            if name in bodies_data:
                alt_deg = bodies_data[name]["alt"]
                if alt_deg >= -7:
                    data[name] = {
                        "alt": round(alt_deg, 2),
                        "az": round(bodies_data[name]["az"], 2)
                    }

        # Sort by highest altitude so the table looks organized
        self._attributes["celestial_bodies"] = dict(sorted(data.items(), key=lambda item: item[1]['alt'], reverse=True))