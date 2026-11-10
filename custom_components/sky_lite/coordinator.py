import logging
import math
import ephem
from datetime import datetime, timedelta
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util
from .const import DOMAIN, CONF_UPDATE_INTERVAL, DEFAULT_BODIES

_LOGGER = logging.getLogger(__name__)

# ==========================================
# ASTRONOMICAL ALGORITHMS ATTRIBUTION
# ==========================================
# Core ephemeris powered by PyEphem (Brandon Rhodes): https://rhodesmill.org/pyephem/
# Moon Bright Limb Position Angle (chi) & Parallactic Angle (q) derived from:
# Jean Meeus, "Astronomical Algorithms", 2nd Edition (Ch. 14 & Ch. 48).
# ==========================================

class SkyLiteCoordinator(DataUpdateCoordinator):
    """Centralized brain for Sky Lite math calculations and cycle caching."""

    def __init__(self, hass, entry):
        self.entry = entry
        self.lat = float(entry.data.get("latitude"))
        self.lon = float(entry.data.get("longitude"))
        self.elev = float(entry.data.get("elevation", 0.0))

        # Setup the PyEphem Observer ONCE
        self.obs = ephem.Observer()
        self.obs.lat = str(self.lat)
        self.obs.lon = str(self.lon)
        self.obs.elevation = self.elev

        # Cache containers for static daily/pass geometry (RPi4 CPU optimization)
        self._solar_cache_key = None
        self._solar_cache = {}
        self._lunar_cache_window = None
        self._lunar_cache = {}

        interval = int(entry.options.get(CONF_UPDATE_INTERVAL, "1"))

        super().__init__(
            hass,
            _LOGGER,
            name="Sky Lite Coordinator",
            update_interval=timedelta(minutes=interval),
        )

    async def _async_update_data(self):
        """Run the heavy math safely in a background thread."""
        return await self.hass.async_add_executor_job(self._calculate_sky)

    def _get_polar_24h_window(self, body, now_ephem, fallback_start_utc):
        """
        For polar AlwaysUp / NeverUp conditions, anchor the 24-hour full circle
        from the previous antitransit (lowest point / nadir) to the next antitransit.
        """
        self.obs.horizon = '0:00'
        self.obs.date = now_ephem
        try:
            r = self.obs.previous_antitransit(body)
            self.obs.date = r
            s = self.obs.next_antitransit(body)
            return r, s
        except Exception:
            r = ephem.Date(fallback_start_utc)
            s = ephem.Date(fallback_start_utc + timedelta(hours=24))
            return r, s

    def _get_active_pass(self, body, now_ephem, current_alt_deg, fallback_start_utc):
        """
        Find the active (rise, set, is_valid_pass) for the Moon.
        Keeps the Moon locked onto its setting pass while fading between 0° and -7.0°,
        and switches immediately to the upcoming pass once it drops below -7.0°.
        """
        self.obs.horizon = '0:00'
        self.obs.date = now_ephem
        try:
            if current_alt_deg >= 0.0:
                r = self.obs.previous_rising(body)
                self.obs.date = r
                s = self.obs.next_setting(body)
                return r, s, True
            else:
                prev_s = self.obs.previous_setting(body)
                self.obs.date = now_ephem
                next_r = self.obs.next_rising(body)

                # If between 0° and -7.0° and it just set (within ~4 hours), finish the setting fade
                if current_alt_deg >= -7.0 and (now_ephem - prev_s) <= (4.0 / 24.0):
                    self.obs.date = prev_s
                    prev_r = self.obs.previous_rising(body)
                    return prev_r, prev_s, True
                else:
                    # Below -7.0° (or rising from -7.0° to 0°): lock onto the upcoming pass
                    self.obs.date = next_r
                    next_s = self.obs.next_setting(body)
                    return next_r, next_s, True
        except (ephem.AlwaysUpError, ephem.NeverUpError, Exception):
            r, s = self._get_polar_24h_window(body, now_ephem, fallback_start_utc)
            return r, s, False

    def _compute_solar_daily_cache(self, now_local, now_ephem, current_sun_alt, sun):
        """Compute solar twilight crossings and 51-point trajectory once per local calendar day."""
        start_of_day_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        start_of_day_utc = start_of_day_local.astimezone(dt_util.UTC).replace(tzinfo=None)
        solar_noon_utc = now_local.replace(hour=12, minute=0, second=0, microsecond=0).astimezone(dt_util.UTC).replace(tzinfo=None)

        crossings = {}
        for h_str in ['18:00', '6:00', '0:00', '-4:00', '-6:00', '-12:00', '-18:00']:
            self.obs.horizon = h_str
            self.obs.date = solar_noon_utc
            try:
                m = self.obs.previous_rising(sun)
                self.obs.date = m
                e = self.obs.next_setting(sun)
                crossings[h_str] = (
                    dt_util.as_local(m.datetime().replace(tzinfo=dt_util.UTC)),
                    dt_util.as_local(e.datetime().replace(tzinfo=dt_util.UTC)),
                    m,
                    e,
                )
            except (ephem.AlwaysUpError, ephem.NeverUpError, Exception):
                crossings[h_str] = (None, None, None, None)

        self.obs.horizon = '0:00'
        r_dt, s_dt, s_rise, s_set = crossings['0:00']
        has_valid_rise_set = (s_rise is not None and s_set is not None)
        is_sun_polar = not has_valid_rise_set

        if is_sun_polar:
            s_rise, s_set = self._get_polar_24h_window(sun, now_ephem, start_of_day_utc)
            day_len_sec = 86400.0 if current_sun_alt > 0 else 0.0
        else:
            day_len_sec = (s_dt - r_dt).total_seconds()

        # Transit (Solar Noon)
        self.obs.date = start_of_day_utc
        sun_transit_dt = None
        try:
            t_ephem = self.obs.next_transit(sun)
            sun_transit_dt = dt_util.as_local(t_ephem.datetime().replace(tzinfo=dt_util.UTC))
        except Exception:
            pass

        # Rise & Set Azimuths + 51-point trajectory azimuths
        self.obs.date = s_rise
        sun.compute(self.obs)
        sun_rise_az = math.degrees(sun.az)

        self.obs.date = s_set
        sun.compute(self.obs)
        sun_set_az = math.degrees(sun.az)

        sun_arc_az = []
        total_sec_s = (s_set.datetime() - s_rise.datetime()).total_seconds()
        if total_sec_s > 0:
            for i in range(51):
                eval_time = s_rise.datetime() + timedelta(seconds=(total_sec_s / 50.0) * i)
                self.obs.date = eval_time
                sun.compute(self.obs)
                sun_arc_az.append(math.degrees(sun.az))

        return {
            "crossings": {k: (v[0], v[1]) for k, v in crossings.items()},
            "s_rise_ephem": s_rise,
            "s_set_ephem": s_set,
            "s_rise_dt": r_dt,
            "s_set_dt": s_dt,
            "has_valid_rise_set": has_valid_rise_set,
            "is_sun_polar": is_sun_polar,
            "day_len_sec": day_len_sec,
            "sun_transit_dt": sun_transit_dt,
            "sun_rise_az": sun_rise_az,
            "sun_set_az": sun_set_az,
            "sun_arc_az": sun_arc_az,
            "total_sec_s": total_sec_s,
        }

    def _compute_lunar_pass_cache(self, m_rise, m_set, has_valid_pass, start_of_day_utc, moon):
        """Compute 51-point lunar trajectory once per active lunar pass."""
        self.obs.horizon = '0:00'
        self.obs.date = m_rise
        moon.compute(self.obs)
        moon_rise_az = math.degrees(moon.az)

        self.obs.date = m_set
        moon.compute(self.obs)
        moon_set_az = math.degrees(moon.az)

        moon_arc_az = []
        total_sec_m = (m_set.datetime() - m_rise.datetime()).total_seconds()
        if total_sec_m > 0:
            for i in range(51):
                eval_time = m_rise.datetime() + timedelta(seconds=(total_sec_m / 50.0) * i)
                self.obs.date = eval_time
                moon.compute(self.obs)
                moon_arc_az.append(math.degrees(moon.az))

        m_rise_dt = dt_util.as_local(m_rise.datetime().replace(tzinfo=dt_util.UTC)) if has_valid_pass else None
        m_set_dt = dt_util.as_local(m_set.datetime().replace(tzinfo=dt_util.UTC)) if has_valid_pass else None

        self.obs.date = m_rise if has_valid_pass else start_of_day_utc
        moon_transit_dt = None
        try:
            mt_ephem = self.obs.next_transit(moon)
            moon_transit_dt = dt_util.as_local(mt_ephem.datetime().replace(tzinfo=dt_util.UTC))
        except Exception:
            pass

        return {
            "m_rise_ephem": m_rise,
            "m_set_ephem": m_set,
            "m_rise_dt": m_rise_dt,
            "m_set_dt": m_set_dt,
            "is_moon_polar": not has_valid_pass,
            "moon_transit_dt": moon_transit_dt,
            "moon_rise_az": moon_rise_az,
            "moon_set_az": moon_set_az,
            "moon_arc_az": moon_arc_az,
            "total_sec_m": total_sec_m,
        }

    def _calculate_sky(self):
        """Calculate the position of all bodies and update daily/pass caches if needed."""
        try:
            now_local = dt_util.now()
            now_utc_naive = now_local.astimezone(dt_util.UTC).replace(tzinfo=None)
            now_ephem = ephem.Date(now_utc_naive)

            self.obs.horizon = '0:00'
            self.obs.date = now_ephem

            lst_rad = float(self.obs.sidereal_time())
            lat_rad = float(self.obs.lat)

            data = {
                "timestamp_local": now_local,
                "lst_rad": lst_rad,
                "lat_rad": lat_rad,
            }

            # 1. Live Sun & Moon Compute
            sun_obj = ephem.Sun()
            moon_obj = ephem.Moon()
            sun_obj.compute(self.obs)
            moon_obj.compute(self.obs)

            sun_ra, sun_dec = float(sun_obj.ra), float(sun_obj.dec)
            moon_ra, moon_dec = float(moon_obj.ra), float(moon_obj.dec)
            current_sun_alt = math.degrees(float(sun_obj.alt))
            current_moon_alt = math.degrees(float(moon_obj.alt))

            data["sun_dec_deg"] = math.degrees(sun_dec)
            data["moon_phase"] = moon_obj.phase / 100.0

            # Upright Waxing/Waning check (used by Sky Map & Legend Sensor)
            angle = (moon_ra - sun_ra) % (2 * math.pi)
            data["moon_waning"] = angle >= math.pi

            # Jean Meeus Naked-Eye Moon Orientation (used by Sky Glance)
            d_ra = sun_ra - moon_ra
            num_chi = math.cos(sun_dec) * math.sin(d_ra)
            den_chi = math.sin(sun_dec) * math.cos(moon_dec) - math.cos(sun_dec) * math.sin(moon_dec) * math.cos(d_ra)
            chi_rad = math.atan2(num_chi, den_chi)

            ha_moon = lst_rad - moon_ra
            num_q = math.sin(ha_moon)
            den_q = math.tan(lat_rad) * math.cos(moon_dec) - math.sin(moon_dec) * math.cos(ha_moon)
            q_rad = math.atan2(num_q, den_q)

            zenith_limb_deg = math.degrees(chi_rad - q_rad)
            data["moon_glance_rot_deg"] = zenith_limb_deg - 90.0

            # Moon Age & Upcoming Phases
            prev_new = ephem.previous_new_moon(now_ephem)
            data["moon_age"] = now_ephem - prev_new
            data["next_new_moon"] = ephem.localtime(ephem.next_new_moon(now_ephem)).date().isoformat()
            data["next_full_moon"] = ephem.localtime(ephem.next_full_moon(now_ephem)).date().isoformat()

            # 2. Planetary Positions & Events (24h format with +/- day prefix for Legend Sensor)
            data["bodies"] = {}
            for name in DEFAULT_BODIES:
                self.obs.horizon = '0:00'
                self.obs.date = now_ephem
                body = getattr(ephem, name)()
                body.compute(self.obs)

                def get_event(event_func):
                    try:
                        self.obs.date = now_ephem
                        event_dt = dt_util.as_local(event_func(body).datetime().replace(tzinfo=dt_util.UTC))
                        day_diff = (event_dt.date() - now_local.date()).days
                        time_str = event_dt.strftime("%H:%M")
                        if day_diff < 0:
                            return f"-{time_str}"
                        elif day_diff > 0:
                            return f"+{time_str}"
                        return time_str
                    except ephem.AlwaysUpError:
                        return "Always Up"
                    except ephem.NeverUpError:
                        return "Never Up"
                    except Exception:
                        return "--:--"

                data["bodies"][name] = {
                    "az": math.degrees(float(body.az)),
                    "alt": math.degrees(float(body.alt)),
                    "rise": get_event(self.obs.next_rising),
                    "set": get_event(self.obs.next_setting),
                    "transit": get_event(self.obs.next_transit),
                }

            # 3. Cached Solar Daily Geometry (Recomputes once per local calendar day)
            today_date = now_local.date()
            if self._solar_cache_key != today_date or not self._solar_cache:
                self._solar_cache = self._compute_solar_daily_cache(now_local, now_ephem, current_sun_alt, sun_obj)
                self._solar_cache_key = today_date

            if self._solar_cache.get("is_sun_polar") and now_ephem > self._solar_cache["s_set_ephem"]:
                self._solar_cache = self._compute_solar_daily_cache(now_local, now_ephem, current_sun_alt, sun_obj)

            # 4. Cached Lunar Pass Geometry (Recomputes only when active lunar pass changes)
            start_of_day_utc = now_local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(dt_util.UTC).replace(tzinfo=None)
            m_rise, m_set, has_valid_m_pass = self._get_active_pass(
                moon_obj, now_ephem, current_moon_alt, start_of_day_utc
            )
            lunar_window_key = (round(float(m_rise), 3), round(float(m_set), 3), has_valid_m_pass)
            if self._lunar_cache_window != lunar_window_key or not self._lunar_cache:
                self._lunar_cache = self._compute_lunar_pass_cache(
                    m_rise, m_set, has_valid_m_pass, start_of_day_utc, moon_obj
                )
                self._lunar_cache_window = lunar_window_key

            # 5. Live Fractional Progress Along Active Pass
            s_rise_dt_utc = self._solar_cache["s_rise_ephem"].datetime()
            total_sec_s = self._solar_cache["total_sec_s"]
            if total_sec_s > 0:
                frac_sun = (now_utc_naive - s_rise_dt_utc).total_seconds() / total_sec_s
                frac_sun = max(-0.15, min(1.15, frac_sun))
            else:
                frac_sun = 0.5

            m_rise_dt_utc = self._lunar_cache["m_rise_ephem"].datetime()
            total_sec_m = self._lunar_cache["total_sec_m"]
            if total_sec_m > 0:
                frac_moon = (now_utc_naive - m_rise_dt_utc).total_seconds() / total_sec_m
                frac_moon = max(-0.15, min(1.15, frac_moon))
            else:
                frac_moon = 0.5

            data["glance"] = {
                **self._solar_cache,
                **self._lunar_cache,
                "frac_sun": frac_sun,
                "frac_moon": frac_moon,
            }

            return data
        except Exception as e:
            _LOGGER.error("Sky Lite Coordinator Math Error: %s", e)
            return {}
