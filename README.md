# Sky Lite (Beta 0414.26.v48)

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

Update Interval Defines how often the SVG plot and legend data are refreshed in seconds. The default is 60 seconds.

Latitude, Longitude, & Elevation Primary coordinates used by the ephem observer to calculate the precise altitude and azimuth of celestial bodies for your specific location.

Invert Plot (South-Up Mode) Toggles the polar map between a standard North-Up orientation and a South-Up "Reflector" orientation. This is particularly useful for observers using Newtonian telescopes or those preferring a ground-view perspective.

Theme Mode Users can force Light, Dark, or System themes. The component dynamically shifts gradients and text colors to maintain high contrast.
Auto Theme When enabled, the integration automatically switches between Light and Dark modes based on the Sun's actual altitude relative to the horizon (-0.015 degrees).

Show Constellations Toggles the rendering of line-art paths for major constellations like Ursa Major and Orion based on the observer's current field of view.

Selected Bodies Allows the user to choose which planetary bodies (Sun, Moon, Mars, Venus, etc.) appear in both the plot and the legend table.

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

      
 
Technical Feature Explanations...

These explanations describe the unique astronomical logic implemented in the Beta v48 build.

1. Radiant Path Lunar Rendering
Unlike standard icons that use pre-rendered images, Sky Lite utilizes a Pure Path Rendering engine for the moon. It mathematically constructs a Beige Radiant Path (#f5f5dc) that acts as a physical "sliver" on a solid disk. This eliminates "globe" artifacts and ensures that even at extremely thin phases, the moon appears as a sharp, vibrant sliver rather than a dim ball.

2. Universal Reflector Logic
The moon's orientation is controlled by a multi-stage physical check:
Hemisphere Synchronization: The engine automatically detects the observer's hemisphere. In the Northern Hemisphere, a waning moon is rendered as Left-Lit, while in the Southern Hemisphere, it is rendered as Right-Lit.
Map-Rotation Correction: If a user in the Northern Hemisphere flips their map to South-Up, the internal geometry of the moon icon is counter-mirrored. This ensures the crescent visually remains on the correct physical side of the observer’s screen to match the real sky.

3. Nominal Polar Alignment
The "bulge" of the lunar crescent is dynamically aligned with the Sun's azimuth in coordinate space. This ensures that on the polar plot, the moon always physically "points" toward the sun’s location, providing a technically accurate cartographic representation regardless of map inversion.

4. Adaptive Legend
The Celestial Legend is designed as a high-density technical HUD. It automatically adapts its icons to show the nominal ground-view for the observer's hemisphere. The typography is locked to a micro-technical scale for dashboard efficiency
     
