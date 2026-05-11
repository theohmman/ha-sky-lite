import json, ephem, math, logging
from datetime import datetime, timedelta

from homeassistant.components.image import ImageEntity 
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from homeassistant.helpers.event import async_track_time_interval
from .const import *
from .data_manager import ConstellationManager

_LOGGER = logging.getLogger(__name__)

# NASA/JPL Published Standard Colors + Realistic Proportionate Scaling
# Scale: Sun (3.0), Jupiter 75% (2.25), Mercury 10% (0.3)
BODIES_CONF = {
    "Sun": ("#ffcc00", 3.0),
    "Moon": ("#fff7e6", 3.0),      # Matched Sun scale; warm illuminated white
    "Mercury": ("#8c8c94", 0.30),  # Dark rocky gray
    "Mars": ("#c1440e", 0.33),     # Rust Red
    "Venus": ("#e6e6c8", 0.40),    # Pale Yellowish-White
    "Saturn": ("#ead6b8", 1.91),   # Pale Gold
    "Jupiter": ("#c88b3a", 2.25)   # Tan/Brown (75% of Sun)
}

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat, lon, elev = config_entry.data.get("latitude"), config_entry.data.get("longitude"), config_entry.data.get("elevation")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    manager = ConstellationManager(hass)
    await manager.async_update_data()
    async_add_entities([SkyLiteMapImage(hass, coordinator, config_entry, lat, lon, elev, manager.constellations, manager.star_data, manager.dso_data, manager.mw_data)], False)

