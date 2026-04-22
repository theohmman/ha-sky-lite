import logging
import ephem
from datetime import timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util
from .const import DOMAIN, CONF_UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)

class SkyLiteCoordinator(DataUpdateCoordinator):
    """Centralized brain for Sky Lite math calculations."""
    
    def __init__(self, hass, entry):
        self.entry = entry
        self.lat = float(entry.data.get("latitude"))
        self.lon = float(entry.data.get("longitude"))
        self.elev = entry.data.get("elevation")
        
        # Setup the PyEphem Observer ONCE
        self.obs = ephem.Observer()
        self.obs.lat = str(self.lat)
        self.obs.lon = str(self.lon)
        self.obs.elevation = self.elev

        # Grab user's refresh rate (defaulting to 1 min)
        interval = int(entry.options.get(CONF_UPDATE_INTERVAL, "1"))
        
        super().__init__(
            hass,
            _LOGGER,
            name="Sky Lite Coordinator",
            update_interval=timedelta(minutes=interval),
        )

    async def _async_update_data(self):
        """Run the heavy math safely in a background thread."""
        return await self.hass.async_add_executor_job(self._calculate_sky)

    def _calculate_sky(self):
        """Calculate the position of all bodies exactly once per interval."""
        try:
            self.obs.date = dt_util.utcnow()
            data = {}
            
            # 1. Moon Phase (Needed by the Image map)
            m1, m2 = ephem.Moon(self.obs), ephem.Moon()
            m2.compute(self.obs.date + 0.1)
            data["moon_phase"] = m1.phase / 100.0
            data["moon_waning"] = m2.phase < m1.phase

            # 2. Planetary Positions (Needed by Image AND Sensor)
            bodies = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]
            data["bodies"] = {}
            
            for name in bodies:
                body = getattr(ephem, name)()
                body.compute(self.obs)
                
                data["bodies"][name] = {
                    "az": float(body.az) * 57.2957795, # Convert Radians to Degrees
                    "alt": float(body.alt) * 57.2957795,
                }
                
            return data
        except Exception as e:
            raise UpdateFailed(f"Sky Lite Math Error: {e}")