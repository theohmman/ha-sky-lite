# Sky Lite for Home Assistant (v2611.1)

Sky Lite is a lightweight, highly performant custom integration for Home Assistant that generates real-time, SVG-based celestial visualizations and ephemeris telemetry for your dashboard[cite: 15, 17]. 

Built entirely with native Home Assistant architecture, Sky Lite calculates and renders the positions of the Sun, Moon, planets, stars, Deep Sky Objects (DSOs), the Milky Way, and IAU constellations dynamically[cite: 15, 17]. It avoids heavy iFrames, external cloud APIs, and destructive disk I/O operations by rendering pure mathematical SVGs directly in memory to virtual image entities—purpose-built to run effortlessly on low-power hardware like the Raspberry Pi 4[cite: 15, 17].

---

## ✨ Features

* **Dual In-Memory SVG Visualizers:**
  * **Sky Map (`image.sky_map`):** A full-hemisphere planisphere tracking the Sun, Moon, Mercury, Venus, Mars, Jupiter, Saturn, bright stars, DSOs, the Milky Way band, seasonal solstice/equinox declination paths, and the 88 recognized IAU constellations[cite: 3, 6, 17].
  * **Sky Glance (`image.sky_glance`):** A precision solar and lunar astrolabe instrument displaying a live atmospheric sky dome, 51-point solar and lunar trajectories, dynamic Golden Hour / Blue Hour / Twilight inclinometer brackets, and live Alt/Az/Rise/Transit/Set telemetry decks[cite: 6].
* **Single-Pass RPi4 Optimization & Zero Disk I/O:** Renders entirely in memory using the native Home Assistant `image` platform[cite: 6, 17]. Static GeoJSON star catalogs load only once per session, daily solar trajectories and twilight crossings are cached once per calendar day, and all entities share a single centralized ephemeris pass—preserving both your CPU and SD card.
* **True Naked-Eye Lunar Mechanics:** Implements Jean Meeus's *Astronomical Algorithms* (Bright Limb Position Angle & Parallactic Angle) in **Sky Glance** to dynamically tilt the Moon's illuminated crescent to match the exact apparent orientation seen by the human eye as it arcs across the sky, complete with daytime atmospheric wash-out and nighttime Earthshine shadow scaling.
* **Polar & Extreme Latitude Support:** Automatically adapts to high-latitude conditions—including 24-hour Midnight Sun (`Always Up`) and Polar Night (`Never Up`) above the Arctic and Antarctic Circles—by transitioning into an unclipped $360^\circ$ orbital view.
* **Terrestrial vs. Astronomical Projection:** Toggle **Sky Map** between looking *up* at the sky (Astronomical Planetarium View) or looking *down* at the sky projected onto the ground (Terrestrial Map View).
* **Browser-Aware & Night-Vision Themes:** Choose **System Default** (automatically adapts to your OS/browser Light or Dark mode via native SVG media queries), standalone **Light Mode**, standalone **Dark Mode**, or a dedicated monochrome **Red (Preserve Night Vision)** mode across all views[cite: 12]. All typography is wrapped in high-contrast vector halos (`paint-order: stroke fill`) for guaranteed legibility on any dashboard background.
* **Rich Companion Legend (`sensor.sky_map_legend`):** Generates a Markdown ephemeris table utilizing custom, base64-encoded SVG iconography tracking Altitude, Azimuth, Rise, Set, and Apex (Transit) times in unambiguous 24-hour format (`-`/`+` day prefixes)[cite: 4, 8, 17].
* **Auto-Decluttering:** Celestial bodies and telemetry automatically fade into ghosted indicators or filter out once they dip more than $7^\circ$ below the horizon, keeping your dashboard clean and relevant[cite: 6, 8, 17].

---

## 🚀 Installation

### Option 1: HACS (Recommended)
1. Open HACS in your Home Assistant instance[cite: 17].
2. Click the three dots in the top right corner and select **Custom repositories**[cite: 17].
3. Add `https://github.com/theohmman/ha-sky-lite` and select **Integration** as the category[cite: 15, 17].
4. Click **Add**, then search for **Sky Lite** in HACS and click **Download**[cite: 17].
5. Restart Home Assistant[cite: 17].

### Option 2: Manual Installation
1. Download the latest release (`v2611.1`) from this repository[cite: 17].
2. Extract the `sky_lite` folder into your `custom_components` directory in Home Assistant (`config/custom_components/sky_lite`)[cite: 17].
3. Restart Home Assistant[cite: 17].

### Setup
1. Navigate to **Settings > Devices & Services > Integrations**[cite: 17].
2. Click **+ Add Integration** and search for **Sky Lite**[cite: 17].
3. Enter the Latitude, Longitude, and Elevation for your observatory[cite: 17].
4. Once installed, click the **Configure** button on the integration to adjust your theme mode (`System Default`, `Light`, `Dark`, `Red`), refresh interval (`1` to `60` minutes), Sky Glance time format (`12h` or `24h`), projection mode, and celestial layer toggles[cite: 2, 12, 17].

---

## 🖥️ Dashboard Setup

Sky Lite exposes two image entities (`image.sky_map` and `image.sky_glance`) and one companion sensor entity (`sensor.sky_map_legend`)[cite: 6, 8, 17]. You can display these individually or combine them seamlessly on your dashboard using a standard `vertical-stack` card[cite: 17].

### 1. Sky Glance Card
Add a **Picture Entity** card (or **Picture** card) pointing to `image.sky_glance`:

```yaml
type: picture-entity
entity: image.sky_glance
show_name: false
show_state: false
```

