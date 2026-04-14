import json, ephem, math, logging
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from .const import *

_LOGGER = logging.getLogger(__name__)

# RA (H:M:S), Dec (D:M:S)
CONSTELLATIONS = {
    "Ursa Major": [("11:03:43", "61:45:00"), ("11:01:50", "56:22:00"), ("11:53:49", "53:41:00"), ("12:15:25", "57:01:00"), ("12:54:01", "55:57:00"), ("13:23:55", "54:55:00"), ("13:47:32", "49:18:00")],
    "Ursa Minor": [("2:31:49", "89:15:00"), ("17:32:12", "86:35:00"), ("18:20:00", "71:50:00"), ("15:44:03", "77:47:00"), ("15:20:00", "71:50:00"), ("14:50:00", "74:00:00")],
    "Orion": [("5:55:10", "7:24:00"), ("5:25:07", "6:20:00"), ("5:36:12", "-1:12:00"), ("5:40:45", "-1:56:00"), ("5:32:00", "-0:17:00"), ("5:14:32", "-8:12:00"), ("5:47:45", "-9:40:00")],
    "Cassiopeia": [("0:09:10", "59:08:00"), ("0:40:30", "56:32:00"), ("0:56:42", "60:43:00"), ("1:25:48", "60:14:00"), ("1:54:23", "63:40:00")],
    "Cygnus": [("20:41:25", "45:16:00"), ("19:44:58", "45:07:00"), ("19:30:43", "27:57:00"), ("19:44:58", "45:07:00"), ("21:12:56", "30:13:00"), ("19:44:58", "45:07:00"), ("19:17:07", "53:22:00")],
    # Zodiac Completion
    "Aries": [("2:07:10", "23:27:00"), ("1:54:38", "20:48:00"), ("1:53:31", "19:17:00")],
    "Taurus": [("4:35:55", "16:30:00"), ("4:19:47", "15:37:00"), ("3:47:29", "24:06:00"), ("5:26:17", "28:36:00"), ("4:35:55", "16:30:00"), ("5:37:38", "21:08:00")],
    "Gemini": [("7:45:18", "28:01:00"), ("7:20:07", "31:53:00"), ("6:37:42", "16:23:00"), ("6:14:52", "22:30:00"), ("7:45:18", "28:01:00")],
    "Cancer": [("8:58:29", "11:51:00"), ("8:44:41", "18:09:00"), ("8:16:30", "9:11:00"), ("8:44:41", "18:09:00"), ("9:17:06", "26:38:00")],
    "Leo": [("10:08:22", "11:58:00"), ("10:20:00", "19:50:00"), ("11:14:06", "20:31:00"), ("11:49:03", "14:34:00"), ("11:14:06", "20:31:00"), ("10:20:00", "19:50:00"), ("9:45:51", "23:46:00")],
    "Virgo": [("13:25:11", "-11:09:00"), ("12:41:39", "-1:26:00"), ("12:55:36", "3:23:00"), ("13:02:10", "10:57:00"), ("12:55:36", "3:23:00"), ("12:41:39", "-1:26:00"), ("11:50:41", "1:45:00")],
    "Libra": [("15:17:00", "-9:22:00"), ("14:50:41", "-16:02:00"), ("15:35:31", "-14:47:00"), ("15:44:04", "-25:17:00")],
    "Scorpius": [("16:00:20", "-22:37:00"), ("16:29:24", "-26:25:00"), ("16:50:00", "-34:17:00"), ("17:33:36", "-43:00:00"), ("17:47:35", "-40:07:00")],
    "Sagittarius": [("19:02:36", "-29:52:00"), ("18:55:15", "-26:17:00"), ("18:27:59", "-25:25:00"), ("18:20:59", "-29:49:00"), ("18:27:59", "-25:25:00"), ("18:45:39", "-26:59:00"), ("19:02:36", "-29:52:00")],
    "Capricorn": [("21:47:02", "-16:07:00"), ("21:05:50", "-17:13:00"), ("20:18:03", "-12:32:00"), ("20:17:38", "-14:59:00"), ("20:46:05", "-25:16:00")],
    "Aquarius": [("22:05:47", "-0:19:00"), ("22:21:39", "-1:23:00"), ("22:52:38", "-7:34:00"), ("23:05:20", "-9:29:00"), ("22:52:38", "-7:34:00"), ("23:19:24", "-13:27:00")],
    "Pisces": [("1:31:29", "15:20:00"), ("0:48:39", "7:35:00"), ("0:02:02", "7:34:00"), ("23:39:56", "5:37:00"), ("23:59:18", "6:51:00")]
}

