import json, ephem, math, logging
from datetime import datetime, timedelta
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from .const import *

_LOGGER = logging.getLogger(__name__)

MILKY_WAY_PATH = [("0:00:00", "62:00:00"), ("2:00:00", "60:00:00"), ("4:00:00", "50:00:00"), ("6:00:00", "20:00:00"), ("8:00:00", "-20:00:00"), ("10:00:00", "-50:00:00"), ("12:00:00", "-63:00:00"), ("14:00:00", "-60:00:00"), ("16:00:00", "-30:00:00"), ("18:00:00", "-28:00:00"), ("20:00:00", "30:00:00"), ("22:00:00", "50:00:00"), ("23:59:59", "62:00:00")]
CONSTELLATIONS = {
    "Ursa Major": [("11:03:43", "61:45:00"), ("11:01:50", "56:22:00"), ("11:53:49", "53:41:00"), ("12:15:25", "57:01:00"), ("12:54:01", "55:57:00")],
    "Ursa Minor": [("2:31:49", "89:15:00"), ("17:32:12", "86:35:00"), ("18:20:00", "71:50:00")],
    "Cassiopeia": [("0:09:10", "59:08:00"), ("0:40:30", "56:32:00"), ("0:56:42", "60:43:00"), ("1:25:48", "60:14:00")],
    "Orion": [("5:55:10", "7:24:00"), ("5:25:07", "6:20:00"), ("5:36:12", "-1:12:00")],
    "Cygnus": [("20:41:25", "45:16:00"), ("19:44:58", "45:07:00"), ("19:30:43", "27:57:00")]
}
FIXED_STARS = {"Vega": ("18:36:56", "38:47:00"), "Deneb": ("20:41:25", "45:16:00"), "Altair": ("19:50:47", "8:52:00"), "Polaris": ("2:31:49", "89:15:00")}

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat, lon, elev = config_entry.data.get("latitude"), config_entry.data.get("longitude"), config_entry.data.get("elevation")
    async_add_entities([SkyLiteSensor(hass, config_entry, lat, lon, elev)], False)

