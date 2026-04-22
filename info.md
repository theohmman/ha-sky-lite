# Sky Lite for Home Assistant

Sky Lite is a lightweight, zero-disk-I/O celestial map for your Home Assistant dashboard. It calculates and renders the real-time positions of the sun, moon, planets, stars, and 88 IAU constellations natively using PyEphem.

### Why Sky Lite?
Unlike other astronomical integrations, Sky Lite is explicitly designed for lower-power hardware like the Raspberry Pi. 
* **Zero Disk I/O:** Renders SVG maps purely in memory using the modern `Image` platform (no hard drive writes, no MJPEG streaming bugs).
* **Smart Polling:** Completely dormant until your user-defined refresh interval passes.
* **Centralized Math:** Uses a native Home Assistant DataUpdateCoordinator so your Map and Legend share the exact same calculations, cutting CPU usage in half.

### Features
* Customizable auto-theming (including a pure-red "Astronomer Mode" for night vision).
* Accurate relative planetary sizing and scaling.
* UI-driven configuration (no YAML required).
* Companion dynamic Altitude/Azimuth legend sensor.

**To get started with the dashboard setup and Lovelace card configurations, please check the full [README](https://github.com/theohmman/ha-sky-lite) on GitHub.**
