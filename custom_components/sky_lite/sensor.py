import ephem, logging
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import *

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat, lon, elev = config_entry.data.get("latitude"), config_entry.data.get("longitude"), config_entry.data.get("elevation")
    async_add_entities([SkyLiteLegendSensor(hass, config_entry, lat, lon, elev)], False)

class SkyLiteLegendSensor(SensorEntity):
    
    # This acts as the shield against database bloat
    _unrecorded_attributes = frozenset({"celestial_bodies"})
    
    def __init__(self, hass, entry, lat, lon, elev):
        self.hass, self.entry, self.lat = hass, entry, float(lat)
        self.obs = ephem.Observer()
        self.obs.lat, self.obs.lon, self.obs.elevation = str(lat), str(lon), elev
        self._attr_name = "Sky Lite Legend"
        self._attr_unique_id = f"sky_lite_legend_{entry.entry_id}"
        self._attributes = {"celestial_bodies": {}}
        self._unsub_interval = None

    async def async_added_to_hass(self):
        self._unsub_interval = async_track_time_interval(self.hass, self.async_update_ha_state_refresh, timedelta(seconds=60))
        self.hass.async_add_executor_job(self.update)

    async def async_will_remove_from_hass(self): 
        if self._unsub_interval: self._unsub_interval()

    async def async_update_ha_state_refresh(self, _now=None):
        self.hass.async_add_executor_job(self.update)
        self.async_write_ha_state()

    def update(self):
        try:
            self.obs.date = datetime.utcnow()
            data = {}
            for name in self.entry.options.get(CONF_SELECTED_BODIES, DEFAULT_BODIES):
                b_o = getattr(ephem, name)()
                b_o.compute(self.obs)
                alt_deg = float(b_o.alt) * 57.3
                if alt_deg >= -7:
                    data[name] = {"alt": round(alt_deg, 1), "az": round(float(b_o.az)*57.3, 1)}
            
            self._attributes["celestial_bodies"] = data
            self._attr_native_value = f"{len(data)} Visible"
        except Exception as e:
            _LOGGER.error("Sky Lite Data Error: %s", e)

    @property
    def extra_state_attributes(self): 
        return self._attributes