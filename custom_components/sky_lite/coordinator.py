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
            self.obs.date = ephem.now()
            data = {}
            
            # 1. Moon Phase & Illumination (Needed by Image and Sensor)
            import math
            m1 = ephem.Moon(self.obs)
            sun_obj = ephem.Sun(self.obs)
            data["moon_phase"] = m1.phase / 100.0
            
            # Check RA distance from Sun to determine Waxing vs Waning
            angle = (m1.ra - sun_obj.ra) % (2 * math.pi)
            data["moon_waning"] = angle >= math.pi

            # Calculate Moon Age and Upcoming Phases
            prev_new = ephem.previous_new_moon(self.obs.date)
            data["moon_age"] = self.obs.date - prev_new
            data["next_new_moon"] = ephem.localtime(ephem.next_new_moon(self.obs.date)).date().isoformat()
            data["next_full_moon"] = ephem.localtime(ephem.next_full_moon(self.obs.date)).date().isoformat()

            # 2. Planetary Positions & Events
            bodies = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]
            data["bodies"] = {}
            
            for name in bodies:
                body = getattr(ephem, name)()
                body.compute(self.obs)
                
                # Safely extract Rise, Set, and Apex events with relative date prefixes
                def get_event(event_func):
                    from datetime import datetime
                    try:
                        # Get event time and current time in local timezone
                        event_dt = ephem.localtime(event_func(body))
                        now_dt = datetime.now()
                        
                        # Calculate the calendar day difference
                        day_diff = (event_dt.date() - now_dt.date()).days
                        
                        # Format as 24-hour HH:MM
                        time_str = event_dt.strftime("%H:%M")
                        
                        if day_diff < 0:
                            return f"-{time_str}"
                        elif day_diff > 0:
                            return f"+{time_str}"
                        else:
                            return time_str
                            
                    except ephem.AlwaysUpError:
                        return "Always Up"
                    except ephem.NeverUpError:
                        return "Never Up"
                    except Exception:
                        return "--:--"

                data["bodies"][name] = {
                    "az": float(body.az) * 57.2957795,
                    "alt": float(body.alt) * 57.2957795,
                    "rise": get_event(self.obs.next_rising),
                    "set": get_event(self.obs.next_setting),
                    "transit": get_event(self.obs.next_transit)
                }
            return data
        except Exception as e:
            _LOGGER.error("Sky Lite Coordinator Math Error: %s", e)
            return {}