class SkyLiteMapImage(ImageEntity):
    def __init__(self, hass, coordinator, entry, lat, lon, elev, constellation_data, star_data, dso_data, mw_data):
        super().__init__(hass) 
        self.coordinator = coordinator 
        self.content_type = "image/svg+xml"
        self.hass, self.entry = hass, entry
        
        # REQUIRED BY HOME ASSISTANT: Prevents the entity from becoming "orphaned"
        self._attr_unique_id = f"{entry.entry_id}_map"
        self._attr_name = "Sky Map"
        
        self.lat_deg, self.lon_deg, self.elev = float(lat), float(lon), float(elev)
        
        self.constellation_data = constellation_data
        self.star_data = star_data 
        self.dso_data = dso_data
        self.mw_data = mw_data
        
        self._cached_svg = None
        self._last_render = None

        self.obs = ephem.Observer()
        self.obs.lat, self.obs.lon, self.obs.elevation = str(self.lat_deg), str(self.lon_deg), self.elev

        # Tell HA when the image was first created
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def extra_state_attributes(self):
        """Fixes the 'Unknown' status by placing it in the attributes where it belongs,
        preventing it from jamming Home Assistant's Websocket push notifications!"""
        opts = self.entry.options
        is_terrestrial = opts.get(CONF_PROJECTION_TERRESTRIAL, False)
        return {"Mode": "Terrestrial" if is_terrestrial else "Astronomical"}

    async def async_added_to_hass(self):
        """Wire the map to listen ONLY to the master Coordinator brain."""
        # The Coordinator in your integration already perfectly tracks the UI slider!
        self.async_on_remove(
            self.coordinator.async_add_listener(self._force_image_refresh)
        )

    @callback
    def _force_image_refresh(self):
        """When the main brain ticks, annihilate the caches and push the UI update."""
        self._attr_image_last_updated = dt_util.utcnow()
        
        # Destroy BOTH caches
        self._cached_image = None  
        self._cached_svg = None    
        
        # Broadcast the timestamp change so the browser instantly refreshes the image
        self.async_write_ha_state()

    def _radec_to_azalt(self, ra_deg, dec_deg, lst_rad, sin_lat, cos_lat):
        ra_rad, dec_rad = math.radians(ra_deg), math.radians(dec_deg)
        ha_rad = lst_rad - ra_rad
        sin_dec, cos_dec = math.sin(dec_rad), math.cos(dec_rad)
        
        sin_alt = sin_lat * sin_dec + cos_lat * cos_dec * math.cos(ha_rad)
        sin_alt = max(-1.0, min(1.0, sin_alt))
        alt_rad = math.asin(sin_alt)
        
        cos_az = (sin_dec - sin_lat * sin_alt) / (cos_lat * math.cos(alt_rad)) if math.cos(alt_rad) != 0 else 0
        cos_az = max(-1.0, min(1.0, cos_az))
        az_rad = math.acos(cos_az)
        
        if math.sin(ha_rad) > 0: az_rad = 2 * math.pi - az_rad
        return math.degrees(az_rad), math.degrees(alt_rad)

    def get_projection(self, az_deg, alt_deg):
        is_terrestrial = self.entry.options.get(CONF_PROJECTION_TERRESTRIAL, False)
        base_angle = (360 - az_deg) if not is_terrestrial else az_deg
        if self.entry.options.get(CONF_INVERT_PLOT, False):
            base_angle = (base_angle + 180) % 360
        r_svg = 41.86 * ((90 - alt_deg) / 90)
        rad = math.radians(base_angle - 90)
        return 50 + r_svg * math.cos(rad), 50 + r_svg * math.sin(rad)

    def image(self):
        try:
            opts = self.entry.options
            update_interval = int(opts.get(CONF_UPDATE_INTERVAL, "1"))
            now = datetime.now()

            cached_svg = getattr(self, '_cached_svg', None)
            last_render = getattr(self, '_last_render', None)
            if cached_svg and last_render:
                if now - last_render < timedelta(minutes=update_interval):
                    return cached_svg

            self.obs.date = ephem.now()
            is_terrestrial = opts.get(CONF_PROJECTION_TERRESTRIAL, False)
            
            theme = opts.get(CONF_THEME_MODE, "system")
            is_dark = True
            if theme == "light": is_dark = False
            elif theme == "system" or theme == "auto":
                sun_state = self.hass.states.get("sun.sun")
                if sun_state and sun_state.state == "above_horizon": is_dark = False

            if theme == "red": bg_color, c_pri, c_sec, c_div, h_c = "#110000", "#ff0000", "#880000", "#550000", "#000000"
            elif is_dark: bg_color, c_pri, c_sec, c_div, h_c = "#0f172a", "#f1f5f9", "#64748b", "#334155", "#020617"
            else: bg_color, c_pri, c_sec, c_div, h_c = "#ffffff", "#0f172a", "#475569", "#94a3b8", "#ffffff"

            svg = []
            svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%" style="background-color: transparent;">')
            
            svg.append('<defs>')
            svg.append('<filter id="halo" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="0.4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
            svg.append('<clipPath id="skyClip"><circle cx="50" cy="50" r="41.86" /></clipPath>')
            svg.append(f'<radialGradient id="skyGrad" cx="50%" cy="50%" r="50%">')
            svg.append(f'<stop offset="30%" stop-color="{bg_color}" />')
            svg.append(f'<stop offset="100%" stop-color="{c_div}" stop-opacity="0.3" />')
            svg.append('</radialGradient>')
            if opts.get(CONF_SHOW_MILKY_WAY, False) and getattr(self, 'mw_data', None):
                svg.append('<filter id="mwBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.8" /></filter>')
            svg.append('</defs>')

            show_mw = opts.get(CONF_SHOW_MILKY_WAY, False) and getattr(self, 'mw_data', None)
            bg_fill = '"transparent"' if show_mw else '"url(#skyGrad)"'
            svg.append(f'<circle cx="50" cy="50" r="41.86" fill={bg_fill} stroke="{c_div}" stroke-width="0.4" />')

            # --- 1. DIRECTIONAL INDICATORS ---
            for r_deg in range(0, 90, 15):
                r_svg = 41.86 * ((90 - r_deg) / 90)
                
                # Only draw the grid ring if it is > 0 (The 0 degree rim is already drawn by the background map)
                if r_deg > 0:
                    svg.append(f'<circle cx="50" cy="50" r="{r_svg}" fill="none" stroke="{c_div}" stroke-width="0.35" opacity="0.6" />')
                
                base_angle = 45 if not is_terrestrial else 315
                if opts.get(CONF_INVERT_PLOT, False): base_angle = (base_angle + 180) % 360
                rad = math.radians(base_angle - 90)
                tx, ty = 50 + r_svg * math.cos(rad), 50 + r_svg * math.sin(rad)
                
                # BUMPED: Font size to 2.0 and opacity to 0.85 for high legibility on mobile screens
                svg.append(f'<text x="{tx}" y="{ty}" fill="{c_sec}" stroke="{bg_color}" stroke-width="0.5" paint-order="stroke fill" font-size="2.0" opacity="0.85" text-anchor="middle" dominant-baseline="middle">{r_deg}°</text>')

            for az in range(0, 360, 45):
                is_major = (az % 90 == 0)
                sw, opac = ("0.45", "0.8") if is_major else ("0.2", "0.45")
                base_angle = (360 - az) if not is_terrestrial else az
                if opts.get(CONF_INVERT_PLOT, False): base_angle = (base_angle + 180) % 360
                rad = math.radians(base_angle - 90)
                x2, y2 = 50 + 41.86 * math.cos(rad), 50 + 41.86 * math.sin(rad)
                svg.append(f'<line x1="50" y1="50" x2="{x2}" y2="{y2}" stroke="{c_div}" stroke-width="{sw}" opacity="{opac}" stroke-dasharray="1,1.5" />')

            lst_rad = float(self.obs.sidereal_time())
            lat_rad = float(self.obs.lat)
            sin_lat, cos_lat = math.sin(lat_rad), math.cos(lat_rad)

            # --- 2. SOLAR PATHS (Z-INDEX: BEHIND THE UNIVERSE) ---
            selected_bodies = opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES)
            if any(b.lower() == "sun" for b in selected_bodies):
                sun_obj = ephem.Sun()
                sun_obj.compute(self.obs)
                current_dec = math.degrees(sun_obj.dec)
                
                # Dynamic Spectrum Color Math
                t = max(0.0, min(1.0, (current_dec + 23.44) / 46.88))
                if t <= 0.5:
                    t_sub = t * 2.0
                    td_col = f"#{int(0 + t_sub * 170):02x}{int(170 + t_sub * 85):02x}{int(255 - t_sub * 255):02x}"
                else:
                    t_sub = (t - 0.5) * 2.0
                    td_col = f"#{int(170 + t_sub * 85):02x}{int(255 - t_sub * 170):02x}00"

                # (Dec, StrokeWidth, Opacity, Dash, Hex Color)
                solar_lines = [
                    (23.44, "0.35", "0.6", "2,2", "#ff5500"),       # Summer (Warm Orange)
                    (-23.44, "0.35", "0.6", "2,2", "#00aaff"),      # Winter (Icy Blue)
                    (0.0, "0.35", "0.6", "4,4", "#aaff00"),         # Equinox (Spring Green)
                    (current_dec, "0.6", "0.85", "", td_col)        # Today (Interpolated)
                ]
                
                for dec, sw, opac, dash, col in solar_lines:
                    path_pts = []
                    for ha_deg in range(-180, 185, 4):
                        ha_r, dec_r = math.radians(ha_deg), math.radians(dec)
                        sin_alt = sin_lat * math.sin(dec_r) + cos_lat * math.cos(dec_r) * math.cos(ha_r)
                        alt_p = math.degrees(math.asin(sin_alt))
                        if alt_p >= -7:
                            cos_az = (math.sin(dec_r) - sin_lat * sin_alt) / (cos_lat * math.cos(math.asin(sin_alt)))
                            az_r = math.acos(max(-1.0, min(1.0, cos_az)))
                            if math.sin(ha_r) > 0: az_r = 2 * math.pi - az_r
                            px, py = self.get_projection(math.degrees(az_r), alt_p)
                            path_pts.append(f"{px},{py}")
                        elif path_pts:
                            dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
                            svg.append(f'<path d="M ' + ' L '.join(path_pts) + f'" fill="none" stroke="{col}" stroke-width="{sw}" opacity="{opac}"{dash_attr} filter="url(#halo)" />')
                            path_pts = []
                    if len(path_pts) > 1:
                        dash_attr = f' stroke-dasharray="{dash}"' if dash else ''
                        svg.append(f'<path d="M ' + ' L '.join(path_pts) + f'" fill="none" stroke="{col}" stroke-width="{sw}" opacity="{opac}"{dash_attr} filter="url(#halo)" />')

            # --- 3. DEEP SKY OBJECTS ---
            if opts.get(CONF_SHOW_MILKY_WAY, False) and getattr(self, 'mw_data', None):
                svg.append('<g clip-path="url(#skyClip)" filter="url(#mwBlur)">') 
                for multipoly in self.mw_data:
                    for poly in multipoly:
                        for ring in poly:
                            path_pts = []
                            for pt in ring[::4]:
                                az_deg, alt_deg = self._radec_to_azalt(pt[0], pt[1], lst_rad, sin_lat, cos_lat)
                                px, py = self.get_projection(az_deg, alt_deg)
                                if path_pts:
                                    last_x, last_y = map(float, path_pts[-1].split(","))
                                    if math.hypot(px - last_x, py - last_y) > 50:
                                        if len(path_pts) > 2: svg.append(f'<path d="M ' + ' L '.join(path_pts) + f' Z" fill="none" stroke="{c_sec}" stroke-width="4.5" opacity="0.12" stroke-linejoin="round" />')
                                        path_pts = [] 
                                path_pts.append(f"{px},{py}")
                            if len(path_pts) > 2: svg.append(f'<path d="M ' + ' L '.join(path_pts) + f' Z" fill="none" stroke="{c_sec}" stroke-width="4.5" opacity="0.12" stroke-linejoin="round" />')
                svg.append('</g>')

            if opts.get(CONF_SHOW_CONSTELLATIONS, False) and getattr(self, 'constellation_data', None):
                svg.append('<g clip-path="url(#skyClip)">')
                for cid, lines in self.constellation_data.items():
                    for line in lines:
                        path_pts = []
                        for pt in line:
                            az_deg, alt_deg = self._radec_to_azalt(pt[0], pt[1], lst_rad, sin_lat, cos_lat)
                            if alt_deg >= -7:
                                px, py = self.get_projection(az_deg, alt_deg)
                                path_pts.append(f"{px},{py}")
                        if len(path_pts) > 1: svg.append(f'<path d="M ' + ' L '.join(path_pts) + f'" fill="none" stroke="{c_div}" stroke-width="0.3" opacity="0.5" />')
                svg.append('</g>')

            if opts.get(CONF_SHOW_STARS, True) and getattr(self, 'star_data', None):
                for star in self.star_data:
                    az_deg, alt_deg = self._radec_to_azalt(star.get("coords", [0, 0])[0], star.get("coords", [0, 0])[1], lst_rad, sin_lat, cos_lat)
                    if alt_deg >= -7:
                        px, py = self.get_projection(az_deg, alt_deg)
                        r, opac = max(0.08, 0.6 - (star.get("mag", 5.0) * 0.1)), max(0.1, 0.85 - (star.get("mag", 5.0) * 0.12))
                        svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="{c_sec}" opacity="{opac}" />')

            if opts.get(CONF_SHOW_DSO, False) and getattr(self, 'dso_data', None):
                for dso in self.dso_data:
                    az_deg, alt_deg = self._radec_to_azalt(dso.get("coords", [0, 0])[0], dso.get("coords", [0, 0])[1], lst_rad, sin_lat, cos_lat)
                    if alt_deg >= -7:
                        px, py = self.get_projection(az_deg, alt_deg)
                        r, opac = max(0.4, 1.2 - (dso.get("mag", 6.0) * 0.15)), max(0.25, 0.85 - (dso.get("mag", 6.0) * 0.1))
                        svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="#38bdf8" opacity="{opac}" filter="url(#halo)" />')
                        if opts.get(CONF_SHOW_DSO_LABELS, False) and dso.get("name", ""):
                            svg.append(f'<text x="{px+1.5}" y="{py+1.5}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.3" paint-order="stroke fill" font-size="1.4" opacity="0.65">{dso.get("name", "")}</text>')

            if opts.get(CONF_SHOW_CONST_LABELS, False) and getattr(self, 'constellation_data', None):
                for cid, lines in self.constellation_data.items():
                    label = CONSTELLATIONS.get(cid, cid)
                    pts = [self.get_projection(*self._radec_to_azalt(pt[0], pt[1], lst_rad, sin_lat, cos_lat)) for line in lines for pt in line if self._radec_to_azalt(pt[0], pt[1], lst_rad, sin_lat, cos_lat)[1] >= 0]
                    if pts:
                        cx, cy = sum(p[0] for p in pts)/len(pts), sum(p[1] for p in pts)/len(pts)
                        svg.append(f'<text x="{cx}" y="{cy}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.4" paint-order="stroke fill" font-size="1.8" opacity="0.85" text-anchor="middle" dominant-baseline="middle">{label}</text>')

            # --- 4. PLANETS (ON TOP) ---
            if selected_bodies:
                ephem_map = {"Sun": ephem.Sun, "Moon": ephem.Moon, "Mercury": ephem.Mercury, "Venus": ephem.Venus, "Mars": ephem.Mars, "Jupiter": ephem.Jupiter, "Saturn": ephem.Saturn}
                for body_name in selected_bodies:
                    if body_name not in ephem_map: continue
                    body_obj = ephem_map[body_name]()
                    body_obj.compute(self.obs)
                    alt, az = math.degrees(body_obj.alt), math.degrees(body_obj.az)
                    
                    if alt >= -7:
                        px, py = self.get_projection(az, alt)
                        color, r = BODIES_CONF.get(body_name, ("#ffffff", 2.0))
                        
                        # --- MOON
                        if body_name in ["Moon", "moon"]:
                            illum = body_obj.phase / 100.0
                            
                            sun_obj = ephem.Sun()
                            sun_obj.compute(self.obs)
                            angle = (body_obj.ra - sun_obj.ra) % (2 * math.pi)
                            is_waxing = angle < math.pi

                            # DYNAMIC DARK DISK: Earthshine shadow instead of a black void
                            m_bg = "#330000" if theme == "red" else "#1e293b"
                            svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="{m_bg}" stroke="{color}" stroke-width="0.3" filter="url(#halo)" />')
                            
                            mx = r * (1.0 - 2.0 * illum)
                            
                            sweep_outer = "1" if is_waxing else "0"
                            sweep_inner = "0" if is_waxing else "1"
                            
                            if illum <= 0.5:
                                path = f"M {px},{py-r} A {r},{r} 0 0,{sweep_outer} {px},{py+r} A {abs(mx)},{r} 0 0,{sweep_inner} {px},{py-r}"
                            else:
                                path = f"M {px},{py-r} A {r},{r} 0 0,{sweep_outer} {px},{py+r} A {abs(mx)},{r} 0 0,{sweep_outer} {px},{py-r}"
                                
                            svg.append(f'<path d="{path}" fill="{color}" />')
                        else:

                            svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="{color}" filter="url(#halo)" />')
                        # Labels intentionally removed per requirements

            # --- 5. COMPASS & HUD OVERLAY ---
            if opts.get(CONF_SHOW_COMPASS, True):
                for label, az in [("N",0), ("NE",45), ("E",90), ("SE",135), ("S",180), ("SW",225), ("W",270), ("NW",315)]:
                    base_angle = (360 - az) if not is_terrestrial else az
                    if opts.get(CONF_INVERT_PLOT, False): base_angle = (base_angle + 180) % 360
                    rad = math.radians(base_angle - 90)
                    lx, ly = 50 + 46 * math.cos(rad), 50 + 46 * math.sin(rad)
                    fs, fw = ("3.6", "bold") if label in ["N","S","E","W"] else ("2.6", "normal")
                    is_focus = ly < 10 if is_terrestrial else ly > 90
                    txt_c, opac = (c_pri, "1.0") if is_focus else (c_sec, "0.7")
                    
                    if is_focus:
                        # The \u1430 Human Observer
                        # DYNAMIC SPACING: 3.5 clears the E/W line in Astro, 1.8 tucks it against the Zenith in Terr
                        z_offset = 1.8 if is_terrestrial else 3.5
                        cx, cy = 50 + z_offset * math.cos(rad), 50 + z_offset * math.sin(rad)
                        
                        # DYNAMIC FLIP: 
                        # Astronomical: Head looks up to Zenith (-90)
                        # Terrestrial: Feet plant down toward Zenith (+90)
                        rot_offset = 90 if is_terrestrial else -90
                        rot = math.degrees(rad) + rot_offset
                        
                        svg.append(f'<text x="{cx}" y="{cy}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.3" paint-order="stroke fill" font-size="4.5" text-anchor="middle" dominant-baseline="middle" transform="rotate({rot} {cx} {cy})" filter="url(#halo)" opacity="0.9">\u1430</text>')
                        
                    # THE MISSING LINE: This actually draws the N, S, E, W labels!
                    svg.append(f'<text x="{lx}" y="{ly}" fill="{txt_c}" stroke="{h_c}" stroke-width="0.6" paint-order="stroke fill" stroke-linejoin="round" font-size="{fs}" text-anchor="middle" dominant-baseline="middle" font-weight="{fw}" opacity="{opac}">{label}</text>')

            # --- CURVED HUD TIMESTAMP ---
            now_local = datetime.now().strftime("%Y%m%d.%H:%M:%S")
            mode_str = "T" if is_terrestrial else "A"
            hud_str = f"{mode_str}: {now_local}"
            
            svg.append('<path id="hudCurve" d="M 3.5,50 A 46.5,46.5 0 0,1 96.5,50" fill="none" stroke="none" />')
            
            # Adjusted startOffset from 25% to 37.5% (Precisely bisecting NW and North)
            svg.append(f'<text fill="{c_sec}" font-size="1.6" opacity="0.75"><textPath href="#hudCurve" startOffset="37.5%" text-anchor="middle">{hud_str}</textPath></text>')

            svg.append('</svg>')
            svg_bytes = "".join(svg).encode('utf-8')
            self._cached_svg = svg_bytes
            self._last_render = now
            return svg_bytes

        except Exception as e:
            import traceback
            err_str = str(e).replace('"', "'").replace('<', '').replace('>', '')
            err_svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%"><rect width="100" height="100" fill="#3f0000" /><text x="50" y="45" fill="#ff8888" font-size="4" text-anchor="middle" font-weight="bold">RENDER ERROR</text><text x="50" y="55" fill="#ffffff" font-size="2.5" text-anchor="middle">{type(e).__name__}: {err_str}</text></svg>']
            return "".join(err_svg).encode('utf-8')