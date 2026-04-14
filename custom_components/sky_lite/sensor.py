import json
import ephem
import math
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import *

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat, lon = config_entry.data.get("latitude"), config_entry.data.get("longitude")
    elev = config_entry.data.get("elevation")

    sensor = SkyLiteSensor(hass, config_entry, lat, lon, elev)
    async_add_entities([sensor], True)

class SkyLiteSensor(SensorEntity):
    def __init__(self, hass, entry, lat, lon, elev):
        self.hass = hass
        self.entry = entry
        self._attr_name = "Sky Lite View"
        self._attr_unique_id = f"sky_lite_{entry.entry_id}"
        self.obs = ephem.Observer()
        self.obs.lat, self.obs.lon, self.obs.elevation = str(lat), str(lon), elev
        self._attributes = {}
        self._unsub_interval = None

        # Listen for option updates
        self.entry.add_update_listener(self.async_update_options)

    async def async_added_to_hass(self):
        """Start the timer when added to Home Assistant."""
        await self.async_update_sensor_interval()

    async def async_will_remove_from_hass(self):
        """Clean up the timer when removed."""
        if self._unsub_interval:
            self._unsub_interval()

    async def async_update_options(self, hass, entry):
        """Handle options update from the UI."""
        await self.async_update_sensor_interval()
        self.async_schedule_update_ha_state(True)

    async def async_update_sensor_interval(self):
        """Update the interval timer based on user settings."""
        if self._unsub_interval:
            self._unsub_interval()

        interval = self.entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._unsub_interval = async_track_time_interval(
            self.hass, self.async_update_ha_state_refresh, timedelta(seconds=interval)
        )

    async def async_update_ha_state_refresh(self, _now=None):
        """Force a state update."""
        self.async_schedule_update_ha_state(True)

    def get_projection(self, az, alt):
        invert = self.entry.options.get(CONF_INVERT_PLOT, False)
        r = (90 - alt) / 90 * 45
        base_angle = az - 90 if not invert else az + 90
        theta = math.radians(base_angle)
        return round(50 + r * math.cos(theta), 2), round(50 + r * math.sin(theta), 2)

    def update(self):
        opts = self.entry.options
        now = datetime.utcnow()
        self.obs.date = now

        selected = opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES)
        all_bodies = {
            "Sun": {"obj": ephem.Sun(), "color": "#f9d71c", "size": 1.6},
            "Moon": {"obj": ephem.Moon(), "color": "#c9d1d9", "size": 1.4},
            "Mars": {"obj": ephem.Mars(), "color": "#ff5f5f", "size": 1.0},
            "Venus": {"obj": ephem.Venus(), "color": "#e3b341", "size": 1.1},
            "Jupiter": {"obj": ephem.Jupiter(), "color": "#d4a276", "size": 1.2},
            "Saturn": {"obj": ephem.Saturn(), "color": "#9b8a6d", "size": 1.1},
            "Mercury": {"obj": ephem.Mercury(), "color": "#A5A5A5", "size": 0.8}
        }

        svg = ['<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="background-color: #0d1117; border-radius: 50%;">']

        # Compass Labels
        labels = {"N": (48.5, 4), "S": (48.5, 99), "E": (96, 51), "W": (1, 51)}
        if opts.get(CONF_INVERT_PLOT):
            labels = {"S": (48.5, 4), "N": (48.5, 99), "W": (96, 51), "E": (1, 51)}

        for text, (x, y) in labels.items():
            svg.append(f'<text x="{x}" y="{y}" fill="#8b949e" font-size="3">{text}</text>')

        # Bodies and Ecliptic
        coord_data = {}
        for name in selected:
            if name in all_bodies:
                info = all_bodies[name]
                body = info["obj"]
                body.compute(self.obs)
                az, alt = float(body.az) * 57.3, float(body.alt) * 57.3
                coord_data[name] = {"az": round(az, 2), "alt": round(alt, 2)}

                if alt > -1:
                    x, y = self.get_projection(az, alt)
                    svg.append(f'<circle cx="{x}" cy="{y}" r="{info["size"]}" fill="{info["color"]}" />')
                    svg.append(f'<text x="{x+2}" y="{y+1}" fill="#f0f6fc" font-size="2.2" pointer-events="none">{name}</text>')

        svg.append('</svg>')
        self._attributes.update({
            "celestial_json": json.dumps(coord_data),
            "svg_plot": "".join(svg),
            "last_updated": datetime.now().strftime("%I:%M:%S %p")
        })

    @property
    def state(self):
        return "Active"

    @property
    def extra_state_attributes(self):
        return self._attributes
