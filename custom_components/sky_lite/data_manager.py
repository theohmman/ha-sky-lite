import os
import json
import logging
import asyncio
import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)

# Target the raw GeoJSON from d3-celestial's master branch
D3_CELESTIAL_URL = "https://raw.githubusercontent.com/ofrohn/d3-celestial/master/data/constellations.lines.json"

class ConstellationManager:
    def __init__(self, hass):
        self.hass = hass
        self.cache_dir = hass.config.path("custom_components/sky_lite/cache")
        self.file_path = os.path.join(self.cache_dir, "constellations.lines.json")
        self.constellations = {}

    async def async_update_data(self):
        """Attempts to fetch fresh GeoJSON data, falls back to local cache if needed."""
        _LOGGER.debug("Sky Lite: Checking d3-celestial repository for updates...")
        session = async_get_clientsession(self.hass)
        
        try:
            # STRICT 5-SECOND TIMEOUT: Prevents HA from hanging during boot
            async with asyncio.timeout(5.0):
                response = await session.get(D3_CELESTIAL_URL)
                response.raise_for_status()
                data = await response.text()
                
                # Write to local cache in a background thread
                await self.hass.async_add_executor_job(self._write_cache, data)
                _LOGGER.info("Sky Lite: Successfully cached constellation data from d3-celestial.")
                
        except (asyncio.TimeoutError, aiohttp.ClientError) as e:
            _LOGGER.warning("Sky Lite: Network/Timeout error fetching data. Falling back to local cache. (%s)", e)
        except Exception as e:
            _LOGGER.error("Sky Lite: Unexpected error fetching constellation data: %s", e)

        # Always load and parse from the local cache to populate self.constellations
        await self.hass.async_add_executor_job(self._load_from_cache)

    def _write_cache(self, data):
        """Writes the downloaded JSON to the local file."""
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(data)

    def _load_from_cache(self):
        """Reads the local file and parses the d3-celestial GeoJSON format."""
        if not os.path.exists(self.file_path):
            _LOGGER.error("Sky Lite: No local constellation cache found and network is down. Constellations disabled.")
            self.constellations = {}
            return

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                geojson = json.load(f)
                
            parsed_data = {}
            # d3-celestial stores data as a FeatureCollection
            for feature in geojson.get("features", []):
                abbv = feature.get("id") # e.g., "UMa", "Ori", "Tau"
                geometry = feature.get("geometry", {})
                
                if geometry.get("type") == "MultiLineString":
                    # coordinates is a list of line segments: [ [ [ra, dec], [ra, dec] ], [ [ra, dec], [ra, dec] ] ]
                    # Note: d3-celestial RA is in degrees (0-360), Dec is in degrees (-90 to 90)
                    parsed_data[abbv] = geometry.get("coordinates", [])
                    
            self.constellations = parsed_data
            _LOGGER.debug("Sky Lite: Loaded %s constellations from cache.", len(self.constellations))
            
        except Exception as e:
            _LOGGER.error("Sky Lite: Failed to parse local constellation cache: %s", e)