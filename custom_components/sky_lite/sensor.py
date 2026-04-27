import logging
import base64
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN, CONF_PROJECTION_TERRESTRIAL

_LOGGER = logging.getLogger(__name__)

# NASA/JPL Standard Palette
BODIES_CONF = {
    "Sun": ("#ffcc00", 3.0),
    "Moon": ("#d9d9d9", 1.2),
    "Mercury": ("#8c8c94", 0.30),
    "Mars": ("#c1440e", 0.33),
    "Venus": ("#e6e6c8", 0.40),
    "Saturn": ("#ead6b8", 1.91),
    "Jupiter": ("#c88b3a", 2.25)
}

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
        """Returns the primary mode to clear 'Unknown' state."""
        is_terr = self.entry.options.get(CONF_PROJECTION_TERRESTRIAL, False)
        return "Terrestrial Mode" if is_terr else "Astronomical Mode"

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data
        if not data or "bodies" not in data: return {}

        opts = self.entry.options
        is_terr = opts.get(CONF_PROJECTION_TERRESTRIAL, False)
        
        moon_phase = data.get("moon_phase", 0)
        moon_waning = data.get("moon_waning", False)
        
        if moon_phase < 0.02: phase_name = "New Moon"
        elif moon_phase > 0.98: phase_name = "Full Moon"
        elif moon_waning: phase_name = "Waning Gibbous" if moon_phase > 0.5 else "Waning Crescent"
        else: phase_name = "Waxing Crescent" if moon_phase < 0.5 else "Waxing Gibbous"
        
        table_rows = []
        for body, b_data in data["bodies"].items():
            # DYNAMIC FILTER: Keep Sun, Moon, or any body above -7 degrees altitude
            if body not in ["Sun", "Moon"] and b_data["alt"] <= -7.0:
                continue

            color, scale = BODIES_CONF.get(body, ("#ffffff", 2.0))
            
            # Dynamically scale the radius based on the map's scaling factor
            r = max(scale * 3.5, 1.5)
            box, center = 24, 12
            
            # --- DYNAMIC INLINE ICONOGRAPHY ---
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
                
                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{box}" height="{box}" viewBox="0 0 {box} {box}"><circle cx="{center}" cy="{center}" r="{r}" fill="#020617" stroke="{color}" stroke-width="0.5"/><path d="{path}" fill="{color}"/></svg>'
            else:
                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{box}" height="{box}" viewBox="0 0 {box} {box}"><circle cx="{center}" cy="{center}" r="{r}" fill="{color}"/></svg>'

            b64_svg = base64.b64encode(svg.encode('utf-8')).decode('utf-8')
            icon_md = f"![{body}](data:image/svg+xml;base64,{b64_svg})"

            table_rows.append({
                "body": f"{icon_md}&nbsp;&nbsp;**{body}**", 
                "alt": f"{b_data['alt']:.1f}°",
                "az": f"{b_data['az']:.1f}°",
                "rise": b_data.get("rise", "--:--"),
                "set": b_data.get("set", "--:--"),
                "apex": b_data.get("transit", "--:--")
            })

        # --- CHRONOLOGICAL SORTING FOR MOON PHASES ---
        # Because the dates are ISO formatted (YYYY-MM-DD), a simple string comparison accurately sorts them!
        next_new = data.get("next_new_moon", "--")
        next_full = data.get("next_full_moon", "--")
        
        if next_new < next_full:
            moon_event_1 = f"**Next New Moon:** {next_new}"
            moon_event_2 = f"**Next Full Moon:** {next_full}"
        else:
            moon_event_1 = f"**Next Full Moon:** {next_full}"
            moon_event_2 = f"**Next New Moon:** {next_new}"

        attr_data = {
            "moon_phase": phase_name,
            "moon_illumination": f"{int(moon_phase * 100)}%",
            "moon_event_1": moon_event_1,
            "moon_event_2": moon_event_2,
            "ephemeris_table": table_rows
        }
        
        # Only inject the constellation anomaly warning if Terrestrial Mode is ON
        if is_terr:
            attr_data["constellation_anomaly"] = "*Note: Terrestrial Mode is ON; constellations are mirrored (projected to the ground)."
            
        return attr_data