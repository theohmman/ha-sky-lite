import os, json, logging
from .const import DSO_NAMES

_LOGGER = logging.getLogger(__name__)

class ConstellationManager:
    def __init__(self, hass):
        self.hass = hass
        # Rerouted to a static read-only data directory within the component
        self.data_dir = hass.config.path("custom_components/sky_lite/data")
        self.const_file_path = os.path.join(self.data_dir, "constellations.lines.json")
        self.stars_file_path = os.path.join(self.data_dir, "stars.6.json")
        self.dso_file_path = os.path.join(self.data_dir, "dsos.bright.json")
        self.mw_file_path = os.path.join(self.data_dir, "mw.json")
        
        self.constellations = {}
        self.star_data = []
        self.dso_data = []
        self.mw_data = []

    async def async_update_data(self):
        _LOGGER.debug("Sky Lite: Loading local celestial data...")
        # Executes the synchronous file reads safely in a background thread
        await self.hass.async_add_executor_job(self._load_from_disk)

    def _load_from_disk(self):
        # 1. Constellations
        if os.path.exists(self.const_file_path):
            try:
                with open(self.const_file_path, "r", encoding="utf-8") as f: geojson = json.load(f)
                parsed_data = {}
                for feature in geojson.get("features", []):
                    geom = feature.get("geometry", {})
                    if geom.get("type") == "MultiLineString": parsed_data[feature.get("id")] = geom.get("coordinates", [])
                self.constellations = parsed_data
            except Exception as e: _LOGGER.error("Sky Lite Constellation Parse Error: %s", e)

        # 2. Stars
        if os.path.exists(self.stars_file_path):
            try:
                with open(self.stars_file_path, "r", encoding="utf-8") as f: geojson = json.load(f)
                parsed_stars = []
                for feature in geojson.get("features", []):
                    mag = feature.get("properties", {}).get("mag", 99)
                    if mag <= 4.5:
                        geom = feature.get("geometry", {})
                        if geom.get("type") == "Point": parsed_stars.append({"coords": geom.get("coordinates", []), "mag": mag})
                self.star_data = parsed_stars
            except Exception as e: _LOGGER.error("Sky Lite Star Parse Error: %s", e)

        # 3. DSOs (Deep Sky Objects)
        if os.path.exists(self.dso_file_path):
            try:
                with open(self.dso_file_path, "r", encoding="utf-8") as f: geojson = json.load(f)
                parsed_dsos = []
                for feature in geojson.get("features", []):
                    try:
                        raw_mag = feature.get("properties", {}).get("mag")
                        mag = float(raw_mag) if raw_mag is not None else 99.0
                    except (TypeError, ValueError):
                        mag = 99.0
                        
                    if mag <= 6.0:
                        geom = feature.get("geometry", {})
                        props = feature.get("properties", {})
                        desig = props.get("desig", "")
                        native_name = props.get("name", "")
                        
                        dso_name = DSO_NAMES.get(desig) or native_name or desig
                        
                        if geom.get("type") == "Point": 
                            parsed_dsos.append({
                                "coords": geom.get("coordinates", []), 
                                "mag": mag,
                                "name": dso_name
                            })

                self.dso_data = parsed_dsos
            except Exception as e: _LOGGER.error("Sky Lite DSO Parse Error: %s", e)

        # 4. Milky Way Band
        if os.path.exists(self.mw_file_path):
            try:
                with open(self.mw_file_path, "r", encoding="utf-8") as f: geojson = json.load(f)
                parsed_mw = []
                for feature in geojson.get("features", []):
                    geom = feature.get("geometry", {})
                    if geom.get("type") == "MultiPolygon": parsed_mw.append(geom.get("coordinates", []))
                self.mw_data = parsed_mw
            except Exception as e: _LOGGER.error("Sky Lite Milky Way Parse Error: %s", e)