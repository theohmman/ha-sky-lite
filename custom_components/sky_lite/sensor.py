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

        # Listen for option updates
        self.entry.add_update_listener(self.async_update_options)

    async def async_update_options(self, hass, entry):
        """Handle options update."""
        await self.async_update_sensor_interval()
        self.async_schedule_update_ha_state(True)

    def get_projection(self, az, alt):
        invert = self.entry.options.get(CONF_INVERT_PLOT, False)
        r = (90 - alt) / 90 * 45
        # If inverted, add 180 degrees to the theta
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

        svg = [f'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="background-color: #0d1117; border-radius: 50%;">']

        # Compass Labels (Respecting Inversion)
        labels = {"N": (48.5, 4), "S": (48.5, 99), "E": (96, 51), "W": (1, 51)}
        if opts.get(CONF_INVERT_PLOT):
            labels = {"S": (48.5, 4), "N": (48.5, 99), "W": (96, 51), "E": (1, 51)}

        for text, (x, y) in labels.items():
            svg.append(f'<text x="{x}" y="{y}" fill="#8b949e" font-size="3">{text}</text>')

        # Draw Ecliptic (Approximate path through planets)
        if opts.get(CONF_SHOW_ECLIPTIC):
            ecliptic_pts = []
            for b_name in ["Sun", "Mercury", "Venus", "Mars", "Jupiter", "Saturn"]:
                b_obj = all_bodies[b_name]["obj"]
                b_obj.compute(self.obs)
                if float(b_obj.alt) > -0.2:
                    ecliptic_pts.append(self.get_projection(float(b_obj.az)*57.3, float(b_obj.alt)*57.3))
            if len(ecliptic_pts) > 2:
                path = "M " + " L ".join([f"{p[0]},{p[1]}" for p in sorted(ecliptic_pts)])
                svg.append(f'<path d="{path}" fill="none" stroke="#6e7681" stroke-width="0.1" opacity="0.3" />')

        # Bodies
        coord_data = {}
        for name in selected:
            info = all_bodies[name]
            body = info["obj"]
            body.compute(self.obs)
            az, alt = float(body.az) * 57.3, float(body.alt) * 57.3
            coord_data[name] = {"az": round(az, 2), "alt": round(alt, 2)}

            if alt > -1:
                x, y = self.get_projection(az, alt)
                # Added class names for CSS styling hooks
                svg.append(f'<circle class="sky-body-{name.lower()}" cx="{x}" cy="{y}" r="{info["size"]}" fill="{info["color"]}" />')
                svg.append(f'<text x="{x+2}" y="{y+1}" fill="#f0f6fc" font-size="2.2" pointer-events="none">{name}</text>')

        svg.append('</svg>')
        self._attributes.update({
            "celestial_json": json.dumps(coord_data),
            "svg_plot": "".join(svg),
            "last_updated": datetime.now().strftime("%I:%M:%S %p")
        })
