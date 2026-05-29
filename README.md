# Sky Lite for Home Assistant (v2.0.1)

Sky Lite is a lightweight, highly performant custom integration for Home Assistant that generates a real-time, SVG-based celestial map for your dashboard. 

Built entirely with native Home Assistant architecture, Sky Lite calculates and renders the positions of the sun, moon, planets, stars, Deep Sky Objects (DSOs), the Milky Way, and IAU constellations dynamically. It avoids heavy iFrames, external cloud APIs, and destructive disk I/O operations by rendering pure mathematical SVGs directly to a virtual image entity.

---

## ✨ Features

* **Near Real-Time Celestial Rendering:** Accurately tracks and displays the Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, and the 88 recognized IAU constellations.
* **Deep Sky & Milky Way Support:** Dynamically downloads, caches, and renders deep sky geometries (like the Milky Way band and major galaxies/nebulae) without bloating your local disk.
* **Zero Disk I/O:** Renders entirely in memory using the native Home Assistant `image` platform. It never writes temporary image files to your hard drive or SD card, preserving your hardware.
* **Smart Polling Engine:** Respects your server resources by perfectly syncing the map and sensor calculations to your user-defined refresh interval (e.g., 1, 5, or 15 minutes), independently of HA's background API sweeps.
* **Terrestrial vs. Astronomical Projection:** Toggle between looking "up" at the sky (Astronomical) or looking "down" at the sky as it relates to a map (Terrestrial). 
* **Dynamic Auto-Theming:** Can automatically switch between Light Mode and Dark Mode based on the physical altitude of the sun at your specific coordinates. Includes a dedicated pure-red "Astronomer Mode" to preserve night vision.
* **Rich Companion Legend:** Generates a stunning Markdown table directly in Home Assistant utilizing custom, base64-encoded SVG iconography. It tracks Altitude, Azimuth, Rise, Set, and Apex (Transit) times.
* **Auto-Decluttering:** The legend automatically removes planetary bodies that dip more than 7 degrees below the horizon (excluding the Sun and Moon), keeping your dashboard clean and relevant.

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

Sky Lite exposes an image entity (`image.sky_map`) and a sensor entity (`sensor.sky_map_legend`). You can display these perfectly seamlessly on your Lovelace dashboard using a standard `vertical-stack` or `vertical-stack-in-card` card.

To display the map on top of your dynamic ephemeris table, add a new **Manual Card** to your dashboard and paste the following YAML:

```yaml
type: vertical-stack
cards:
  - type: picture-entity
    entity: image.sky_map
    show_name: false
    show_state: false
  - type: markdown
    content: |
      <div align="center">
      <table style="width:100%; border:none; text-align:center;">
      <tr>
      {% for item in state_attr('sensor.sky_map_legend', 'scaled_bodies') %}
      <td style="border:none;">
      {{ item.icon }}<br><sub>{{ item.body }}</sub>
      </td>
      {% if loop.index % 6 == 0 and not loop.last %}
      </tr><tr>
      {% endif %}
      {% endfor %}
      </tr>
      </table>
      </div>

      ---

      |Rise|Apex|Body|Alt|Az|Set|
      | ---: | ---: | :--- | ---: | ---: | ---: |
      {% for body in state_attr('sensor.sky_map_legend', 'ephemeris_table') -%}
      | {{ body.rise }} | {{ body.apex }} | {{ body.body }} | {{ body.alt }} | {{ body.az }} | {{ body.set }} |
      {% endfor %}

      {{ state_attr('sensor.sky_map_legend', 'moon_icon') }}&nbsp;&nbsp;<br>**Moon Phase:** {{ state_attr('sensor.sky_map_legend', 'moon_phase') }} | **Moonlit:** {{ state_attr('sensor.sky_map_legend', 'moon_illumination') }}

      {{ state_attr('sensor.sky_map_legend', 'moon_event_1') }} <br> {{ state_attr('sensor.sky_map_legend', 'moon_event_2') }}

      {% if state_attr('sensor.sky_map_legend', 'constellation_anomaly') %}
      <br>
      <sub>{{ state_attr('sensor.sky_map_legend', 'constellation_anomaly') }}</sub>
      {% endif %}

      ---

      <div align="right"><sub><i>Updated at {{ states.sensor.sky_map_legend.last_updated | as_local | as_timestamp | timestamp_custom('%H:%M:%S') }}</i></sub></div>

```

