import os, json, logging, asyncio
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DSO_NAMES

_LOGGER = logging.getLogger(__name__)

# Target the raw GeoJSON from d3-celestial's master branch
D3_CELESTIAL_URL = "https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/constellations.lines.json"
D3_STARS_URL = "https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/stars.6.json"
D3_DSO_URL = "https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/dsos.bright.json"
D3_MW_URL = "https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/mw.json"

class ConstellationManager:
    def __init__(self, hass):
        self.hass = hass
        self.cache_dir = hass.config.path("custom_components/sky_lite/cache")
        self.const_file_path = os.path.join(self.cache_dir, "constellations.lines.json")
        self.stars_file_path = os.path.join(self.cache_dir, "stars.6.json")
        self.dso_file_path = os.path.join(self.cache_dir, "dsos.6.json")
        self.mw_file_path = os.path.join(self.cache_dir, "mw.json")
        
        self.constellations = {}
        self.star_data = []
        self.dso_data = []
        self.mw_data = []

    async def _fetch_and_save(self, session, url, filepath):
        try:
            async with asyncio.timeout(5.0):
                response = await session.get(url)
                response.raise_for_status()
                data = await response.text()
                await self.hass.async_add_executor_job(self._save_to_cache, filepath, data)
        except Exception as e:
            _LOGGER.warning("Sky Lite: Failed to fetch %s. Using cache if available. Error: %s", url, e)

    async def async_update_data(self):
        _LOGGER.debug("Sky Lite: Checking d3-celestial repository for updates...")
        session = async_get_clientsession(self.hass)
        
        # Parallel fetch all 4 datasets simultaneously to prevent boot-hanging
        tasks = [
            self._fetch_and_save(session, D3_CELESTIAL_URL, self.const_file_path),
            self._fetch_and_save(session, D3_STARS_URL, self.stars_file_path),
            self._fetch_and_save(session, D3_DSO_URL, self.dso_file_path),
            self._fetch_and_save(session, D3_MW_URL, self.mw_file_path)
        ]
        await asyncio.gather(*tasks)
        await self.hass.async_add_executor_job(self._load_from_cache)

    def _save_to_cache(self, file_path, data):
        if not os.path.exists(self.cache_dir): os.makedirs(self.cache_dir)
        with open(file_path, "w", encoding="utf-8") as f: f.write(data)

    def _load_from_cache(self):
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
                    # Bulletproof magnitude parsing (handles nulls and strings)
                    try:
                        raw_mag = feature.get("properties", {}).get("mag")
                        mag = float(raw_mag) if raw_mag is not None else 99.0
                    except (TypeError, ValueError):
                        mag = 99.0
                        
                    # Filter out faint objects
                    if mag <= 6.0:
                        geom = feature.get("geometry", {})
                        
                        props = feature.get("properties", {})
                        desig = props.get("desig", "")
                        native_name = props.get("name", "")
                        
                        # PRIORITY LOOKUP: 
                        # 1. Our custom dictionary 
                        # 2. The native name in the JSON
                        # 3. The raw designation (M 33) as a final fallback
                        dso_name = DSO_NAMES.get(desig) or native_name or desig
                        
                        if geom.get("type") == "Point": 
                            parsed_dsos.append({
                                "coords": geom.get("coordinates", []), 
                                "mag": mag,
                                "name": dso_name
                            })

                self.dso_data = parsed_dsos
                _LOGGER.debug("Sky Lite: Successfully loaded %s Deep Sky Objects.", len(self.dso_data))
            except Exception as e: 
                _LOGGER.error("Sky Lite DSO Parse Error: %s", e)

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