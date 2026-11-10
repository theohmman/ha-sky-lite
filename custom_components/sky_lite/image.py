import math, logging
from datetime import datetime, timedelta

from homeassistant.components.image import ImageEntity
from homeassistant.core import callback
from homeassistant.util import dt as dt_util
from .const import *

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    lat = config_entry.data.get("latitude")
    lon = config_entry.data.get("longitude")
    elev = config_entry.data.get("elevation")
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    manager = hass.data[DOMAIN]["static_manager"]

    # Sky Map and Sky Glance entities
    async_add_entities([
        SkyLiteMapImage(hass, coordinator, config_entry, lat, lon, elev, manager.constellations, manager.star_data, manager.dso_data, manager.mw_data),
        SkyLiteGlanceImage(hass, coordinator, config_entry, lat, lon, elev)
    ], False)


# Sky Map
class SkyLiteMapImage(ImageEntity):
    def __init__(self, hass, coordinator, entry, lat, lon, elev, constellation_data, star_data, dso_data, mw_data):
        super().__init__(hass)
        self.coordinator = coordinator
        self.content_type = "image/svg+xml"
        self.hass, self.entry = hass, entry

        self._attr_unique_id = f"{entry.entry_id}_map"
        self._attr_name = "Sky Map"

        self.lat_deg, self.lon_deg, self.elev = float(lat), float(lon), float(elev)

        self.constellation_data = constellation_data
        self.star_data = star_data
        self.dso_data = dso_data
        self.mw_data = mw_data

        self._cached_svg = None
        self._last_render = None
        self._attr_image_last_updated = dt_util.utcnow()

    @property
    def extra_state_attributes(self):
        opts = self.entry.options
        is_terrestrial = opts.get(CONF_PROJECTION_TERRESTRIAL, False)
        return {"Mode": "Terrestrial" if is_terrestrial else "Astronomical"}

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self._force_image_refresh)
        )

    @callback
    def _force_image_refresh(self):
        self._attr_image_last_updated = dt_util.utcnow()
        self._cached_image = None
        self._cached_svg = None
        self.async_write_ha_state()

    def _get_comp_color(self, hex_color):
        hc = hex_color.lstrip('#')
        if len(hc) != 6: return "#ffffff"
        r = 255 - int(hc[0:2], 16)
        g = 255 - int(hc[2:4], 16)
        b = 255 - int(hc[4:6], 16)
        return f"#{r:02x}{g:02x}{b:02x}"

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
            if self._cached_svg is not None:
                return self._cached_svg

            data = self.coordinator.data
            if not data or "bodies" not in data:
                return b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"/>'

            opts = self.entry.options
            is_terrestrial = opts.get(CONF_PROJECTION_TERRESTRIAL, False)

            theme = opts.get(CONF_THEME_MODE, "system")
            if theme not in ("system", "light", "dark", "red"):
                theme = "system"

            # Standalone Theme Palettes: (bg_color, c_pri, c_sec, c_div, h_c, m_bg)
            PALETTES = {
                "dark":  ("#0f172a", "#f8fafc", "#94a3b8", "#334155", "#020617", "#1e293b"),
                "light": ("#ffffff", "#0f172a", "#334155", "#94a3b8", "#ffffff", "#1e293b"),
                "red":   ("#110000", "#ff0000", "#aa0000", "#550000", "#000000", "#330000"),
            }

            if theme == "system":
                l_p = PALETTES["light"]
                d_p = PALETTES["dark"]
                theme_css = f"""
                    :root {{
                        --bg: {l_p[0]}; --pri: {l_p[1]}; --sec: {l_p[2]};
                        --div: {l_p[3]}; --hc: {l_p[4]}; --mbg: {l_p[5]};
                    }}
                    @media (prefers-color-scheme: dark) {{
                        :root {{
                            --bg: {d_p[0]}; --pri: {d_p[1]}; --sec: {d_p[2]};
                            --div: {d_p[3]}; --hc: {d_p[4]}; --mbg: {d_p[5]};
                        }}
                    }}
                """
            else:
                p = PALETTES[theme]
                theme_css = f"""
                    :root {{
                        --bg: {p[0]}; --pri: {p[1]}; --sec: {p[2]};
                        --div: {p[3]}; --hc: {p[4]}; --mbg: {p[5]};
                    }}
                """

            bg_color = "var(--bg)"
            c_pri = "var(--pri)"
            c_sec = "var(--sec)"
            c_div = "var(--div)"
            h_c = "var(--hc)"
            m_bg = "var(--mbg)"

            svg = []
            svg.append('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="1000" height="1000" preserveAspectRatio="xMidYMid meet" style="width: 100%; height: auto; background-color: transparent;">')

            svg.append('<defs>')
            svg.append(f'<style>{theme_css}</style>')
            svg.append('<filter id="halo" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="0.4" result="coloredBlur"/><feMerge><feMergeNode in="coloredBlur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>')
            svg.append('<filter id="dsoBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="0.7" /></filter>')
            svg.append('<filter id="glowBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="0.5" /></filter>')
            svg.append('<clipPath id="skyClip"><circle cx="50" cy="50" r="41.86" /></clipPath>')
            svg.append('<radialGradient id="skyGrad" cx="50%" cy="50%" r="50%">')
            svg.append(f'<stop offset="30%" style="stop-color: {bg_color};" />')
            svg.append(f'<stop offset="100%" style="stop-color: {c_div}; stop-opacity: 0.3;" />')
            svg.append('</radialGradient>')
            if opts.get(CONF_SHOW_MILKY_WAY, False) and getattr(self, 'mw_data', None):
                svg.append('<filter id="mwBlur" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="1.8" /></filter>')
            svg.append('</defs>')

            # Interior sky globe always rendered with url(#skyGrad) so opposite-mode card background never bleeds
            svg.append(f'<circle cx="50" cy="50" r="41.86" fill="url(#skyGrad)" stroke="{c_div}" stroke-width="0.4" />')

            for r_deg in range(0, 90, 15):
                r_svg = 41.86 * ((90 - r_deg) / 90)
                if r_deg > 0:
                    svg.append(f'<circle cx="50" cy="50" r="{r_svg}" fill="none" stroke="{c_div}" stroke-width="0.35" opacity="0.6" />')

                base_angle = 45 if not is_terrestrial else 315
                if opts.get(CONF_INVERT_PLOT, False): base_angle = (base_angle + 180) % 360
                rad = math.radians(base_angle - 90)
                tx, ty = 50 + r_svg * math.cos(rad), 50 + r_svg * math.sin(rad)
                svg.append(f'<text x="{tx}" y="{ty}" fill="{c_sec}" stroke="{bg_color}" stroke-width="0.5" paint-order="stroke fill" font-size="2.0" opacity="0.85" text-anchor="middle" dominant-baseline="middle">{r_deg}°</text>')

            for az in range(0, 360, 45):
                is_major = (az % 90 == 0)
                sw, opac = ("0.45", "0.8") if is_major else ("0.2", "0.45")
                base_angle = (360 - az) if not is_terrestrial else az
                if opts.get(CONF_INVERT_PLOT, False): base_angle = (base_angle + 180) % 360
                rad = math.radians(base_angle - 90)
                x2, y2 = 50 + 41.86 * math.cos(rad), 50 + 41.86 * math.sin(rad)

                line_color = "#22c55e" if round(y2, 2) >= 50.00 else "#3b82f6"
                svg.append(f'<line x1="50" y1="50" x2="{x2}" y2="{y2}" stroke="{line_color}" stroke-width="{sw}" opacity="{opac}" stroke-dasharray="1,1.5" />')

            lst_rad = data["lst_rad"]
            lat_rad = data["lat_rad"]
            sin_lat, cos_lat = math.sin(lat_rad), math.cos(lat_rad)

            selected_bodies = opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES)
            if any(b.lower() == "sun" for b in selected_bodies):
                current_dec = data["sun_dec_deg"]

                t = max(0.0, min(1.0, (current_dec + 23.44) / 46.88))
                if t <= 0.5:
                    t_sub = t * 2.0
                    td_col = f"#{int(0 + t_sub * 170):02x}{int(170 + t_sub * 85):02x}{int(255 - t_sub * 255):02x}"
                else:
                    t_sub = (t - 0.5) * 2.0
                    td_col = f"#{int(170 + t_sub * 85):02x}{int(255 - t_sub * 170):02x}00"

                solar_lines = [
                    (23.44, "0.35", "0.6", "2,2", "#ff5500"),
                    (-23.44, "0.35", "0.6", "2,2", "#00aaff"),
                    (0.0, "0.35", "0.6", "4,4", "#aaff00"),
                    (current_dec, "0.6", "0.85", "", td_col)
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

            show_const_lines = opts.get(CONF_SHOW_CONSTELLATIONS, False)
            show_const_labels = opts.get(CONF_SHOW_CONST_LABELS, False)
            const_centroids = {}

            if (show_const_lines or show_const_labels) and getattr(self, 'constellation_data', None):
                if show_const_lines:
                    svg.append('<g clip-path="url(#skyClip)">')
                for cid, lines in self.constellation_data.items():
                    label_pts = []
                    for line in lines:
                        path_pts = []
                        for pt in line:
                            az_deg, alt_deg = self._radec_to_azalt(pt[0], pt[1], lst_rad, sin_lat, cos_lat)
                            if alt_deg >= -7:
                                px, py = self.get_projection(az_deg, alt_deg)
                                if show_const_lines:
                                    path_pts.append(f"{px},{py}")
                                if show_const_labels and alt_deg >= 0:
                                    label_pts.append((px, py))
                        if show_const_lines and len(path_pts) > 1:
                            svg.append(f'<path d="M ' + ' L '.join(path_pts) + f'" fill="none" stroke="{c_div}" stroke-width="0.3" opacity="0.5" />')
                    if show_const_labels and label_pts:
                        const_centroids[cid] = (
                            sum(p[0] for p in label_pts) / len(label_pts),
                            sum(p[1] for p in label_pts) / len(label_pts),
                        )
                if show_const_lines:
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
                        r, opac = max(0.8, 1.6 - (dso.get("mag", 6.0) * 0.15)), max(0.35, 0.95 - (dso.get("mag", 6.0) * 0.1))
                        svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="#38bdf8" opacity="{opac}" filter="url(#dsoBlur)" />')
                        if opts.get(CONF_SHOW_DSO_LABELS, False) and dso.get("name", ""):
                            svg.append(f'<text x="{px+1.5}" y="{py+1.5}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.3" paint-order="stroke fill" font-size="1.4" opacity="0.65">{dso.get("name", "")}</text>')

            if show_const_labels and const_centroids:
                for cid, (cx, cy) in const_centroids.items():
                    label = CONSTELLATIONS.get(cid, cid)
                    svg.append(f'<text x="{cx}" y="{cy}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.4" paint-order="stroke fill" font-size="1.8" opacity="0.85" text-anchor="middle" dominant-baseline="middle">{label}</text>')

            if selected_bodies:
                for body_name in selected_bodies:
                    b_info = data["bodies"].get(body_name)
                    if not b_info:
                        continue
                    alt, az = b_info["alt"], b_info["az"]

                    if alt >= -7:
                        px, py = self.get_projection(az, alt)
                        color, r = BODIES_CONF.get(body_name, ("#ffffff", 2.0))
                        comp_color = self._get_comp_color(color)

                        if body_name.lower() == "moon":
                            illum = data["moon_phase"]
                            is_waxing = not data["moon_waning"]

                            svg.append(f'<circle cx="{px}" cy="{py}" r="{r*1.5}" fill="{comp_color}" filter="url(#glowBlur)" opacity="0.8" />')
                            svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="{m_bg}" stroke="{color}" stroke-width="0.3" />')

                            mx = r * (1.0 - 2.0 * illum)
                            sweep_outer = "1" if is_waxing else "0"
                            sweep_inner = "0" if is_waxing else "1"

                            if illum <= 0.5:
                                path = f"M {px},{py-r} A {r},{r} 0 0,{sweep_outer} {px},{py+r} A {abs(mx)},{r} 0 0,{sweep_inner} {px},{py-r}"
                            else:
                                path = f"M {px},{py-r} A {r},{r} 0 0,{sweep_outer} {px},{py+r} A {abs(mx)},{r} 0 0,{sweep_outer} {px},{py-r}"

                            svg.append(f'<path d="{path}" fill="{color}" />')
                        else:
                            svg.append(f'<circle cx="{px}" cy="{py}" r="{r*1.5}" fill="{comp_color}" filter="url(#glowBlur)" opacity="0.8" />')
                            svg.append(f'<circle cx="{px}" cy="{py}" r="{r}" fill="{color}" />')

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
                        z_offset = 1.8 if is_terrestrial else 3.5
                        cx, cy = 50 + z_offset * math.cos(rad), 50 + z_offset * math.sin(rad)

                        rot_offset = 90 if is_terrestrial else -90
                        rot = math.degrees(rad) + rot_offset

                        svg.append(f'<text x="{cx}" y="{cy}" fill="{c_pri}" stroke="{h_c}" stroke-width="0.3" paint-order="stroke fill" font-size="4.5" text-anchor="middle" dominant-baseline="middle" transform="rotate({rot} {cx} {cy})" filter="url(#halo)" opacity="0.9">\u1430</text>')

                    svg.append(f'<text x="{lx}" y="{ly}" fill="{txt_c}" stroke="{h_c}" stroke-width="0.6" paint-order="stroke fill" stroke-linejoin="round" font-size="{fs}" text-anchor="middle" dominant-baseline="middle" font-weight="{fw}" opacity="{opac}">{label}</text>')

            now_local = data["timestamp_local"].strftime("%Y%m%d.%H:%M:%S")
            mode_str = "T" if is_terrestrial else "A"
            hud_str = f"{mode_str}: {now_local}"

            svg.append('<path id="hudCurve" d="M 3.5,50 A 46.5,46.5 0 0,1 96.5,50" fill="none" stroke="none" />')
            svg.append(f'<text fill="{c_sec}" stroke="{h_c}" stroke-width="0.6" paint-order="stroke fill" stroke-linejoin="round" font-size="2.6" opacity="0.85"><textPath href="#hudCurve" startOffset="37.5%" text-anchor="middle">{hud_str}</textPath></text>')

            svg.append('</svg>')
            svg_bytes = "".join(svg).encode('utf-8')
            self._cached_svg = svg_bytes
            self._last_render = data["timestamp_local"]
            return svg_bytes

        except Exception as e:
            err_str = str(e).replace('"', "'").replace('<', '').replace('>', '')
            err_svg = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100" width="100%" height="100%"><rect width="100" height="100" fill="#3f0000" /><text x="50" y="45" fill="#ff8888" font-size="4" text-anchor="middle" font-weight="bold">RENDER ERROR</text><text x="50" y="55" fill="#ffffff" font-size="2.5" text-anchor="middle">{type(e).__name__}: {err_str}</text></svg>']
            return "".join(err_svg).encode('utf-8')


# Sky Glance
class SkyLiteGlanceImage(ImageEntity):
    def __init__(self, hass, coordinator, entry, lat, lon, elev):
        super().__init__(hass)
        self.coordinator = coordinator
        self.content_type = "image/svg+xml"
        self.hass, self.entry = hass, entry

        self._attr_unique_id = f"{entry.entry_id}_glance"
        self._attr_name = "Sky Glance"

        self.lat_deg, self.lon_deg, self.elev = float(lat), float(lon), float(elev)

        self._cached_svg = None
        self._last_render = None
        self._attr_image_last_updated = dt_util.utcnow()

    async def async_added_to_hass(self):
        self.async_on_remove(
            self.coordinator.async_add_listener(self._force_image_refresh)
        )

    @callback
    def _force_image_refresh(self):
        self._attr_image_last_updated = dt_util.utcnow()
        self._cached_image = None
        self._cached_svg = None
        self.async_write_ha_state()

    def image(self):
        try:
            if self._cached_svg is not None:
                return self._cached_svg

            data = self.coordinator.data
            if not data or "bodies" not in data or "glance" not in data:
                return b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 160"/>'

            opts = self.entry.options
            glance = data["glance"]

            current_sun_alt = data["bodies"]["Sun"]["alt"]
            current_sun_az = data["bodies"]["Sun"]["az"]
            current_moon_alt = data["bodies"]["Moon"]["alt"]
            current_moon_az = data["bodies"]["Moon"]["az"]

            sun_alt_str = f"{current_sun_alt:.1f}°"
            sun_az_str = f"{current_sun_az:.1f}°"
            moon_alt_str = f"{current_moon_alt:.1f}°"
            moon_az_str = f"{current_moon_az:.1f}°"

            # --- THEME ENGINE (System Default, Light, Dark, Red) ---
            theme = opts.get(CONF_THEME_MODE, "system")
            if theme not in ("system", "light", "dark", "red"):
                theme = "system"

            time_format_pref = opts.get(CONF_TIME_FORMAT, "12h")
            is_24h = (time_format_pref == "24h")

            def format_time(dt_obj):
                if dt_obj is None:
                    return "--:--"
                if is_24h:
                    return dt_obj.strftime("%H:%M")
                return dt_obj.strftime("%-I:%M%p").lower()

            # Palettes: (c_pri, c_sec, h_c, m_fg, m_gl)
            GLANCE_PALETTES = {
                "dark":  ("#f8fafc", "#cbd5e1", "#020617", "#fff7e6", "#ffffff"),
                "light": ("#0f172a", "#334155", "#ffffff", "#f8fafc", "#ffffff"),
                "red":   ("#ff0000", "#cc0000", "#000000", "#ff0000", "#880000"),
            }

            if theme == "system":
                l_p = GLANCE_PALETTES["light"]
                d_p = GLANCE_PALETTES["dark"]
                theme_vars_css = f"""
                    :root {{
                        --pri: {l_p[0]}; --sec: {l_p[1]}; --hc: {l_p[2]};
                        --mfg: {l_p[3]}; --mgl: {l_p[4]};
                    }}
                    @media (prefers-color-scheme: dark) {{
                        :root {{
                            --pri: {d_p[0]}; --sec: {d_p[1]}; --hc: {d_p[2]};
                            --mfg: {d_p[3]}; --mgl: {d_p[4]};
                        }}
                    }}
                """
            else:
                p = GLANCE_PALETTES[theme]
                theme_vars_css = f"""
                    :root {{
                        --pri: {p[0]}; --sec: {p[1]}; --hc: {p[2]};
                        --mfg: {p[3]}; --mgl: {p[4]};
                    }}
                """

            c_pri = "var(--pri)"
            c_sec = "var(--sec)"
            h_c = "var(--hc)"
            m_fg = "var(--mfg)"
            m_gl = "var(--mgl)"

            # --- LINEAR INTERPOLATION (LERP) ENGINE ---
            def hex_to_rgb(h):
                h = h.lstrip('#')
                return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

            def rgb_to_hex(r, g, b):
                return f'#{int(r):02x}{int(g):02x}{int(b):02x}'

            def lerp_color(c1, c2, t):
                r1, g1, b1 = hex_to_rgb(c1)
                r2, g2, b2 = hex_to_rgb(c2)
                return rgb_to_hex(r1 + (r2 - r1) * t, g1 + (g2 - g1) * t, b1 + (b2 - b1) * t)

            def get_interpolated_state(alt, keyframes):
                if alt >= keyframes[0]['alt']: return keyframes[0]
                if alt <= keyframes[-1]['alt']: return keyframes[-1]
                for i in range(len(keyframes) - 1):
                    upper = keyframes[i]
                    lower = keyframes[i+1]
                    if lower['alt'] <= alt <= upper['alt']:
                        t = (upper['alt'] - alt) / (upper['alt'] - lower['alt'])
                        state = {}
                        for key in upper.keys():
                            if key == 'alt': continue
                            if isinstance(upper[key], str) and upper[key].startswith('#'):
                                state[key] = lerp_color(lower[key], upper[key], t)
                            else:
                                state[key] = lower[key] + (upper[key] - lower[key]) * t
                        return state
                return keyframes[-1]

            if theme == "red":
                sky_keyframes = [
                    {'alt': 12.0, 'top': '#330000', 'mid': '#660000', 'bot': '#aa0000'},
                    {'alt': 6.0,  'top': '#2b0000', 'mid': '#550000', 'bot': '#990000'},
                    {'alt': 0.0,  'top': '#220000', 'mid': '#440000', 'bot': '#770000'},
                    {'alt': -3.0, 'top': '#1a0000', 'mid': '#330000', 'bot': '#550000'},
                    {'alt': -6.0, 'top': '#110000', 'mid': '#220000', 'bot': '#3b0000'},
                    {'alt': -12.0,'top': '#0a0000', 'mid': '#150000', 'bot': '#250000'},
                    {'alt': -18.0,'top': '#000000', 'mid': '#080000', 'bot': '#150000'}
                ]
                bloom_keyframes = [
                    {'alt': 20.0, 'core': '#ff0000', 'glow': '#aa0000', 'op': 0.8, 'rad_mult': 2.0},
                    {'alt': 10.0, 'core': '#ff0000', 'glow': '#990000', 'op': 0.8, 'rad_mult': 2.0},
                    {'alt': 6.0,  'core': '#ee0000', 'glow': '#880000', 'op': 1.0, 'rad_mult': 2.5},
                    {'alt': 0.0,  'core': '#dd0000', 'glow': '#770000', 'op': 1.0, 'rad_mult': 3.0},
                    {'alt': -3.0, 'core': '#bb0000', 'glow': '#660000', 'op': 0.8, 'rad_mult': 3.0},
                    {'alt': -6.0, 'core': '#990000', 'glow': '#440000', 'op': 0.4, 'rad_mult': 3.0},
                    {'alt': -12.0,'core': '#550000', 'glow': '#220000', 'op': 0.0, 'rad_mult': 3.0}
                ]
            else:
                sky_keyframes = [
                    {'alt': 12.0, 'top': '#2563eb', 'mid': '#60a5fa', 'bot': '#e0f2fe'},
                    {'alt': 6.0,  'top': '#3b82f6', 'mid': '#60a5fa', 'bot': '#fcd34d'},
                    {'alt': 0.0,  'top': '#1e3a8a', 'mid': '#8b5cf6', 'bot': '#f97316'},
                    {'alt': -3.0, 'top': '#111827', 'mid': '#4c1d95', 'bot': '#be185d'},
                    {'alt': -6.0, 'top': '#020617', 'mid': '#0e7490', 'bot': '#06b6d4'},
                    {'alt': -12.0,'top': '#020617', 'mid': '#0f172a', 'bot': '#1e3a8a'},
                    {'alt': -18.0,'top': '#000000', 'mid': '#000000', 'bot': '#020617'}
                ]
                bloom_keyframes = [
                    {'alt': 20.0, 'core': '#fffbeb', 'glow': '#fef08a', 'op': 0.8, 'rad_mult': 2.0},
                    {'alt': 10.0, 'core': '#fef08a', 'glow': '#fcd34d', 'op': 0.8, 'rad_mult': 2.0},
                    {'alt': 6.0,  'core': '#fde047', 'glow': '#ffaa00', 'op': 1.0, 'rad_mult': 2.5},
                    {'alt': 0.0,  'core': '#f97316', 'glow': '#ff4400', 'op': 1.0, 'rad_mult': 3.0},
                    {'alt': -3.0, 'core': '#e11d48', 'glow': '#9d174d', 'op': 0.8, 'rad_mult': 3.0},
                    {'alt': -6.0, 'core': '#be123c', 'glow': '#831843', 'op': 0.4, 'rad_mult': 3.0},
                    {'alt': -12.0,'core': '#7f1d1d', 'glow': '#450a0a', 'op': 0.0, 'rad_mult': 3.0}
                ]

            live_sky = get_interpolated_state(current_sun_alt, sky_keyframes)
            live_bloom = get_interpolated_state(current_sun_alt, bloom_keyframes)

            # --- CANVAS ---
            WIDTH = 200
            HEIGHT = 160
            HORIZON_Y = 110
            CX = 100
            R_BASE = 34.0
            R_OUT = 78.0

            is_sun_polar = glance.get("is_sun_polar", False)
            is_moon_polar = glance.get("is_moon_polar", False)

            if is_sun_polar:
                R = 27.0
                CY_sun_rise = 70.0
                CY_sun_set = 70.0
                CY_dial = 88.0
                sky_clip_height = HEIGHT
            else:
                sin_r = math.sin(math.radians(270 - glance["sun_rise_az"]))
                sin_s = math.sin(math.radians(270 - glance["sun_set_az"]))
                min_sin = min(sin_r, sin_s)
                if min_sin < 0:
                    max_safe_r = (HORIZON_Y - 36.0) / (1.0 - min_sin)
                    R = min(R_BASE, max(20.0, max_safe_r))
                else:
                    R = R_BASE
                CY_sun_rise = HORIZON_Y + R * sin_r
                CY_sun_set = HORIZON_Y + R * sin_s
                CY_dial = min(HORIZON_Y, CY_sun_rise)
                sky_clip_height = HORIZON_Y

            if is_moon_polar:
                CY_moon_rise = 70.0 if is_sun_polar else (HORIZON_Y - R)
                CY_moon_set = CY_moon_rise
            else:
                CY_moon_rise = HORIZON_Y + R * math.sin(math.radians(270 - glance["moon_rise_az"]))
                CY_moon_set = HORIZON_Y + R * math.sin(math.radians(270 - glance["moon_set_az"]))

            svg = []
            svg.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="1000" height="800" preserveAspectRatio="xMidYMid meet" style="width: 100%; height: auto;">')

            svg.append('<defs>')
            svg.append(f'''
                <style>
                    {theme_vars_css}
                    text, tspan {{
                        font-family: sans-serif;
                        paint-order: stroke fill;
                        stroke: {h_c};
                        stroke-width: 0.85px;
                        stroke-linecap: round;
                        stroke-linejoin: round;
                    }}
                    .ts-rad-lbl {{ font-size: 5.0px; font-weight: normal; }}
                    .ts-frac    {{ font-size: 5.0px; font-weight: normal; }}
                    .ts-pos-lbl {{ font-size: 5.0px; font-weight: normal; }}
                    .ts-rad-time{{ font-size: 5.2px; font-weight: bold; }}
                    .ts-moon-rs {{ font-size: 5.2px; font-weight: normal; }}
                    .ts-value   {{ font-size: 6.0px; font-weight: bold; }}
                    .ts-pos-val {{ font-size: 6.0px; font-weight: bold; }}
                    .ts-pos-sym {{ font-size: 6.8px; }}

                    @media (max-width: 450px) {{
                        .ts-rad-lbl {{ font-size: 5.0px; }}
                        .ts-frac    {{ font-size: 5.0px; }}
                        .ts-pos-lbl {{ font-size: 5.0px; }}
                        .ts-rad-time{{ font-size: 5.2px; }}
                        .ts-moon-rs {{ font-size: 5.2px; }}
                        .ts-value   {{ font-size: 6.0px; }}
                        .ts-pos-val {{ font-size: 6.0px; }}
                        .ts-pos-sym {{ font-size: 6.8px; }}
                    }}
                </style>
            ''')

            svg.append('<linearGradient id="skyGrad" x1="0%" y1="0%" x2="0%" y2="100%">')
            svg.append(f'<stop offset="0%" stop-color="{live_sky["top"]}" />')
            svg.append(f'<stop offset="70%" stop-color="{live_sky["mid"]}" />')
            svg.append(f'<stop offset="100%" stop-color="{live_sky["bot"]}" />')
            svg.append('</linearGradient>')

            svg.append('<radialGradient id="sunBloomGrad" cx="50%" cy="50%" r="50%">')
            svg.append(f'<stop offset="0%" stop-color="{live_bloom["glow"]}" stop-opacity="1.0" />')
            svg.append(f'<stop offset="40%" stop-color="{live_bloom["glow"]}" stop-opacity="0.6" />')
            svg.append(f'<stop offset="100%" stop-color="{live_bloom["glow"]}" stop-opacity="0.0" />')
            svg.append('</radialGradient>')

            svg.append('<linearGradient id="marginGrad" x1="0%" y1="100%" x2="0%" y2="0%">')
            if theme == "red":
                svg.append('<stop offset="0%" stop-color="#330000" />')
                svg.append('<stop offset="50%" stop-color="#aa0000" />')
                svg.append('<stop offset="100%" stop-color="#ff0000" />')
            else:
                svg.append('<stop offset="0%" stop-color="#020617" />')
                svg.append('<stop offset="25%" stop-color="#1e3a8a" />')
                svg.append('<stop offset="45%" stop-color="#06b6d4" />')
                svg.append('<stop offset="50%" stop-color="#f97316" />')
                svg.append('<stop offset="60%" stop-color="#fcd34d" />')
                svg.append('<stop offset="100%" stop-color="#3b82f6" />')
            svg.append('</linearGradient>')

            svg.append('<linearGradient id="daylightLineGrad" x1="0%" y1="0%" x2="100%" y2="0%">')
            svg.append(f'<stop offset="0%" stop-color="{live_sky["mid"]}" />')
            svg.append(f'<stop offset="50%" stop-color="{live_sky["top"]}" />')
            svg.append(f'<stop offset="100%" stop-color="{live_sky["mid"]}" />')
            svg.append('</linearGradient>')

            # userSpaceOnUse ensures filter regions are not squeezed by shallow winter dome arches
            svg.append(f'<filter id="glowBlurGlance" filterUnits="userSpaceOnUse" x="0" y="0" width="{WIDTH}" height="{HEIGHT}"><feGaussianBlur stdDeviation="0.6" /></filter>')
            svg.append(f'<filter id="domeGlow" filterUnits="userSpaceOnUse" x="0" y="0" width="{WIDTH}" height="{HEIGHT}"><feGaussianBlur stdDeviation="3.0" /></filter>')
            svg.append(f'<clipPath id="skyClip"><rect x="0" y="0" width="{WIDTH}" height="{sky_clip_height}" /></clipPath>')
            svg.append(f'<clipPath id="twilightClip"><rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" /></clipPath>')
            svg.append('</defs>')

            # --- UNPACK CACHED DAILY / PASS GEOMETRY FROM COORDINATOR ---
            crossings = glance["crossings"]
            day_len_sec = glance["day_len_sec"]

            if current_sun_alt > 0:
                top_bar_lbl = "Daylight"
                bar_val_sec = day_len_sec
            else:
                top_bar_lbl = "Nighttime"
                bar_val_sec = max(0.0, 86400.0 - day_len_sec)

            top_bar_val = f"{int(bar_val_sec // 3600)} h {int((bar_val_sec % 3600) // 60)} min"
            rise_str = format_time(glance["s_rise_dt"])
            set_str = format_time(glance["s_set_dt"])
            moon_rise_str = format_time(glance["m_rise_dt"])
            moon_set_str = format_time(glance["m_set_dt"])
            sun_transit_str = format_time(glance["sun_transit_dt"])
            moon_transit_str = format_time(glance["moon_transit_dt"])

            def get_dial_pos_alt(alt, is_am):
                rad = math.radians(alt)
                xs = (CX - R_OUT * math.cos(rad)) if is_am else (CX + R_OUT * math.cos(rad))
                return xs, CY_dial - R_OUT * math.sin(rad)

            sun_pts = []
            for i, az_deg in enumerate(glance["sun_arc_az"]):
                alpha_s = math.radians(270 - az_deg)
                xs = CX + R * math.cos(alpha_s)
                CY_dyn = CY_sun_rise + (i / 50.0) * (CY_sun_set - CY_sun_rise)
                sun_pts.append(f"{xs:.2f},{CY_dyn - R * math.sin(alpha_s):.2f}")

            moon_pts = []
            for i, az_deg in enumerate(glance["moon_arc_az"]):
                alpha_m = math.radians(270 - az_deg)
                xm = CX + R * math.cos(alpha_m)
                CY_dyn = CY_moon_rise + (i / 50.0) * (CY_moon_set - CY_moon_rise)
                moon_pts.append(f"{xm:.2f},{CY_dyn - R * math.sin(alpha_m):.2f}")

            m_margin_pts = [f"{get_dial_pos_alt(a, True)[0]:.1f},{get_dial_pos_alt(a, True)[1]:.1f}" for a in range(-18, 19)]
            e_margin_pts = [f"{get_dial_pos_alt(a, False)[0]:.1f},{get_dial_pos_alt(a, False)[1]:.1f}" for a in range(-18, 19)]

            if is_sun_polar:
                arc_width = 2.0 * R
            else:
                arc_width = abs(float(sun_pts[-1].split(",")[0]) - float(sun_pts[0].split(",")[0])) if len(sun_pts) > 1 else 40.0

            dyn_r = (arc_width * (3.0 / 12.0)) / 2.0
            dyn_r = max(3.5, min(dyn_r, 10.5))

            r_sun_core = dyn_r
            r_moon_core = dyn_r * 0.90
            r_moon_glow = dyn_r * 1.5
            r_sun_bloom = dyn_r * live_bloom['rad_mult']

            # Monochromatic Sun symbol (\u2600\ufe0e)
            am_items_def = [
                (+6, '6:00', None),
                (+1, None, '☀\ufe0e Golden'),
                (-4, '-4:00', None),
                (-5, None, '⧖ Blue'),
                (-6, '-6:00', None),
                (-9, None, '⚓︎ Twilight'),
                (-12, '-12:00', None),
                (-15, None, '✧ Twilight'),
                (-18, '-18:00', None)
            ]

            pm_items_def = [
                (+6, '6:00', None),
                (+1, None, 'Golden ☀\ufe0e'),
                (-4, '-4:00', None),
                (-5, None, 'Blue ⧖'),
                (-6, '-6:00', None),
                (-9, None, 'Twilight ⚓︎'),
                (-12, '-12:00', None),
                (-15, None, 'Twilight ✧'),
                (-18, '-18:00', None)
            ]

            am_time_items, am_lbl_items = [], []
            pm_time_items, pm_lbl_items = [], []

            for alt, h_str, lbl in am_items_def:
                x, y = get_dial_pos_alt(alt, True)
                if h_str:
                    t_event, _ = crossings.get(h_str, (None, None))
                    if t_event: am_time_items.append({'y': y, 'x_arc': x, 'time': format_time(t_event)})
                if lbl: am_lbl_items.append({'y': y, 'x_arc': x, 'lbl': lbl})

            for alt, h_str, lbl in pm_items_def:
                x, y = get_dial_pos_alt(alt, False)
                if h_str:
                    _, t_event = crossings.get(h_str, (None, None))
                    if t_event: pm_time_items.append({'y': y, 'x_arc': x, 'time': format_time(t_event)})
                if lbl: pm_lbl_items.append({'y': y, 'x_arc': x, 'lbl': lbl})

            def resolve_collisions(items, min_gap):
                sorted_items = sorted(items, key=lambda i: i['y'])
                for i in range(1, len(sorted_items)):
                    prev_y = sorted_items[i-1]['y']
                    curr_y = sorted_items[i]['y']
                    if curr_y - prev_y < min_gap: sorted_items[i]['y'] = prev_y + min_gap
                return sorted_items

            am_time_items = resolve_collisions(am_time_items, 5.4)
            am_lbl_items = resolve_collisions(am_lbl_items, 5.2)
            pm_time_items = resolve_collisions(pm_time_items, 5.4)
            pm_lbl_items = resolve_collisions(pm_lbl_items, 5.2)

            svg.append('<g clip-path="url(#twilightClip)">')
            if len(m_margin_pts) > 1: svg.append(f'<path d="M ' + ' L '.join(m_margin_pts) + f'" fill="none" stroke="url(#marginGrad)" stroke-width="1.6" stroke-linecap="round" />')
            if len(e_margin_pts) > 1: svg.append(f'<path d="M ' + ' L '.join(e_margin_pts) + f'" fill="none" stroke="url(#marginGrad)" stroke-width="1.6" stroke-linecap="round" />')

            for item in am_time_items:
                svg.append(f'<text x="{item["x_arc"] - 1.5}" y="{item["y"]}" dy="0.3em" text-anchor="end" fill="{c_pri}" class="ts-rad-time">{item["time"]}</text>')
            for item in am_lbl_items:
                svg.append(f'<text x="{item["x_arc"] + 4.0}" y="{item["y"]}" dy="0.3em" text-anchor="start" fill="{c_sec}" class="ts-rad-lbl">{item["lbl"]}</text>')

            for item in pm_time_items:
                svg.append(f'<text x="{item["x_arc"] + 1.5}" y="{item["y"]}" dy="0.3em" text-anchor="start" fill="{c_pri}" class="ts-rad-time">{item["time"]}</text>')
            for item in pm_lbl_items:
                svg.append(f'<text x="{item["x_arc"] - 4.0}" y="{item["y"]}" dy="0.3em" text-anchor="end" fill="{c_sec}" class="ts-rad-lbl">{item["lbl"]}</text>')
            svg.append('</g>')

            # --- STRICTLY BOUNDED PHYSICAL SKY DOME AURA ---
            svg.append('<g clip-path="url(#skyClip)">')
            dome_aura_width = dyn_r * 2.6
            if is_sun_polar:
                svg.append(f'<circle cx="{CX}" cy="{CY_sun_rise}" r="{R}" fill="none" stroke="url(#skyGrad)" stroke-width="{dome_aura_width}" filter="url(#domeGlow)" opacity="0.6" />')
                svg.append(f'<circle cx="{CX}" cy="{CY_sun_rise}" r="{R}" fill="none" stroke="url(#skyGrad)" stroke-width="{r_sun_core * 2}" opacity="1.0" />')
                svg.append(f'<circle cx="{CX}" cy="{CY_sun_rise}" r="{R}" fill="url(#skyGrad)" />')
            elif len(sun_pts) > 1:
                first_x = sun_pts[0].split(",")[0]
                last_x = sun_pts[-1].split(",")[0]
                fill_path = f"M {first_x},{HORIZON_Y} L " + " L ".join(sun_pts) + f" L {last_x},{HORIZON_Y} Z"
                arc_only_path = f"M {first_x},{HORIZON_Y} L " + " L ".join(sun_pts) + f" L {last_x},{HORIZON_Y}"

                # Round linecaps and joins eliminate diagonal butt-cap chops at the horizon corners
                svg.append(f'<path d="{arc_only_path}" fill="none" stroke="url(#skyGrad)" stroke-width="{dome_aura_width}" stroke-linecap="round" stroke-linejoin="round" filter="url(#domeGlow)" opacity="0.6" />')
                svg.append(f'<path d="{arc_only_path}" fill="none" stroke="url(#skyGrad)" stroke-width="{r_sun_core * 2}" stroke-linecap="round" stroke-linejoin="round" opacity="1.0" />')
                svg.append(f'<path d="{fill_path}" fill="url(#skyGrad)" />')

            if len(moon_pts) > 1:
                svg.append(f'<path d="M ' + ' L '.join(moon_pts) + f'" fill="none" stroke="{c_sec}" stroke-width="0.4" stroke-dasharray="1.5,1.5" opacity="0.6" />')

            def get_body_opacity(alt):
                if alt >= 0.0: return 1.0
                elif alt <= -7.0: return 0.0
                else: return (alt + 7.0) / 7.0

            def get_moon_glow_opacity(sun_alt):
                if sun_alt >= 0.0: return 0.0
                elif sun_alt <= -6.0: return 0.4
                else: return 0.4 * (-sun_alt / 6.0)

            if current_sun_alt <= 0.0: moon_lit_op = 1.0
            elif current_sun_alt >= 6.0: moon_lit_op = 0.8
            else: moon_lit_op = 1.0 - (0.2 * (current_sun_alt / 6.0))

            sun_body_op = f"{get_body_opacity(current_sun_alt):.2f}"
            moon_body_op = f"{get_body_opacity(current_moon_alt):.2f}"
            moon_glow_live = get_moon_glow_opacity(current_sun_alt)

            sun_tel_op = "0.15" if current_sun_alt < -7.0 else "1.0"
            moon_tel_op = "0.15" if current_moon_alt < -7.0 else "1.0"

            frac_sun = glance["frac_sun"]
            CY_sun_live = CY_sun_rise + frac_sun * (CY_sun_set - CY_sun_rise)
            alpha_c_sun = math.radians(270 - current_sun_az)
            cx_sun = CX + R * math.cos(alpha_c_sun)
            cy_sun = CY_sun_live - R * math.sin(alpha_c_sun)

            frac_moon = glance["frac_moon"]
            CY_moon_live = CY_moon_rise + frac_moon * (CY_moon_set - CY_moon_rise)
            alpha_c_moon = math.radians(270 - current_moon_az)
            cx_moon = CX + R * math.cos(alpha_c_moon)
            cy_moon = CY_moon_live - R * math.sin(alpha_c_moon)
            illum = data["moon_phase"]

            if current_sun_alt >= 12.0: base_dark_op = 0.0
            elif current_sun_alt <= -12.0: base_dark_op = 0.8
            else: base_dark_op = 0.8 * ((12.0 - current_sun_alt) / 24.0)
            final_dark_side_op = base_dark_op * (1.0 - illum)

            # True Naked-Eye Moon Limb Orientation (Jean Meeus Bright Limb - Parallactic Angle)
            rot_deg = data["moon_glance_rot_deg"]

            svg.append(f'<g opacity="{moon_body_op}">')
            svg.append(f'<circle cx="{cx_moon}" cy="{cy_moon}" r="{r_moon_glow}" fill="{m_gl}" filter="url(#glowBlurGlance)" opacity="{moon_glow_live:.2f}" />')
            svg.append(f'<circle cx="{cx_moon}" cy="{cy_moon}" r="{r_moon_core}" fill="#000000" opacity="{final_dark_side_op:.2f}" />')

            mx = r_moon_core * (1.0 - 2.0 * illum)
            sweep_inner = "0" if illum <= 0.5 else "1"
            m_path = f"M {cx_moon},{cy_moon-r_moon_core} A {r_moon_core},{r_moon_core} 0 0,1 {cx_moon},{cy_moon+r_moon_core} A {abs(mx)},{r_moon_core} 0 0,{sweep_inner} {cx_moon},{cy_moon-r_moon_core}"

            svg.append(f'<g transform="rotate({rot_deg:.2f} {cx_moon} {cy_moon})" opacity="{moon_lit_op:.2f}">')
            svg.append(f'<path d="{m_path}" fill="{m_fg}" />')
            svg.append('</g>')
            svg.append('</g>')

            if live_bloom['op'] > 0:
                svg.append(f'<circle cx="{cx_sun}" cy="{cy_sun}" r="{r_sun_bloom}" fill="url(#sunBloomGrad)" opacity="{live_bloom["op"]}" />')

            svg.append(f'<g opacity="{sun_body_op}">')
            svg.append(f'<circle cx="{cx_sun}" cy="{cy_sun}" r="{r_sun_core}" fill="{live_bloom["core"]}" />')
            svg.append('</g>')

            svg.append('</g>') # End Sky Clip

            # --- DATA DECKS & SEPARATORS ---
            SEP_Y = 128.0
            VAL_DN_Y = HORIZON_Y + 14.0
            LBL_DN_Y = HORIZON_Y + 25.0

            svg.append(f'<text x="{CX}" y="{VAL_DN_Y}" class="ts-frac" fill="{c_pri}" text-anchor="middle">☼ {sun_transit_str} ▲</text>')
            svg.append(f'<text x="{CX}" y="{LBL_DN_Y}" class="ts-frac" fill="{c_pri}" text-anchor="middle">☾ {moon_transit_str} ▲</text>')

            rise_anchor = CX - 18.0
            set_anchor = CX + 18.0

            svg.append(f'<text x="{rise_anchor}" y="{VAL_DN_Y}" class="ts-value" fill="{c_pri}" text-anchor="end">{rise_str}</text>')
            svg.append(f'<text x="{rise_anchor}" y="{LBL_DN_Y}" class="ts-moon-rs" fill="{c_sec}" text-anchor="end">{moon_rise_str}</text>')

            svg.append(f'<text x="{set_anchor}" y="{VAL_DN_Y}" class="ts-value" fill="{c_pri}" text-anchor="start">{set_str}</text>')
            svg.append(f'<text x="{set_anchor}" y="{LBL_DN_Y}" class="ts-moon-rs" fill="{c_sec}" text-anchor="start">{moon_set_str}</text>')

            # Segmented division line with embedded Rise / Transit / Set labels (1pt smaller than 5.0px transits)
            rise_lbl_cx = CX - 28.0
            set_lbl_cx = CX + 28.0

            for x1, x2 in [
                (CX - 38.0, rise_lbl_cx - 5.5),
                (rise_lbl_cx + 5.5, CX - 7.5),
                (CX + 7.5, set_lbl_cx - 4.5),
                (set_lbl_cx + 4.5, CX + 38.0),
            ]:
                svg.append(f'<line x1="{x1}" y1="{SEP_Y}" x2="{x2}" y2="{SEP_Y}" stroke="{c_sec}" stroke-width="0.3" opacity="0.4" />')

            for lbl_x, lbl_txt in [(rise_lbl_cx, "Rise"), (CX, "Transit"), (set_lbl_cx, "Set")]:
                svg.append(f'<text x="{lbl_x}" y="{SEP_Y}" dy="0.35em" font-size="4.0" fill="{c_sec}" text-anchor="middle">{lbl_txt}</text>')

            # --- TOP BAR ---
            div_width = min(arc_width, 60)
            div_x1 = CX - (div_width / 2.0)

            svg.append(f'<rect x="{div_x1}" y="19.4" width="{div_width}" height="1.6" fill="url(#daylightLineGrad)" opacity="0.9" rx="0.8" />')
            svg.append(f'<text x="{CX}" y="17.0" class="ts-pos-val" fill="{c_pri}" text-anchor="middle">{top_bar_val}</text>')
            svg.append(f'<text x="{CX}" y="26.0" class="ts-pos-lbl" fill="{c_sec}" text-anchor="middle">{top_bar_lbl}</text>')

            L_BASE = 35
            R_BASE_X = 165

            # --- TELEMETRY DECKS WITH HORIZONTAL SEPARATORS ---
            svg.append(f'<g opacity="{sun_tel_op}">')
            svg.append(f'<text x="{L_BASE - 22}" y="22.5" class="ts-pos-sym" fill="{c_pri}" text-anchor="middle">☼</text>')
            svg.append(f'<text x="{L_BASE}" y="17.5" class="ts-pos-val" fill="{c_pri}" text-anchor="middle">{sun_alt_str} <tspan class="ts-pos-lbl" fill="{c_sec}">Alt</tspan></text>')
            svg.append(f'<line x1="{L_BASE - 12}" y1="19.6" x2="{L_BASE + 12}" y2="19.6" stroke="{c_sec}" stroke-width="0.3" opacity="0.6" />')
            svg.append(f'<text x="{L_BASE}" y="25.0" class="ts-pos-val" fill="{c_pri}" text-anchor="middle">{sun_az_str} <tspan class="ts-pos-lbl" fill="{c_sec}">Az</tspan></text>')
            svg.append('</g>')

            svg.append(f'<g opacity="{moon_tel_op}">')
            svg.append(f'<text x="{R_BASE_X + 22}" y="22.5" class="ts-pos-sym" fill="{c_pri}" text-anchor="middle">☾</text>')
            svg.append(f'<text x="{R_BASE_X}" y="17.5" class="ts-pos-val" fill="{c_pri}" text-anchor="middle">{moon_alt_str} <tspan class="ts-pos-lbl" fill="{c_sec}">Alt</tspan></text>')
            svg.append(f'<line x1="{R_BASE_X - 12}" y1="19.6" x2="{R_BASE_X + 12}" y2="19.6" stroke="{c_sec}" stroke-width="0.3" opacity="0.6" />')
            svg.append(f'<text x="{R_BASE_X}" y="25.0" class="ts-pos-val" fill="{c_pri}" text-anchor="middle">{moon_az_str} <tspan class="ts-pos-lbl" fill="{c_sec}">Az</tspan></text>')
            svg.append('</g>')

            svg.append('</svg>')

            svg_bytes = "".join(svg).encode('utf-8')
            self._cached_svg = svg_bytes
            self._last_render = data["timestamp_local"]
            return svg_bytes

        except Exception as e:
            err_str = str(e).replace('"', "'")
            return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 160"><text x="100" y="80" fill="red" font-size="4" text-anchor="middle">Error: {err_str}</text></svg>'.encode('utf-8')