*(Note: If you use custom dashboard plugins like stack-in-card, you can replace `type: vertical-stack` with `type: custom:vertical-stack-in-card` to completely erase the borders between the map and the table)*

---

## 🧠 Design Philosophy & UX

Sky Lite was engineered to bridge the gap between complex 3D astronomical mathematics and 2D dashboard constraints. To prevent spatial disorientation, the UI deliberately utilizes physical associations and subconscious cues to anchor the user's experience.

### The Horizon Anchor

Standard, uniform grid lines can be difficult to parse at a glance. Sky Lite color-codes its azimuth directional lines relative to the equatorial plane:

* **Green Lines:** Vectors pointing to or below the equatorial plane, representing the Earth and the horizon.
* **Blue Lines:** Vectors pointing into the upper hemisphere, representing the open sky.
This distinct separation provides a subconscious visual anchor, allowing users to immediately orient "up" and "down" without needing to read numerical degree labels.

### Physicality of Projection

Switching between a map view and a planetarium view requires the user to flip their spatial mental model. Sky Lite assists this transition using a dynamic Observer icon (`ᐰ` - a nod to the Stargate franchise's symbol for Earth) whose position mimics the user's physical posture; the halo as the head and bottom of the inverted "V" as the feet:

* **Terrestrial Mode (Map View):** The observer is positioned above the horizon facing the direction at the top, simulating the user standing on the ground and looking *down* at the screen as a physical map. Celestial bodies are plotted as if they fell straight down from space onto the surface of the Earth.
* **Astronomical Mode (Planetarium View):** The observer shifts below the horizon line, simulating the user lying on the ground—feet facing the bottom, head pointing to the top—holding the screen up to the sky. The rendering flips so that the visual points align perfectly with where the physical bodies exist in the night sky above them.

### Seasonal Color Mapping

Tracking the shifting path of the sun requires understanding its changing declination across the seasons. Instead of using arbitrary colors or requiring the user to read raw numerical degrees, the solar paths are rendered using a temperature-association gradient:

* **Winter Solstice (-23.44°):** Icy Blue
* **Equinoxes (0.0°):** Spring Green
* **Summer Solstice (+23.44°):** Warm Orange
This translates complex seasonal orbital tracking into an intuitive, at-a-glance visual cue.

---

## 📜 Attributions & Acknowledgments

* **Astronomical Engine:** The core positional mathematics, lunar phasing, and transit calculations powering Sky Lite are driven by [PyEphem](https://rhodesmill.org/pyephem/), a scientific-grade Python library for high-precision astronomy.
* **Constellation Data:** Standardized abbreviations and mappings conform to the [International Astronomical Union (IAU)](https://www.iau.org/) designations.
* **Architectural Inspiration:** A massive thank you to the [ha_skyfield](https://github.com/partofthething/ha_skyfield) project by partofthething. This excellent custom component served as foundational inspiration for integrating complex astronomical tracking natively within the Home Assistant ecosystem.
* **Visual Inspiration & GeoJSON Data:** Conceptual inspiration for the map's aesthetic, SVG projection strategies, and the robust background GeoJSON data mapping the stars, DSOs, and Milky Way were drawn directly from the stunning [d3-celestial](https://github.com/ofrohn/d3-celestial) JavaScript library by ofrohn.
* **Hardware Philosophy:** General inspiration for this project was born from a desire to work around dependency overheads of ARM processors, ensuring fluid celestial rendering even on constrained environments like the Raspberry Pi 4.