class SkyLiteSensor(SensorEntity):
    def __init__(self, hass, entry, lat, lon, elev):
        self.hass, self.entry, self.lat = hass, entry, float(lat)
        self.obs = ephem.Observer()
        self.obs.lat, self.obs.lon, self.obs.elevation = str(lat), str(lon), elev
        self._attr_name, self._attr_unique_id = "Sky Lite View", f"sky_lite_{entry.entry_id}"
        self._attributes = {"svg_plot": "", "svg_legend": "", "last_updated": ""}
        self._unsub_interval = None
        self.entry.add_update_listener(self.async_update_options)

    async def async_added_to_hass(self):
        await self.async_update_sensor_interval(); self.hass.async_add_executor_job(self.update)

    async def async_will_remove_from_hass(self): 
        if self._unsub_interval: self._unsub_interval()

    async def async_update_options(self, hass, entry):
        await self.async_update_sensor_interval(); self.hass.async_add_executor_job(self.update); self.async_write_ha_state()

    async def async_update_sensor_interval(self):
        if self._unsub_interval: self._unsub_interval()
        interval = self.entry.options.get(CONF_UPDATE_INTERVAL, 60)
        self._unsub_interval = async_track_time_interval(self.hass, self.async_update_ha_state_refresh, timedelta(seconds=interval))

    async def async_update_ha_state_refresh(self, _now=None):
        self.hass.async_add_executor_job(self.update); self.async_write_ha_state()

    def get_projection(self, az, alt):
        invert = self.entry.options.get(CONF_INVERT_PLOT, False); r = (90 - alt) / 2.15
        base_angle = az - 90 if not invert else az + 90
        theta = math.radians(base_angle)
        return round(50 + r * math.cos(theta), 2), round(50 + r * math.sin(theta), 2)

    def draw_moon(self, cx, cy, r, ph, waning, invert, is_plot=True):
        """Production RC: Pure Radiant Path with Hemisphere-Adaptive Orientation."""
        is_nh = self.lat >= 0
        if is_plot:
            # Nominal Polar Plot Bulge logic: faces East for Waning, West for Waxing.
            # On N-Up (invert=F) East is Right (lit_left=F). S-Up (invert=T) East is Left (lit_left=T).
            lit_left = invert if waning else not invert
        else:
            # Legend Ground View: Waning NH = Left, Waning SH = Right.
            lit_left = waning if is_nh else not waning

        sweep_outer = 0 if lit_left else 1
        # Crescent Geometry: arcs curve towards same side (sweep_inner must inverse sweep_outer relative to chord)
        sweep_inner = (1 - sweep_outer) if ph < 0.5 else sweep_outer
        r_inner = r * abs(1 - 2*ph)
        
        d = f"M {cx},{cy-r} A {r},{r} 0 0,{sweep_outer} {cx},{cy+r} A {r_inner},{r} 0 0,{sweep_inner} {cx},{cy-r} Z"
        return f'<path d="{d}" fill="#f5f5dc" opacity="1.0" {"filter=\'url(#halo)\'" if is_plot else ""} />'

    def get_sun_path(self, ep_date, color, opacity, dashed=True):
        try:
            d_t, t_o = ep_date.tuple(), ephem.Observer()
            dt = datetime(d_t[0], d_t[1], d_t[2])
            t_o.lat, t_o.lon = self.obs.lat, self.obs.lon
            segs, cur = [], []
            for i in range(0, 1441, 30):
                t_o.date = dt + timedelta(minutes=i); s = ephem.Sun(t_o)
                if s.alt > 0: cur.append(self.get_projection(float(s.az)*57.3, float(s.alt)*57.3))
                elif cur: segs.append(cur); cur = []
            if cur: segs.append(cur)
            svg_p, dash = "", 'stroke-dasharray="2,1"' if dashed else ""
            for seg in segs:
                if len(seg) > 1:
                    d = "M " + " L ".join([f"{p[0]},{p[1]}" for p in seg])
                    svg_p += f'<path d="{d}" fill="none" stroke="{color}" stroke-width="0.55" {dash} opacity="{opacity}" />'
            return svg_p
        except Exception: return ""

    def update(self):
        try:
            opts, now_utc = self.entry.options, datetime.utcnow()
            self.obs.date = now_utc; now_local = dt_util.as_local(now_utc)
            invert, theme = opts.get(CONF_INVERT_PLOT, False), opts.get(CONF_THEME_MODE, "system")
            m1 = ephem.Moon(self.obs); m2 = ephem.Moon()
            m2.compute(float(self.obs.date) + 0.1); waning = m2.phase < m1.phase
            if opts.get(CONF_AUTO_THEME, False):
                sn = ephem.Sun(self.obs); theme = "light" if sn.alt > -0.015 else "dark"
            if theme == "light":
                c_w, c_b, c_p, h_c = "#FFFFFF", "#D0EAFF", "#FFDEAD", "#ffffff"
                t_p, t_s = "#1a202c", "#4a5568"
                grad = f'<stop offset="0%" stop-color="{c_w}"/><stop offset="40%" stop-color="{c_b}"/><stop offset="85%" stop-color="{c_p}" stop-opacity="0.95"/><stop offset="100%" stop-color="{c_p}" stop-opacity="0.2"/>'
            else:
                bg_s, bg_h, bg_b, h_c = "#020617", "#0f172a", "#1e293b", "#000000"
                t_p, t_s = "#ffffff", "#d1d5db" # Lighter text for dark mode visibility
                grad = f'<stop offset="0%" stop-color="{bg_s}"/><stop offset="85%" stop-color="{bg_h}"/><stop offset="100%" stop-color="{bg_b}"/>'
            c_pri = "var(--primary-text-color, #ffffff)" if theme == "system" else t_p
            c_sec = "var(--secondary-text-color, #d1d5db)" if theme == "system" else t_s
            c_div = "var(--divider-color, #334155)" if theme == "system" else "#cbd5e1" if theme == "light" else "#334155"
            bodies_conf = {"Sun": ("#ffcc00", 3.2), "Moon": ("#36454f", 2.8), "Mars": ("#be185d", 1.8), "Venus": ("#fef3c7", 1.9), "Jupiter": ("#6d28d9", 2.1), "Saturn": ("#06b6d4", 1.9), "Mercury": ("#475569", 1.4)}
            svg_defs = [f'<radialGradient id="hG" cx="50%" cy="50%" r="50%">{grad}</radialGradient>',
                        f'<filter id="halo"><feMorphology in="SourceAlpha" result="dilate" radius="0.05"/><feFlood flood-color="{h_c}" flood-opacity="0.9"/><feComposite in2="dilate" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
                        f'<filter id="glint"><feGaussianBlur stdDeviation="0.2" result="blur"/><feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>']
            for name, (color, size) in bodies_conf.items():
                svg_defs.append(f'<radialGradient id="sph_{name}" cx="35%" cy="35%" r="50%"><stop offset="0%" stop-color="#ffffff" stop-opacity="0.5"/><stop offset="100%" stop-color="{color}"/></radialGradient>')
            svg = [f'<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg" style="background-color: transparent; border-radius: 50%; color: {c_pri};">',
                   f'<defs>{"".join(svg_defs)}</defs>', '<circle cx="50" cy="50" r="42" fill="url(#hG)" />']
            for alt in range(15, 90, 15):
                r = (90 - alt) / 2.15; svg.append(f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{c_div}" stroke-width="0.35" opacity="0.6" />')
                lx, ly = self.get_projection(225, alt); svg.append(f'<text x="{lx}" y="{ly}" fill="{c_sec}" font-size="2.6" font-weight="bold" text-anchor="middle" filter="url(#halo)">{alt}°</text>')
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
            if invert: dirs = ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
            for i, label in enumerate(dirs):
                rad = math.radians(i*45-90); lx, ly = 50+46*math.cos(rad), 50+46*math.sin(rad)
                fs = "5.6" if label in ["N","S","E","W"] else "4.2"
                svg.append(f'<text x="{lx}" y="{ly}" fill="{c_pri}" font-size="{fs}" text-anchor="middle" dominant-baseline="middle" font-weight="{"bold" if label in ["N","S","E","W"] else "normal"}" filter="url(#halo)">{label}</text>')
            is_nh = self.lat >= 0
            svg.append(self.get_sun_path(ephem.next_summer_solstice(now_utc) if is_nh else ephem.next_winter_solstice(now_utc), "#ffcc00", 0.4, True))
            svg.append(self.get_sun_path(ephem.next_winter_solstice(now_utc) if is_nh else ephem.next_summer_solstice(now_utc), "#38bdf8", 0.4, True))
            svg.append(self.get_sun_path(ephem.Date(now_utc), "#ffcc00", 0.7, False))
            leg = [f'<svg viewBox="0 0 100 135" xmlns="http://www.w3.org/2000/svg" style="color: {c_pri};">',
                   f'<defs>{"".join(svg_defs)}</defs>', f'<text x="5" y="8" fill="{c_pri}" font-size="4.2" font-weight="bold">Celestial Legend</text>',
                   f'<line x1="5" y1="10" x2="95" y2="10" stroke="{c_div}" stroke-width="0.2"/>']
            y_off = 16
            for name, (ra, dec) in FIXED_STARS.items():
                star = ephem.FixedBody(); star._ra, star._dec = ra, dec; star.compute(self.obs)
                if star.alt > 0:
                    sx, sy = self.get_projection(float(star.az)*57.3, float(star.alt)*57.3)
                    svg.append(f'<path d="M{sx},{sy-1.5} L{sx},{sy+1.5} M{sx-1.5},{sy} L{sx+1.5},{sy}" stroke="{c_sec}" stroke-width="0.15" opacity="0.4" filter="url(#glint)" />')
                    svg.append(f'<circle cx="{sx}" cy="{sy}" r="0.85" fill="{c_sec}" opacity="0.9" />')
                    leg.append(f'<g transform="translate(10, {y_off})">')
                    leg.append(f'  <path d="M0,-1.2 L0,1.2 M-1.2,0 L1.2,0" stroke="{c_sec}" stroke-width="0.15" opacity="0.5" filter="url(#glint)"/>')
                    leg.append(f'  <circle cx="0" cy="0" r="0.6" fill="{c_sec}"/><text x="8" y="0.8" fill="{c_pri}" font-size="3.0">{name}</text>')
                    leg.append(f'  <text x="55" y="0.8" fill="{c_sec}" font-size="2.6" text-anchor="end">{round(float(star.alt)*57.3,1)}°</text>')
                    leg.append(f'  <text x="85" y="0.8" fill="{c_sec}" font-size="2.6" text-anchor="end">{round(float(star.az)*57.3,1)}°</text></g>')
                    y_off += 7
            for name in opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES):
                if name in bodies_conf:
                    clr, sz = bodies_conf[name]; b_o = getattr(ephem, name)(); b_o.compute(self.obs)
                    if b_o.alt > -0.5:
                        px, py = self.get_projection(float(b_o.az)*57.3, float(b_o.alt)*57.3)
                        leg.append(f'<g transform="translate(10, {y_off})">')
                        if name == "Moon":
                            ph = b_o.phase / 100.0
                            svg.append(self.draw_moon(px, py, sz, ph, waning, invert, True))
                            leg.append(self.draw_moon(0, 0, sz, ph, waning, False, False))
                        else:
                            svg.append(f'<circle cx="{px}" cy="{py}" r="{sz}" fill="url(#sph_{name})" filter="url(#halo)" />')
                            leg.append(f'  <circle cx="0" cy="0" r="{sz}" fill="url(#sph_{name})"/>')
                        leg.append(f'  <text x="8" y="0.8" fill="{c_pri}" font-size="3.0">{name}</text>')
                        leg.append(f'  <text x="55" y="0.8" fill="{c_sec}" font-size="2.6" text-anchor="end">{round(float(b_o.alt)*57.3,1)}°</text>')
                        leg.append(f'  <text x="85" y="0.8" fill="{c_sec}" font-size="2.6" text-anchor="end">{round(float(b_o.az)*57.3,1)}°</text></g>')
                        y_off += 7
            leg.append(f'<text x="5" y="{y_off+8}" fill="{c_sec}" font-size="2.0">{now_local.isoformat(timespec="seconds")}</text>')
            leg.append('</svg>'); svg.append('</svg>')
            self._attributes.update({"svg_plot": "".join(svg), "svg_legend": "".join(leg), "last_updated": now_local.isoformat(timespec="seconds")})
            self._attr_native_value = "Active"
        except Exception as e: _LOGGER.error("Error in Sky Lite: %s", e); self._attr_native_value = "Error"

    @property
    def extra_state_attributes(self): return self._attributes