### 2. Sky Map & Ephemeris Legend Stack
To display the **Sky Map** above your dynamic ephemeris table, add a new **Manual Card** to your dashboard and paste the following YAML[cite: 17]:

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

*(Note: If you use custom dashboard plugins like `vertical-stack-in-card` or `stack-in-card`, you can replace `type: vertical-stack` with `type: custom:vertical-stack-in-card` to completely erase the borders between the map, glance card, and table.)*[cite: 17]

---

## 🧠 Design Philosophy & UX

Sky Lite was engineered to bridge the gap between complex 3D astronomical mathematics and 2D dashboard constraints[cite: 17]. To prevent spatial disorientation, the UI deliberately utilizes physical associations and subconscious cues to anchor the user's experience[cite: 17].

### The Horizon Anchor (Sky Map)
Standard, uniform grid lines can be difficult to parse at a glance[cite: 17]. Sky Lite color-codes its azimuth directional lines relative to the equatorial plane[cite: 17]:
* **Green Lines:** Vectors pointing to or below the equatorial plane, representing the Earth and the southern horizon[cite: 6, 17].
* **Blue Lines:** Vectors pointing into the northern hemisphere, representing the open sky[cite: 6, 17].
This distinct separation provides a subconscious visual anchor, allowing users to immediately orient "up" and "down" without needing to read numerical degree labels[cite: 17].

### Physicality of Projection (Sky Map)
Switching between a map view and a planetarium view requires the user to flip their spatial mental model[cite: 17]. Sky Lite assists this transition using a dynamic Observer icon (`ᐰ` — a nod to the *Stargate* franchise's symbol for Earth) whose position mimics the user's physical posture, with the halo as the head and the bottom of the inverted "V" as the feet[cite: 17]:
* **Terrestrial Mode (Map View):** The observer is positioned above the horizon facing the direction at the top, simulating the user standing on the ground and looking *down* at the screen as a physical map[cite: 17]. Celestial bodies are plotted as if they fell straight down from space onto the surface of the Earth[cite: 17].
* **Astronomical Mode (Planetarium View):** The observer shifts below the horizon line, simulating the user lying on the ground—feet facing the bottom, head pointing to the top—holding the screen up to the sky[cite: 17]. The rendering flips so that the visual points align with where the physical bodies exist in the night sky above them[cite: 17].

### Seasonal Color Mapping (Sky Map)
Tracking the shifting path of the Sun requires understanding its changing declination across the seasons[cite: 17]. Instead of using arbitrary colors or requiring the user to read raw numerical degrees, the solar paths are rendered using a temperature-association gradient[cite: 17]:
* **Winter Solstice (-23.44°):** Icy Blue[cite: 17]
* **Equinoxes (0.0°):** Spring Green[cite: 17]
* **Summer Solstice (+23.44°):** Warm Orange[cite: 17]
This translates complex seasonal orbital tracking into an intuitive, at-a-glance visual cue[cite: 17].

### Atmospheric & Lunar Realism (Sky Glance)
Rather than plotting a static sine wave, **Sky Glance** models the physical sky dome as a dynamic horizon-clipped projection:
* **True Azimuth Arcs:** The dome expands in summer and contracts in winter based on the exact rising and setting azimuths of the Sun and Moon at your coordinates, automatically transitioning into a full $360^\circ$ circle during polar Midnight Sun or Polar Night.
* **Naked-Eye Field Rotation:** While **Sky Map** displays an upright waxing/waning terminator for quick phase identification, **Sky Glance** computes the Moon's Parallactic Angle and Bright Limb Zenith Angle so the crescent rocks and tilts across the sky dome exactly as you see it when looking up from your backyard.

---

## 📜 Attributions & Acknowledgments

* **Astronomical Engine:** The core positional mathematics, lunar phasing, and transit calculations powering Sky Lite are driven by [PyEphem](https://rhodesmill.org/pyephem/) by Brandon Rhodes, a scientific-grade Python library for high-precision astronomy[cite: 15, 17].
* **Lunar Limb & Parallactic Algorithms:** Apparent naked-eye lunar crescent orientation equations in Sky Glance are derived from Jean Meeus's *Astronomical Algorithms* (2nd Edition, Chapters 14 & 48).
* **Constellation Data:** Standardized abbreviations and mappings conform to the [International Astronomical Union (IAU)](https://www.iau.org/) designations[cite: 15, 17].
* **Architectural Inspiration:** A massive thank you to the [ha_skyfield](https://github.com/partofthething/ha_skyfield) project by `partofthething`[cite: 15, 17]. This custom component served as foundational inspiration for integrating complex astronomical tracking natively within the Home Assistant ecosystem[cite: 15, 17].
* **Visual Inspiration & GeoJSON Data:** Conceptual inspiration for the map's aesthetic, SVG projection strategies, and the background GeoJSON data mapping the stars, DSOs, and Milky Way were drawn directly from the [d3-celestial](https://github.com/ofrohn/d3-celestial) JavaScript library by Olaf Frohn (`ofrohn`)[cite: 5, 15, 17].
* **Hardware Philosophy:** Built to eliminate heavy dependency overheads on ARM processors, ensuring fluid, zero-disk-I/O celestial rendering on constrained hardware like the Raspberry Pi 4[cite: 15, 17].

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details. Bundled celestial GeoJSON datasets inside `custom_components/sky_lite/data/` are derived from [d3-celestial](https://github.com/ofrohn/d3-celestial) by Olaf Frohn under the **BSD 3-Clause License**.