# Major individual star markers
FIXED_STARS = {
    "Vega": ("18:36:56", "38:47:00"),
    "Deneb": ("20:41:25", "45:16:00"),
    "Altair": ("19:50:47", "8:52:00"),
    "Polaris": ("2:31:49", "89:15:00")
}

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat, lon, elev = config_entry.data.get("latitude"), config_entry.data.get("longitude"), config_entry.data.get("elevation")
    async_add_entities([SkyLiteSensor(hass, config_entry, lat, lon, elev)], False)

class SkyLiteSensor(SensorEntity):
    def __init__(self, hass, entry, lat, lon, elev):
        self.hass, self.entry, self.lat = hass, entry, float(lat)
        self.obs = ephem.Observer()
        self.obs.lat, self.obs.lon, self.obs.elevation = str(lat), str(lon), elev
        self._attr_name = "Sky Lite View"
        self._attr_unique_id = f"sky_lite_{entry.entry_id}"
        self._attributes = {"svg_plot": "", "last_updated": "Initializing..."}
        self._unsub_interval = None
        self.entry.add_update_listener(self.async_update_options)

    async def async_added_to_hass(self):
        await self.async_update_sensor_interval()
        self.hass.async_add_executor_job(self.update)

    async def async_will_remove_from_hass(self): 
        if self._unsub_interval: self._unsub_interval()

    async def async_update_options(self, hass, entry):
        await self.async_update_sensor_interval()
        self.hass.async_add_executor_job(self.update)
        self.async_write_ha_state()

    async def async_update_sensor_interval(self):
        if self._unsub_interval: self._unsub_interval()
        interval = self.entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        self._unsub_interval = async_track_time_interval(self.hass, self.async_update_ha_state_refresh, timedelta(seconds=interval))

    async def async_update_ha_state_refresh(self, _now=None):
        self.hass.async_add_executor_job(self.update)
        self.async_write_ha_state()

    def get_projection(self, az, alt):
        invert = self.entry.options.get(CONF_INVERT_PLOT, False)
        r = (90 - alt) / 2.15
        base_angle = az - 90 if not invert else az + 90
        theta = math.radians(base_angle)
        return round(50 + r * math.cos(theta), 2), round(50 + r * math.sin(theta), 2)

    def get_sun_path(self, ephem_date, color, opacity, dashed=True):
        try:
            d_tuple = ephem_date.tuple()
            dt = datetime(d_tuple[0], d_tuple[1], d_tuple[2])
            sun = ephem.Sun()
            sun.compute(ephem_date)
            dec = sun.dec
            temp_obs = ephem.Observer()
            temp_obs.lat, temp_obs.lon = self.obs.lat, self.obs.lon
            segments, current_segment = [], []
            for i in range(0, 1441, 30):
                temp_obs.date = dt + timedelta(minutes=i)
                s = ephem.Sun(temp_obs)
                if s.alt > 0: current_segment.append(self.get_projection(float(s.az)*57.3, float(s.alt)*57.3))
                elif current_segment: segments.append(current_segment); current_segment = []
            if current_segment: segments.append(current_segment)
            svg_paths = ""
            dash = 'stroke-dasharray="2,1"' if dashed else ""
            for seg in segments:
                if len(seg) > 1:
                    d = "M " + " L ".join([f"{p[0]},{p[1]}" for p in seg])
                    svg_paths += f'<path d="{d}" fill="none" stroke="{color}" stroke-width="0.3" {dash} opacity="{opacity}" />'
            return svg_paths
        except Exception: return ""

    def update(self):
        try:
            opts, now = self.entry.options, datetime.utcnow()
            self.obs.date = now
            invert, theme = opts.get(CONF_INVERT_PLOT, False), opts.get(CONF_THEME_MODE, "system")
            
            if theme == "light": bg_s, bg_b, t_p, t_s = "#f0f2f5", "#ffffff", "#1a1a1a", "#70757a"
            else: bg_s, bg_b, t_p, t_s = "#0c0e12", "#1a1c21", "#f0f6fc", "#8b949e"
            
            c_p = "var(--primary-text-color, #f0f6fc)" if theme == "system" else t_p
            c_s = "var(--secondary-text-color, #8b949e)" if theme == "system" else t_s
            c_d = "var(--divider-color, #30363d)" if theme == "system" else "#30363d"

            svg = [f'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="background-color: transparent; border-radius: 50%;">',
                   f'<defs><radialGradient id="hG"><stop offset="85%" stop-color="{bg_s}"/><stop offset="100%" stop-color="{bg_b}"/></radialGradient></defs>',
                   '<circle cx="50" cy="50" r="42" fill="url(#hG)" />']

            # Grid logic
            for alt in range(10, 90, 10):
                r = (90 - alt) / 2.15
                svg.append(f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{c_d}" stroke-width="0.08" opacity="0.4" />')
                if alt % 30 == 0: svg.append(f'<text x="50.5" y="{50-r-0.8}" fill="{c_s}" font-size="2" opacity="0.5">{alt}°</text>')

            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            if invert: dirs = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
            for i, label in enumerate(dirs):
                rad = math.radians(i*45-90)
                x2, y2 = 50+42*math.cos(rad), 50+42*math.sin(rad)
                lx, ly = 50+45.5*math.cos(rad), 50+45.5*math.sin(rad)
                svg.append(f'<line x1="50" y1="50" x2="{x2}" y2="{y2}" stroke="{c_d}" stroke-width="0.08" opacity="0.2" />')
                svg.append(f'<text x="{lx}" y="{ly}" fill="{c_p}" font-size="3.2" text-anchor="middle" dominant-baseline="middle" font-weight="bold">{label}</text>')

            # Paths logic
            svg.append(self.get_sun_path(ephem.next_summer_solstice(now), "#FFD700", 0.3, True))
            svg.append(self.get_sun_path(ephem.next_winter_solstice(now), "#4facfe", 0.3, True))
            svg.append(self.get_sun_path(ephem.Date(now), "#FFD700", 0.6, False))

            # NEW: Fixed Stars Logic (Summer Triangle)
            for name, (ra, dec) in FIXED_STARS.items():
                star = ephem.FixedBody()
                star._ra, star._dec = ra, dec
                star.compute(self.obs)
                if star.alt > 0:
                    x, y = self.get_projection(float(star.az)*57.3, float(star.alt)*57.3)
                    svg.append(f'<circle cx="{x}" cy="{y}" r="0.4" fill="{c_s}" opacity="0.8" />')
                    if opts.get(CONF_SHOW_CONST_LABELS):
                        svg.append(f'<text x="{x+1}" y="{y}" fill="{c_s}" font-size="1.5" opacity="0.4">{name}</text>')

            # Constellations Logic (Thinner lines)
            if opts.get(CONF_SHOW_CONSTELLATIONS):
                for name, stars in CONSTELLATIONS.items():
                    pts = []
                    for ra_str, dec_str in stars:
                        star = ephem.FixedBody()
                        star._ra, star._dec = ra_str, dec_str
                        star.compute(self.obs)
                        if star.alt > -5: pts.append(self.get_projection(float(star.az)*57.3, float(star.alt)*57.3))
                    if len(pts) > 1:
                        d = "M " + " L ".join([f"{p[0]},{p[1]}" for p in pts])
                        svg.append(f'<path d="{d}" fill="none" stroke="{c_s}" stroke-width="0.08" opacity="0.3" />')
                        if opts.get(CONF_SHOW_CONST_LABELS) and any(0 < p[0] < 100 and 0 < p[1] < 100 for p in pts):
                            svg.append(f'<text x="{pts[0][0]}" y="{pts[0][1]-1}" fill="{c_s}" font-size="1.8" opacity="0.3">{name}</text>')

            # Planets logic
            bodies = {"Sun": ("#FFD700", 2.4), "Moon": ("#E0E0E0", 2.1), "Mars": ("#FF4500", 1.1), "Venus": ("#FFCC33", 1.2), "Jupiter": ("#D4A276", 1.4), "Saturn": ("#C0C0C0", 1.2), "Mercury": ("#A5A5A5", 0.9)}
            for name in opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES):
                if name in bodies:
                    color, size = bodies[name]
                    b = getattr(ephem, name)()
                    b.compute(self.obs)
                    az, alt = float(b.az)*57.3, float(b.alt)*57.3
                    if alt > -0.5:
                        x, y = self.get_projection(az, alt)
                        svg.append(f'<circle cx="{x}" cy="{y}" r="{size}" fill="{color}" />')
                        svg.append(f'<text x="{x+2.2}" y="{y+1}" fill="{c_p}" font-size="2.6" font-weight="bold">{name}</text>')

            svg.append('</svg>')
            self._attributes.update({"svg_plot": "".join(svg), "last_updated": datetime.now().strftime("%I:%M:%S %p")})
            self._attr_native_value = "Active"
        except Exception as e:
            _LOGGER.error("Error in Sky Lite update: %s", e)
            self._attr_native_value = "Error"

    @property
    def extra_state_attributes(self): return self._attributes