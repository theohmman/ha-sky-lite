import json, ephem, math, logging
from datetime import datetime, timedelta
from homeassistant.components.camera import Camera
from homeassistant.util import dt as dt_util
from .const import *
from .data_manager import ConstellationManager

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat, lon, elev = config_entry.data.get("latitude"), config_entry.data.get("longitude"), config_entry.data.get("elevation")
    manager = ConstellationManager(hass)
    await manager.async_update_data()
    async_add_entities([SkyLiteMapCamera(hass, config_entry, lat, lon, elev, manager.constellations)], False)

class SkyLiteMapCamera(Camera):
    def __init__(self, hass, entry, lat, lon, elev, constellation_data):
        super().__init__()
        self.content_type = "image/svg+xml"
        self.hass, self.entry, self.lat = hass, entry, float(lat)
        self.constellation_data = constellation_data
        self.obs = ephem.Observer()
        self.obs.lat, self.obs.lon, self.obs.elevation = str(lat), str(lon), elev
        self._attr_name = "Sky Lite Map"
        self._attr_unique_id = f"sky_lite_map_{entry.entry_id}"

    def get_projection(self, az, alt):
        invert = self.entry.options.get(CONF_INVERT_PLOT, False); r = (90 - alt) / 2.15
        base_angle = az - 90 if not invert else az + 90
        theta = math.radians(base_angle)
        return round(50 + r * math.cos(theta), 2), round(50 + r * math.sin(theta), 2)

    def draw_moon(self, cx, cy, r, ph, waning, invert, is_plot=True):
        is_nh = self.lat >= 0
        lit_left = invert if waning else not invert if is_plot else waning if is_nh else not waning
        sweep_outer = 0 if lit_left else 1
        sweep_inner = (1 - sweep_outer) if ph < 0.5 else sweep_outer
        r_inner = r * abs(1 - 2*ph)
        svg = [f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#36454f" opacity="1.0" filter="url(#halo)" />']
        d = f"M {cx},{cy-r} A {r},{r} 0 0,{sweep_outer} {cx},{cy+r} A {r_inner},{r} 0 0,{sweep_inner} {cx},{cy-r} Z"
        svg.append(f'<path d="{d}" fill="#f5f5dc" opacity="1.0" />')
        return "".join(svg)

    def get_sun_path(self, ep_date, color, opacity, dashed=True):
        d_t, t_o = ep_date.tuple(), ephem.Observer()
        dt = datetime(d_t[0], d_t[1], d_t[2])
        t_o.lat, t_o.lon = self.obs.lat, self.obs.lon
        segs, cur = [], []
        for i in range(0, 1441, 30):
            t_o.date = dt + timedelta(minutes=i); s = ephem.Sun(t_o)
            alt_deg = float(s.alt) * 57.3
            if alt_deg >= -7: 
                cur.append(self.get_projection(float(s.az)*57.3, alt_deg))
            elif cur: segs.append(cur); cur = []
        if cur: segs.append(cur)
        svg_p, dash = "", 'stroke-dasharray="2,1"' if dashed else ""
        for seg in segs:
            if len(seg) > 1:
                d = "M " + " L ".join([f"{p[0]},{p[1]}" for p in seg])
                svg_p += f'<path d="{d}" fill="none" stroke="{color}" stroke-width="0.55" {dash} opacity="{opacity}" />'
        return svg_p

    def camera_image(self, width=None, height=None):
        opts, now_utc = self.entry.options, datetime.utcnow()
        self.obs.date = now_utc
        show_compass = opts.get(CONF_SHOW_COMPASS, True) # Grab the new toggle
        invert = opts.get(CONF_INVERT_PLOT, False)
        theme = opts.get(CONF_THEME_MODE, "system")
        
        # New Auto-Theme Logic based on the dropdown selection
        if theme == "auto":
            sn = ephem.Sun(self.obs)
            theme = "light" if sn.alt > -0.015 else "dark"
            
        # 1. Base Colors, Theming, and Text Masks (Halos)
        if theme == "light":
            c_pri = "#1a202c"  # Dark text
            c_sec = "#4a5568"
            c_div = "#cbd5e1"
            grad = '<stop offset="0%" stop-color="#FFFFFF"/><stop offset="100%" stop-color="#FFDEAD" stop-opacity="0.2"/>'
            h_c = "#ffffff"    # Light mask (Equal and opposite)

        elif theme == "dark":
            c_pri = "#ffffff"  # Light text
            c_sec = "#d1d5db"
            c_div = "#334155"
            grad = '<stop offset="0%" stop-color="#020617"/><stop offset="100%" stop-color="#1e293b"/>'
            h_c = "#020617"    # Dark mask (Equal and opposite)

        elif theme == "red":
            c_pri = "#ff3333"  # Bright red text
            c_sec = "#990000"
            c_div = "#440000"
            grad = '<stop offset="0%" stop-color="#110000"/><stop offset="100%" stop-color="#000000"/>'
            h_c = "#110000"    # Deep dark red mask (Equal and opposite)

        else: # "system" fallback
            c_pri = "var(--primary-text-color, #ffffff)"
            c_sec = "var(--secondary-text-color, #d1d5db)"
            c_div = "var(--divider-color, #334155)"
            grad = '<stop offset="0%" stop-color="#020617"/><stop offset="100%" stop-color="#1e293b"/>'
            h_c = "#000000"    # Safe dark mask for system default

        # 2. Standardized Astronomical Colors & Scaling
        # Format: "Name": ("Hex Color", Size)
        bodies_conf = {
            "Sun": ("#FDB813", 3.0),
            "Moon": ("#E6E6E6", 3.0),
            "Jupiter": ("#C88B3A", 2.0),
            "Saturn": ("#E3CB8B", 1.7),
            "Venus": ("#F5D76E", 0.9),
            "Mars": ("#E27B58", 0.5),
            "Mercury": ("#97979F", 0.25)
        }

        # 3. Night Vision (Astronomer's Mode) Override
        if theme == "red":
            c_pri = "#ff3333"
            c_sec = "#990000"
            c_div = "#440000"
            grad = '<stop offset="0%" stop-color="#110000"/><stop offset="100%" stop-color="#000000"/>'
            h_c = "#ff0000"
            # Force all planetary bodies to render in pure red
            bodies_conf = {k: ("#ff0000", v[1]) for k, v in bodies_conf.items()}

        svg_defs = [f'<radialGradient id="hG" cx="50%" cy="50%" r="50%">{grad}</radialGradient>',
                    f'<filter id="halo"><feMorphology in="SourceAlpha" result="dilate" radius="0.05"/><feFlood flood-color="{h_c}" flood-opacity="0.9"/><feComposite in2="dilate" operator="in"/><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>']
        
        for name, (color, size) in bodies_conf.items():
            svg_defs.append(f'<radialGradient id="sph_{name}" cx="35%" cy="35%" r="50%"><stop offset="0%" stop-color="#ffffff" stop-opacity="0.5"/><stop offset="100%" stop-color="{color}"/></radialGradient>')

        # ... (The rest of the rendering loop for circles, text, and lines remains identical) ...

        svg = ['<?xml version="1.0" encoding="utf-8"?>',
               f'<svg width="800px" height="800px" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet" xmlns="http://www.w3.org/2000/svg" style="background-color: transparent; border-radius: 50%; color: {c_pri};">',
               f'<defs>{"".join(svg_defs)}</defs>', '<circle cx="50" cy="50" r="42" fill="url(#hG)" />']
        for alt in range(0, 90, 15):
            r = (90 - alt) / 2.15; svg.append(f'<circle cx="50" cy="50" r="{r}" fill="none" stroke="{c_div}" stroke-width="0.35" opacity="0.6" />')
            lx, ly = self.get_projection(225, alt); svg.append(f'<text x="{lx}" y="{ly}" fill="{c_sec}" font-size="2.6" font-weight="bold" text-anchor="middle" filter="url(#halo)">{alt}°</text>')

# Directional Markers (N, NE, E, etc.)
        if show_compass:
            dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"] if not invert else ["S", "SW", "W", "NW", "N", "NE", "E", "SE"]
            for i, label in enumerate(dirs):
                rad = math.radians(i*45-90)
                lx, ly = 50 + 46 * math.cos(rad), 50 + 46 * math.sin(rad)
                fs, fw = ("5.6", "bold") if label in ["N","S","E","W"] else ("4.2", "normal")
                
                # Using paint-order="stroke fill" creates a perfect, elegant outer border
                svg.append(f'<text x="{lx}" y="{ly}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.6" paint-order="stroke fill" stroke-linejoin="round" font-size="{fs}" text-anchor="middle" dominant-baseline="middle" font-weight="{fw}">{label}</text>')

        is_nh = self.lat >= 0
        svg.append(self.get_sun_path(ephem.next_summer_solstice(now_utc) if is_nh else ephem.next_winter_solstice(now_utc), "#ffcc00", 0.4, True))
        svg.append(self.get_sun_path(ephem.next_winter_solstice(now_utc) if is_nh else ephem.next_summer_solstice(now_utc), "#38bdf8", 0.4, True))
        svg.append(self.get_sun_path(ephem.Date(now_utc), "#ffcc00", 0.7, False))

# Constellations
        if opts.get(CONF_SHOW_CONSTELLATIONS):
            show_labels = opts.get(CONF_SHOW_CONST_LABELS, False)
            for abbv, lines in self.constellation_data.items():
                first_pt = None
                for segment in lines:
                    c_pts = []
                    for ra_deg, dec_deg in segment:
                        cs = ephem.FixedBody(); cs._ra, cs._dec = math.radians(ra_deg), math.radians(dec_deg); cs.compute(self.obs)
                        if float(cs.alt) * 57.3 >= -7: 
                            px, py = self.get_projection(float(cs.az)*57.3, float(cs.alt)*57.3)
                            c_pts.append((px, py))
                            if not first_pt: first_pt = (px, py)
                    if len(c_pts) > 1:
                        svg.append(f'<path d="M ' + ' L '.join([f"{p[0]},{p[1]}" for p in c_pts]) + f'" fill="none" stroke="{c_sec}" stroke-width="0.2" opacity="0.5" />')
                
                if show_labels and first_pt:
                    # Translate the abbreviation into the full Latin name
                    full_name = CONSTELLATIONS.get(abbv, abbv)
                    
                    # Apply the paint-order outline so the text pops against the star lines
                    svg.append(f'<text x="{first_pt[0]+1.5}" y="{first_pt[1]+1.5}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.5" paint-order="stroke fill" font-size="2.4" opacity="0.85">{full_name}</text>')

# RESTORED: Planets, Sun, and Moon
        m1, m2 = ephem.Moon(self.obs), ephem.Moon()
        m2.compute(float(self.obs.date) + 0.1); waning = m2.phase < m1.phase

        for name in opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES):
            if name in bodies_conf:
                clr, sz = bodies_conf[name]; b_o = getattr(ephem, name)(); b_o.compute(self.obs)
                alt_deg = float(b_o.alt) * 57.3
                if alt_deg >= -7:
                    px, py = self.get_projection(float(b_o.az)*57.3, alt_deg)
                    if name == "Moon":
                        svg.append(self.draw_moon(px, py, sz, b_o.phase / 100.0, waning, invert, True))
                    else:
                        svg.append(f'<circle cx="{px}" cy="{py}" r="{sz}" fill="url(#sph_{name})" filter="url(#halo)" />')

        svg.append('</svg>')
        return "".join(svg).encode('utf-8')