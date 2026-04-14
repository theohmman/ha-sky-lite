# Sky Lite (Beta 0414.26.0336)

A lightweight, high-performance celestial tracker and polar plot generator for Home Assistant.

## 🌌 The Inspiration
This project was born as a lightweight "fork in spirit" of [ha_skyfield](https://github.com/partofthething/ha_skyfield). While the original project provides incredible scientific accuracy, its heavy dependencies (Matplotlib, NumPy, and Skyfield) often fail to compile or run efficiently on ARM-based hardware like the **Raspberry Pi**. 

**Sky Lite** strips away the heavy rendering engines and replaces them with a "headless" SVG generator, making it the perfect choice for users who want beautiful sky visuals without the CPU overhead.

---

## ✨ Features
* **Pi-Friendly Architecture:** Uses the C-based `ephem` library for near-zero CPU impact.
* **Dynamic SVG Rendering:** Generates a real-time, theme-aware polar plot directly in a sensor attribute.
* **Atmospheric Visuals:** Includes a radial horizon gradient and elevation rings (10° increments).
* **The Ecliptic & Zodiac:** Full 12-sign Zodiac paths and the "Summer Triangle" markers to help track planetary movement.
* **Solar Paths:** Visualizes the Summer Solstice, Winter Solstice, and Today’s specific Sun path.
* **Theme Support:** Supports System, Light, and Dark modes with automatic CSS variable mapping.

---

## 🛠️ Installation

### Manual Installation
1. Download the `sky_lite` folder.
2. Copy it into your Home Assistant `/config/custom_components/` directory.
3. Restart Home Assistant.
4. Go to **Settings > Devices & Services > Add Integration** and search for "Sky Lite".

### HACS (Recommended)
1. Add this repository URL as a **Custom Repository** in HACS.
2. Click **Install**.
3. Restart Home Assistant and add the integration via the Devices menu.

---

## ⚙️ Configuration & Options
Once installed, you can click the **Configure** button on the integration to adjust:
* **Update Interval:** 10s to 3600s (Default: 60s).
* **Theme Mode:** Toggle between System (Auto), Forced Light, or Forced Dark.
* **Show Constellations:** Toggle lines for major anchors like Orion and the Big Dipper.
* **Constellation Labels:** Show/Hide names for star groups.
* **Invert Plot:** Flips the map (South is Up) for Southern Hemisphere observers.

---

## 📊 Dashboard Setup
To display the map, use the **Custom Button Card** (available in HACS) to handle the raw SVG data:

```yaml
type: custom:button-card
entity: sensor.sky_lite_view
show_name: false
show_icon: false
aspect_ratio: 1/1
custom_fields:
  sky_plot: |
    [[[ return entity.attributes.svg_plot ]]]
styles:
  grid:
    - grid-template-areas: "\"sky_plot\""
  card:
    - background-color: transparent
    - border-radius: 50%
    - padding: 0px
    - border: none
  custom_fields:
    sky_plot:
      - width: 100%
      - height: 100%
