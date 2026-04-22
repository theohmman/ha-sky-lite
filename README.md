# Sky Lite for Home Assistant Beta 2.02

Sky Lite is a lightweight, highly performant custom integration for Home Assistant that generates a real-time, SVG-based celestial map for your dashboard. 

Built entirely with native Home Assistant architecture, Sky Lite calculates and renders the positions of the sun, moon, planets, stars, and IAU constellations dynamically. It avoids heavy iFrames, external cloud APIs, and destructive disk I/O operations by rendering pure mathematical SVGs directly to a virtual image entity.

---

## ✨ Features

* **Real-Time Celestial Rendering:** Accurately tracks and displays the Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, and the 88 recognized IAU constellations.
* **Astronomically Accurate Scaling:** Planetary bodies are rendered using standard astronomical color hex codes and accurate relative visual sizing.
* **Zero Disk I/O:** Renders entirely in memory using the native Home Assistant `image` platform. It never writes temporary image files to your hard drive or SD card, preserving your hardware.
* **Smart Polling Engine:** Respects your server resources by remaining completely dormant until your user-defined refresh interval (e.g., 1, 5, or 15 minutes) has passed.
* **Dynamic Auto-Theming:** Can automatically switch between Light Mode and Dark Mode based on the physical altitude of the sun at your specific coordinates.
* **Astronomer Mode (Night Vision):** A dedicated, pure-red UI theme that preserves your night vision when using the dashboard outdoors.
* **Customizable UI:** Toggle compass markers, invert North/South orientation, adjust refresh rates, and toggle constellation lines/labels directly from the Home Assistant integrations menu—no YAML configuration required.
* **Companion Legend:** Includes logic to generate a beautiful, dynamic Markdown table showing the current Altitude and Azimuth of the celestial bodies.

---

## 🚀 Installation

### Option 1: HACS (Recommended)
1. Open HACS in your Home Assistant instance.
2. Click the three dots in the top right corner and select **Custom repositories**.
3. Add the URL of this repository and select **Integration** as the category.
4. Click **Add**, then search for "Sky Lite" in HACS and click **Download**.
5. Restart Home Assistant.

### Option 2: Manual Installation
1. Download the latest release from this repository.
2. Extract the `sky_lite` folder into your `custom_components` directory in Home Assistant.
3. Restart Home Assistant.

### Setup
1. Navigate to **Settings > Devices & Services > Integrations**.
2. Click **+ Add Integration** and search for "Sky Lite".
3. Enter the Latitude, Longitude, and Elevation for your observatory.
4. Once installed, click the **Configure** button on the integration to adjust your theme, map refresh rate, toggles, and layout preferences.

---

## 🖥️ Dashboard Setup

Sky Lite exposes an image entity (`image.sky_lite_map`) and a sensor entity (`sensor.sky_lite_legend`). You can display these on your Lovelace dashboard using standard cards.

### 1. The Sky Map (Picture Entity Card)
To display the map, use a standard `picture-entity` card. Clicking the map will open a crisp, static, high-resolution viewer.

```yaml
type: picture-entity
entity: image.sky_lite_map
show_name: false
show_state: false
```

### 2. The Celestial Legend (Markdown + Card Mod)
To display the dynamic altitude and azimuth data, you can use a Markdown card. 

* **Requirement:** This setup requires [card-mod](https://github.com/thomasloven/lovelace-card-mod) installed via HACS to style the table seamlessly and generate the pure CSS planetary spheres.

```yaml
type: markdown
content: |
  ## <ha-icon icon="mdi:telescope"></ha-icon> Celestial Legend

  | Body | Altitude | Azimuth |
  | :---: | :---: | :---: |
  {%- set bodies = state_attr('sensor.sky_lite_legend', 'celestial_bodies') %}
  {%- set colors = {
    'Sun': '#FDB813',
    'Moon': '#E6E6E6',
    'Jupiter': '#C88B3A',
    'Saturn': '#E3CB8B',
    'Venus': '#F5D76E',
    'Mars': '#E27B58',
    'Mercury': '#97979F'
  } %}
  {%- if bodies %}
    {%- for body, coords in bodies.items() %}
  | <div style="display: flex; align-items: center; justify-content: flex-start; padding-left: 10px;"><div style="width: 14px; height: 14px; border-radius: 50%; background: radial-gradient(circle at 35% 35%, rgba(255,255,255,0.7) 0%, {{ colors.get(body, '#ffffff') }} 100%); margin-right: 12px; box-shadow: 0 0 5px {{ colors.get(body, '#ffffff') }}40;"></div>**{{ body }}**</div> | {{ coords.alt }}° | {{ coords.az }}° |
    {%- endfor %}
  {%- else %}
  | Waiting for celestial data... | - | - |
  {%- endif %}
card_mod:
  style:
    ha-markdown $: |
      h2 {
        font-size: 1.2em;
        font-weight: bold;
        margin-bottom: 12px;
        margin-top: 0px;
        color: var(--primary-text-color);
      }
      table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.95em;
      }
      th {
        border-bottom: 2px solid var(--divider-color) !important;
        color: var(--secondary-text-color);
        padding: 8px 4px !important;
        text-align: center !important;
      }
      td {
        border-bottom: 1px solid var(--divider-color);
        padding: 10px 4px !important;
        color: var(--primary-text-color);
        text-align: center !important;
      }
      td:nth-child(3) {
        color: var(--secondary-text-color);
      }
    .: |
      ha-card {
        background: var(--card-background-color);
        border-radius: var(--ha-card-border-radius, 12px);
      }
```

---

## 📜 Attributions & Acknowledgments

* **Astronomical Engine:** The core positional mathematics and transit calculations powering Sky Lite are driven by **[PyEphem](https://rhodesmill.org/pyephem/)**, a scientific-grade Python library for high-precision astronomy.
* **Constellation Data:** Standardized abbreviations and mappings conform to the **[International Astronomical Union (IAU)](https://www.iau.org/)** designations.
* **Inspiration:** This project was built to bring the beauty of physical planetariums and mobile star-tracking applications directly into the smart home ecosystem without the overhead of external APIs or iframe workarounds.
```