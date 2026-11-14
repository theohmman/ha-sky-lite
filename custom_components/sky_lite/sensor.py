import logging
import base64
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import (
    DOMAIN,
    CONF_PROJECTION_TERRESTRIAL,
    CONF_SELECTED_BODIES,
    CONF_SHOW_BODY_LABELS,
    DEFAULT_BODIES,
    BODIES_CONF,
    PLANET_SYMBOLS,
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config_entry, async_add_entities):
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    async_add_entities([SkyLiteLegendSensor(coordinator, config_entry)], False)

class SkyLiteLegendSensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        self.entry = entry
        self._attr_unique_id = f"{entry.entry_id}_legend"
        self._attr_name = "Sky Map Legend"
        self._attr_icon = "mdi:table-star"

    @property
    def native_value(self):
        is_terr = self.entry.options.get(CONF_PROJECTION_TERRESTRIAL, False)
        return "Terrestrial Mode" if is_terr else "Astronomical Mode"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        if not data or "bodies" not in data: return {}

        opts = self.entry.options
        is_terr = opts.get(CONF_PROJECTION_TERRESTRIAL, False)
        show_body_labels = opts.get(CONF_SHOW_BODY_LABELS, False)
        selected_bodies = opts.get(CONF_SELECTED_BODIES, DEFAULT_BODIES)

        moon_phase = data.get("moon_phase", 0)
        moon_waning = data.get("moon_waning", False)

        if moon_phase < 0.02: phase_name = "New Moon"
        elif moon_phase > 0.98: phase_name = "Full Moon"
        elif moon_waning: phase_name = "Waning Gibbous" if moon_phase > 0.5 else "Waning Crescent"
        else: phase_name = "Waxing Crescent" if moon_phase < 0.5 else "Waxing Gibbous"

        table_rows = []
        scaled_bodies = []
        moon_icon_html = ""

        for body, b_data in data["bodies"].items():
            is_selected = any(s.lower() == body.lower() for s in selected_bodies)
            color, scale = BODIES_CONF.get(body, ("#ffffff", 2.0))
            r = max(scale * 3.0, 1.5)
            box, center = 24, 12

            # Always generate the Moon footer icon regardless of selection/altitude
            if body.lower() == "moon":
                illum = moon_phase
                mx = r * (1.0 - 2.0 * illum)
                is_waxing = not moon_waning
                sweep_out = "1" if is_waxing else "0"
                sweep_in = "0" if is_waxing else "1"

                if illum <= 0.5:
                    path = f"M {center},{center-r} A {r},{r} 0 0,{sweep_out} {center},{center+r} A {abs(mx)},{r} 0 0,{sweep_in} {center},{center-r}"
                else:
                    path = f"M {center},{center-r} A {r},{r} 0 0,{sweep_out} {center},{center+r} A {abs(mx)},{r} 0 0,{sweep_out} {center},{center-r}"

                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{box}" height="{box}" viewBox="0 0 {box} {box}"><circle cx="{center}" cy="{center}" r="{r:.2f}" fill="#1e293b" stroke="{color}" stroke-width="0.5"/><path d="{path}" fill="{color}"/></svg>'
                b64_svg = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
                moon_icon_html = f'<img src="data:image/svg+xml;base64,{b64_svg}" alt="Moon" style="vertical-align: middle; margin-right: 4px;" />'

            if not is_selected:
                continue

            # 1. EPHEMERIS FILTER: Keep Sun/Moon always. Keep planets only if alt > -7.0
            if body not in ["Sun", "Moon"] and b_data["alt"] <= -7.0:
                continue

            # Ephemeris Text-Only Row
            table_rows.append({
                "body": f"**{body}**",
                "alt": f"{b_data['alt']:.1f}°",
                "az": f"{b_data['az']:.1f}°",
                "rise": b_data.get("rise", "--:--"),
                "set": b_data.get("set", "--:--"),
                "apex": b_data.get("transit", "--:--")
            })

            # 2. SCALED BODIES (MIDDLE TABLE): Append Sun & Planets if altitude > -7.0
            if body.lower() != "moon" and b_data["alt"] > -7.0:
                sym_svg = ""
                if show_body_labels and body in PLANET_SYMBOLS:
                    sym = PLANET_SYMBOLS[body]
                    sym_svg = f'<text x="{center}" y="{center}" fill="#000000" stroke="none" font-family="sans-serif" font-size="{r * 1.65:.2f}" font-weight="bold" text-anchor="middle" dominant-baseline="central">{sym}</text>'

                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{box}" height="{box}" viewBox="0 0 {box} {box}"><circle cx="{center}" cy="{center}" r="{r:.2f}" fill="{color}"/>{sym_svg}</svg>'
                b64_svg = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
                icon_html = f'<img src="data:image/svg+xml;base64,{b64_svg}" alt="{body}" />'

                scaled_bodies.append({
                    "body": body,
                    "icon": icon_html
                })

        next_new = data.get("next_new_moon", "--")
        next_full = data.get("next_full_moon", "--")

        if next_new < next_full:
            moon_event_1 = f"**Next New Moon:** {next_new}"
            moon_event_2 = f"**Next Full Moon:** {next_full}"
        else:
            moon_event_1 = f"**Next Full Moon:** {next_full}"
            moon_event_2 = f"**Next New Moon:** {next_new}"

        attr_data = {
            "moon_icon": moon_icon_html,
            "moon_phase": phase_name,
            "moon_illumination": f"{int(moon_phase * 100)}%",
            "moon_event_1": moon_event_1,
            "moon_event_2": moon_event_2,
            "ephemeris_table": table_rows,
            "scaled_bodies": scaled_bodies
        }

        if is_terr:
            attr_data["constellation_anomaly"] = "*Note: Terrestrial Mode is ON; constellations are mirrored (projected to the ground)."

        return attr_data
