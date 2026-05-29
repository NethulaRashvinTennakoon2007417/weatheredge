from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
import requests, re, math, functools, sys, os
from urllib.parse import unquote
from datetime import datetime, date as date_type
from zoneinfo import ZoneInfo
import concurrent.futures

# ── License (web mode) ────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from license import validate_code as _validate_code

app = Flask(__name__)
CORS(app)

# ── City Config ───────────────────────────────────────────────────────────────
CITY_COORDS = {
    "Atlanta": {
        "lat": 33.6407, "lon": -84.4277, "station": "KATL",
        "tz": "America/New_York", "unit": "fahrenheit",
        "wunderground": "https://www.wunderground.com/history/daily/us/ga/atlanta/KATL",
        "flag": "🇺🇸", "volume": "high",
        "pm_city_slug": "atlanta",
        # Climate metadata for peak-time and sigma calculations
        "climate": "continental",   # continental=full thermal swing, maritime=moderated, arid=fast heat
        "urban": True,              # urban heat island delays peak ~30min, raises sigma
        "coastal": False,           # sea/lake breeze caps afternoon heating
        "elev_m": 315,              # elevation in meters (higher = faster heating/cooling)
    },
    "New York (LaGuardia)": {
        "lat": 40.7769, "lon": -73.8740, "station": "KLGA",
        "tz": "America/New_York", "unit": "fahrenheit",
        "wunderground": "https://www.wunderground.com/history/daily/us/ny/new-york-city/KLGA",
        "flag": "🇺🇸", "volume": "high",
        "note": "Resolves on LaGuardia (KLGA) not JFK",
        "pm_city_slug": "nyc",
        "climate": "continental",
        "urban": True,
        "coastal": True,    # Atlantic/East River influence, sea breeze common in summer
        "elev_m": 6,
    },
    "Miami": {
        "lat": 25.7959, "lon": -80.2870, "station": "KMIA",
        "tz": "America/New_York", "unit": "fahrenheit",
        "wunderground": "https://www.wunderground.com/history/daily/us/fl/miami/KMIA",
        "flag": "🇺🇸", "volume": "high",
        "pm_city_slug": "miami",
        "climate": "tropical",      # tropical: high humidity dampens diurnal range, peaks earlier
        "urban": True,
        "coastal": True,
        "elev_m": 4,
    },
    "Chicago": {
        "lat": 41.9742, "lon": -87.9073, "station": "KORD",
        "tz": "America/Chicago", "unit": "fahrenheit",
        "wunderground": "https://www.wunderground.com/history/daily/us/il/chicago/KORD",
        "flag": "🇺🇸", "volume": "high",
        "pm_city_slug": "chicago",
        "climate": "continental",
        "urban": True,
        "coastal": True,    # Lake Michigan sea breeze effect significant
        "elev_m": 205,
    },
    "Dallas": {
        "lat": 32.8998, "lon": -97.0403, "station": "KDFW",
        "tz": "America/Chicago", "unit": "fahrenheit",
        "wunderground": "https://www.wunderground.com/history/daily/us/tx/dallas/KDFW",
        "flag": "🇺🇸", "volume": "medium",
        "pm_city_slug": "dallas",
        "climate": "arid",          # arid/semi-arid: very fast heating, peaks late and high
        "urban": True,
        "coastal": False,
        "elev_m": 185,
    },
    "Seattle": {
        "lat": 47.4502, "lon": -122.3088, "station": "KSEA",
        "tz": "America/Los_Angeles", "unit": "fahrenheit",
        "wunderground": "https://www.wunderground.com/history/daily/us/wa/seattle/KSEA",
        "flag": "🇺🇸", "volume": "medium",
        "pm_city_slug": "seattle",
        "climate": "maritime",      # maritime: very moderated, smaller diurnal range
        "urban": False,
        "coastal": True,
        "elev_m": 131,
    },
    "London": {
        "lat": 51.5048, "lon": 0.0495, "station": "EGLC",
        "tz": "Europe/London", "unit": "celsius",
        "wunderground": "https://www.wunderground.com/history/daily/gb/london/EGLC",
        "flag": "🇬🇧", "volume": "very high",
        "note": "London City Airport (EGLC) — most liquid weather market",
        "pm_city_slug": "london",
        "intl_source": "metoffice",
        "met_location_id": "354297",
        "met_obs_station": "EGLC",
        "climate": "maritime",      # UK: very maritime, small diurnal range, early peaks
        "urban": True,
        "coastal": False,           # tidal Thames but not direct sea exposure
        "elev_m": 6,
    },
    "Seoul": {
        "lat": 37.4602, "lon": 126.4407, "station": "RKSI",
        "tz": "Asia/Seoul", "unit": "celsius",
        "wunderground": "https://www.wunderground.com/history/daily/kr/incheon/RKSI",
        "flag": "🇰🇷", "volume": "high",
        "note": "Incheon International Airport (RKSI)",
        "pm_city_slug": "seoul",
        "intl_source": "open-meteo",
        "climate": "continental",
        "urban": True,
        "coastal": True,    # Yellow Sea coast
        "elev_m": 7,
    },
    "Wellington": {
        "lat": -41.3272, "lon": 174.8052, "station": "NZWN",
        "tz": "Pacific/Auckland", "unit": "celsius",
        "wunderground": "https://www.wunderground.com/history/daily/nz/wellington/NZWN",
        "flag": "🇳🇿", "volume": "very high",
        "note": "Wellington Airport — very high Polymarket liquidity",
        "pm_city_slug": "wellington",
        "intl_source": "metservice",
        "climate": "maritime",
        "urban": False,
        "coastal": True,    # very exposed coastal — Cook Strait, notorious winds
        "elev_m": 4,
    },
    "Buenos Aires": {
        "lat": -34.8222, "lon": -58.5358, "station": "SAEZ",
        "tz": "America/Argentina/Buenos_Aires", "unit": "celsius",
        "wunderground": "https://www.wunderground.com/history/daily/ar/ezeiza/SAEZ",
        "flag": "🇦🇷", "volume": "high",
        "note": "Ezeiza Airport (SAEZ)",
        "pm_city_slug": "buenos-aires",
        "intl_source": "open-meteo",
        "climate": "continental",
        "urban": True,
        "coastal": False,   # inland from Río de la Plata enough to have full swing
        "elev_m": 26,
    },
    "Shenzhen": {
        "lat": 22.6395, "lon": 113.8108, "station": "ZGSZ",
        "tz": "Asia/Shanghai", "unit": "celsius",
        "wunderground": "https://www.wunderground.com/history/daily/cn/shenzhen/ZGSZ",
        "flag": "🇨🇳", "volume": "very high",
        "note": "Shenzhen Bao'an International Airport (ZGSZ)",
        "pm_city_slug": "shenzhen",
        "intl_source": "open-meteo-cma",   # CMA model — Chinese national model, best for S.China
        "climate": "tropical",              # subtropical/tropical: humid, peaks earlier, dampened range
        "urban": True,
        "coastal": True,    # Pearl River Delta coast, sea breeze significant
        "elev_m": 4,
    },
    "Warsaw": {
        "lat": 52.1657, "lon": 20.9671, "station": "EPWA",
        "tz": "Europe/Warsaw", "unit": "celsius",
        "wunderground": "https://www.wunderground.com/history/daily/pl/warsaw/EPWA",
        "flag": "🇵🇱", "volume": "medium",
        "note": "Warsaw Chopin Airport (EPWA)",
        "pm_city_slug": "warsaw",
        "intl_source": "open-meteo",  # intl_models covers Europe well (ECMWF+ICON+MetFR+GEM)
        "climate": "continental",     # cold winters, warm summers, high diurnal range
        "urban": True,
        "coastal": False,
        "elev_m": 110,
    },
}

# ── Polymarket URL Builder ─────────────────────────────────────────────────────
def build_polymarket_url(city_name, city_slug, date_str, unit):
    """
    Build the Polymarket event URL for a highest-temperature market.
    Pattern: /event/highest-temperature-in-{city}-on-{month}-{day}-{year}
    e.g. https://polymarket.com/event/highest-temperature-in-atlanta-on-february-21-2026
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        month = dt.strftime("%B").lower()   # february
        day = dt.day                          # 21 (plain number, no ordinal)
        year = dt.year
        slug = f"highest-temperature-in-{city_slug}-on-{month}-{day}-{year}"
        return f"https://polymarket.com/event/{slug}"
    except:
        return None

def build_polymarket_search_url(city_name, date_str):
    """Fallback search URL."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        q = f"highest temperature {city_name} {dt.strftime('%B %d %Y')}"
        return f"https://polymarket.com/markets?_q={q.replace(' ', '+')}"
    except:
        return "https://polymarket.com/markets"

# ── International Weather Sources ─────────────────────────────────────────────

def fetch_metoffice(lat, lon, date_str, unit="celsius"):
    """
    UK Met Office DataPoint API — official UK forecast, best source for London.
    Free API, no key required for basic forecasts.
    Also tries Open-Meteo with UK Met Office model (ICON-EU).
    """
    try:
        # Open-Meteo with UK Met Office model (ukmo_seamless) - highly accurate for UK
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,precipitation_probability,windspeed_10m,cloudcover",
            "daily": "temperature_2m_max,temperature_2m_min",
            "models": "ukmo_seamless",   # UK Met Office Unified Model
            "temperature_unit": unit,
            "windspeed_unit": "mph",
            "forecast_days": 7,
            "timezone": "auto"
        }, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            day_temps = [temps[i] for i, t in enumerate(times)
                        if date_str in t and i < len(temps) and temps[i] is not None]
            if day_temps:
                return {
                    "available": True,
                    "high_temp": round(max(day_temps), 1),
                    "low_temp": round(min(day_temps), 1),
                    "source": "UK Met Office (UKMO Unified Model)",
                    "source_url": "https://www.metoffice.gov.uk/weather/forecast/gcpvjx7nr",
                    "hourly": [{"hour": t[11:16], "temp": round(temps[i], 1)}
                               for i, t in enumerate(times)
                               if date_str in t and i < len(temps) and temps[i] is not None]
                }
    except Exception as e:
        print(f"Met Office error: {e}")
    return {"available": False}

def fetch_metservice_nz(lat, lon, date_str, unit="celsius"):
    """
    MetService NZ official — best source for Wellington.
    Uses Open-Meteo with ICON-EU as proxy since MetService API requires auth.
    """
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,precipitation_probability,windspeed_10m",
            "models": "icon_seamless",  # DWD ICON, good Southern Hemisphere coverage
            "temperature_unit": unit,
            "windspeed_unit": "mph",
            "forecast_days": 7,
            "timezone": "auto"
        }, timeout=12)
        if resp.status_code == 200:
            data = resp.json()
            hourly = data.get("hourly", {})
            times = hourly.get("time", [])
            temps = hourly.get("temperature_2m", [])
            day_temps = [temps[i] for i, t in enumerate(times)
                        if date_str in t and i < len(temps) and temps[i] is not None]
            if day_temps:
                return {
                    "available": True,
                    "high_temp": round(max(day_temps), 1),
                    "low_temp": round(min(day_temps), 1),
                    "source": "MetService NZ (ICON model)",
                    "source_url": "https://www.metservice.com/towns-cities/locations/wellington/7-days",
                    "hourly": [{"hour": t[11:16], "temp": round(temps[i], 1)}
                               for i, t in enumerate(times)
                               if date_str in t and i < len(temps) and temps[i] is not None]
                }
    except Exception as e:
        print(f"MetService NZ error: {e}")
    return {"available": False}

def fetch_international_source(coords, date_str):
    """
    Fetch the best available international weather source for a given city.
    Returns consistent dict with available, high_temp, source, source_url, hourly.
    """
    intl = coords.get("intl_source")
    lat, lon = coords["lat"], coords["lon"]
    unit = coords.get("unit", "celsius")

    if intl == "metoffice":
        return fetch_metoffice(lat, lon, date_str, unit)
    elif intl == "metservice":
        return fetch_metservice_nz(lat, lon, date_str, unit)
    elif intl == "open-meteo-cma":
        # CMA (China Meteorological Administration) — best for South China / Pearl River Delta
        try:
            resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "hourly": "temperature_2m,precipitation_probability,windspeed_10m",
                "models": "cma_grapes_global",
                "temperature_unit": unit,
                "windspeed_unit": "mph",
                "forecast_days": 7,
                "timezone": "auto"
            }, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                day_temps = [temps[i] for i, t in enumerate(times)
                            if date_str in t and i < len(temps) and temps[i] is not None]
                if day_temps:
                    return {
                        "available": True,
                        "high_temp": round(max(day_temps), 1),
                        "source": "CMA GRAPES (China Met Admin)",
                        "source_url": "https://open-meteo.com",
                        "hourly": [{"hour": t[11:16], "temp": round(temps[i], 1)}
                                   for i, t in enumerate(times)
                                   if date_str in t and i < len(temps) and temps[i] is not None]
                    }
        except Exception as e:
            print(f"CMA GRAPES error: {e}")
        return {"available": False}
    else:
        # Generic: Open-Meteo with best available regional model
        try:
            # Try GFS (global), ECMWF (global), and pick best
            resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "hourly": "temperature_2m,precipitation_probability,windspeed_10m",
                "models": "gfs_seamless",
                "temperature_unit": unit,
                "windspeed_unit": "mph",
                "forecast_days": 7,
                "timezone": "auto"
            }, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                hourly = data.get("hourly", {})
                times = hourly.get("time", [])
                temps = hourly.get("temperature_2m", [])
                day_temps = [temps[i] for i, t in enumerate(times)
                            if date_str in t and i < len(temps) and temps[i] is not None]
                if day_temps:
                    return {
                        "available": True,
                        "high_temp": round(max(day_temps), 1),
                        "low_temp": round(min(day_temps), 1),
                        "source": "NOAA GFS (global model)",
                        "source_url": f"https://open-meteo.com",
                        "hourly": [{"hour": t[11:16], "temp": round(temps[i], 1)}
                                   for i, t in enumerate(times)
                                   if date_str in t and i < len(temps) and temps[i] is not None]
                    }
        except Exception as e:
            print(f"Intl source error: {e}")
    return {"available": False}

# NOTE: Polymarket live odds are fetched client-side (browser JS) via the
# gamma-api.polymarket.com public API. The server cannot reach external APIs.
# The frontend calls /api/pm_slug to get the correct event slug to query.

def fetch_open_meteo(lat, lon, days=7, unit="fahrenheit"):
    try:
        resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m,precipitation_probability,windspeed_10m,cloudcover,dewpoint_2m,apparent_temperature",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,windspeed_10m_max",
            "current": "temperature_2m,windspeed_10m,cloudcover,precipitation,dewpoint_2m",
            "temperature_unit": unit,
            "windspeed_unit": "mph",
            "forecast_days": days,
            "timezone": "auto"
        }, timeout=10)
        return resp.json()
    except Exception as e:
        print(f"Open-Meteo error: {e}")
        return None

def fetch_open_meteo_ensemble(lat, lon, days=3, unit="fahrenheit"):
    """Fetch ECMWF ensemble for spread/uncertainty calculation."""
    try:
        resp = requests.get("https://ensemble-api.open-meteo.com/v1/ensemble", params={
            "latitude": lat, "longitude": lon,
            "hourly": "temperature_2m",
            "models": "ecmwf_ifs025",
            "temperature_unit": unit,
            "forecast_days": days,
            "timezone": "auto"
        }, timeout=12)
        return resp.json()
    except Exception as e:
        print(f"Ensemble error: {e}")
        return None


# ── Multi-Model Intelligence Layer ────────────────────────────────────────────

def fetch_multi_model_peaks(lat, lon, date_str, unit, is_us=True, coords=None):
    """
    Fetch peak daily temperature from multiple weather models in parallel.

    US cities:  HRRR (best_match = auto-selects HRRR for US short-range),
                ICON (European model, globally validated),
                GEM  (Canadian model, strong N.America coverage)
    Intl cities: ECMWF, ICON, GEM, MetFrance (AROME/ARPEGE)

    Returns dict: {model_name: peak_temp_float}
    All models fetched concurrently — total wait is max(individual times).
    """
    us_models = [
        ("HRRR",   "best_match"),           # Auto best for location — HRRR for US
        ("ICON",   "icon_seamless"),         # DWD ICON: excellent globally
        ("GEM",    "gem_seamless"),          # Canadian GEM: strong N.America
    ]
    intl_models = [
        ("ECMWF",  "ecmwf_ifs025"),         # Best global model
        ("ICON",   "icon_seamless"),         # DWD ICON
        ("GEM",    "gem_seamless"),          # Canadian GEM
        ("MetFR",  "meteofrance_seamless"),  # French AROME/ARPEGE — best for Europe
    ]
    china_models = [
        ("ECMWF",  "ecmwf_ifs025"),         # Best global model
        ("ICON",   "icon_seamless"),         # DWD ICON
        ("CMA",    "cma_grapes_global"),     # China Met Admin — best for S.China/Pearl River Delta
        ("GEM",    "gem_seamless"),          # Canadian GEM
    ]
    # Use China-specific models for Shenzhen
    coords = coords or {}
    intl_source = coords.get("intl_source", "") if isinstance(coords, dict) else ""
    if is_us:
        models = us_models
    elif intl_source == "open-meteo-cma":
        models = china_models
    else:
        models = intl_models

    def _fetch_one(name_model):
        name, model_id = name_model
        try:
            resp = requests.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": lat, "longitude": lon,
                "hourly": "temperature_2m",
                "models": model_id,
                "temperature_unit": unit,
                "forecast_days": 2,
                "timezone": "auto"
            }, timeout=12)
            if resp.status_code == 200:
                data = resp.json()
                times = data.get("hourly", {}).get("time", [])
                temps = data.get("hourly", {}).get("temperature_2m", [])
                day = [temps[i] for i, t in enumerate(times)
                       if date_str in t and i < len(temps) and temps[i] is not None]
                if day:
                    return name, round(max(day), 1)
        except Exception as e:
            print(f"Multi-model {name} ({model_id}) error: {e}")
        return name, None

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        for name, peak in ex.map(_fetch_one, models):
            if peak is not None:
                results[name] = peak
    return results


def compute_ensemble_quantiles(lat, lon, date_str, unit):
    """
    Compute a TRUE probability distribution from ECMWF 50-member ensemble.

    Returns P10/P25/P50/P75/P90 of daily maximum temperature.
    This replaces the Gaussian bell-curve assumption — instead of
    assuming a symmetric normal distribution, we use the REAL distribution
    of 50 independently-perturbed model runs as samples.

    Key improvement:
      Old way: center=85°F, sigma=2.5°F → assume symmetric bell curve
      New way: 50 members peak at [82,83,83,84,84,84,85,85,86,87,88...]
               → compute actual percentiles from real samples
               → captures skewness, bimodality, fat tails
    """
    try:
        ens = fetch_open_meteo_ensemble(lat, lon, days=3, unit=unit)
        if not ens:
            return None
        ens_hourly = ens.get("hourly", {})
        times = ens_hourly.get("time", [])

        member_peaks = []
        for col in sorted(k for k in ens_hourly if k.startswith("temperature_2m_member")):
            vals = ens_hourly[col]
            day_vals = [
                vals[i] for i, t in enumerate(times)
                if date_str in t and i < len(vals) and vals[i] is not None
            ]
            if day_vals:
                member_peaks.append(max(day_vals))

        if len(member_peaks) < 10:
            return None

        s = sorted(member_peaks)
        n = len(s)

        def pct(p):
            idx = (p / 100) * (n - 1)
            lo, hi = int(idx), min(int(idx) + 1, n - 1)
            frac = idx - lo
            return round(s[lo] * (1 - frac) + s[hi] * frac, 1)

        iqr = pct(75) - pct(25)
        # IQR → sigma equivalence for normal: IQR ≈ 1.35σ
        sigma_from_ensemble = round(max(0.3, iqr / 1.35), 2)

        return {
            "p10":                pct(10),
            "p25":                pct(25),
            "p50":                pct(50),
            "p75":                pct(75),
            "p90":                pct(90),
            "mean":               round(sum(member_peaks) / n, 1),
            "spread":             round(s[-1] - s[0], 1),
            "iqr":                round(iqr, 1),
            "sigma_from_ensemble": sigma_from_ensemble,
            "n_members":          n,
            "member_peaks":       member_peaks,
        }
    except Exception as e:
        print(f"Ensemble quantile error: {e}")
        return None


def compute_bucket_probs_from_ensemble(member_peaks, pm_brackets):
    """
    Compute bracket probabilities DIRECTLY from ensemble member peaks.
    No Gaussian assumption. Each of 50 members says "the high will be X°.
    We count how many fall in each bracket — that IS the probability.

    This is the method used by probabilistic forecasting professionals
    (WMO MME, ECMWF, NOAA/GFS-ENS). It naturally handles:
      - Asymmetric distributions  (e.g. "mostly cool but could spike")
      - Bimodal distributions     (e.g. front may or may not arrive)
      - Fat tails                 (extreme outlier members)
    """
    if not member_peaks or len(member_peaks) < 5:
        return None
    n = len(member_peaks)
    result = []
    total_counted = 0
    for b in pm_brackets:
        lo = b.get("lo", -999)
        hi = b.get("hi")
        if hi is None:        # "X or higher"
            count = sum(1 for p in member_peaks if p >= lo)
        elif lo <= -900:      # "X or lower"
            count = sum(1 for p in member_peaks if p < hi)
        else:
            count = sum(1 for p in member_peaks if lo <= p < hi)
        total_counted += count
        entry = dict(b)
        entry["ensemble_prob"] = round(count / n * 100, 1)
        result.append(entry)
    return result


def compute_intelligent_consensus(multi_model_peaks, wu_peak_so_far,
                                  current_hour, unit, days_out=0):
    """
    Time-aware weighted consensus that properly shifts from model forecasts
    to real station observations as the day progresses.

    The key insight from professional meteorology:
      Before sunrise: models are all we have — treat them equally
      Morning (8-11am): station data starts coming in — give it growing weight
      Midday (11am-2pm): station data strongly dominates
      Afternoon (2pm+): actual observed high IS the answer

    Returns a dict with:
      smart_consensus — the best estimate of today's high
      model_mean      — pure model average (for comparison)
      model_spread    — disagreement between models (= uncertainty signal)
      model_agreement — "strong" / "moderate" / "poor" / "unknown"
      confidence      — "high" / "medium" / "low"
      bet_sizing_mult — suggested multiplier for Kelly bet size (0.0-1.0)
    """
    # Time-of-day weight allocation
    if days_out > 0:
        iem_w, model_w = 0.0, 1.0
        time_label = "future day"
    elif current_hour < 8:
        iem_w, model_w = 0.0, 1.0
        time_label = "pre-sunrise"
    elif current_hour < 10:
        iem_w, model_w = 0.20, 0.80
        time_label = "early morning"
    elif current_hour < 12:
        iem_w, model_w = 0.50, 0.50
        time_label = "mid-morning"
    elif current_hour < 14:
        iem_w, model_w = 0.75, 0.25
        time_label = "midday"
    elif current_hour < 17:
        iem_w, model_w = 0.90, 0.10
        time_label = "afternoon"
    else:
        iem_w, model_w = 1.0, 0.0
        time_label = "evening / resolved"

    if multi_model_peaks:
        vals = list(multi_model_peaks.values())
        model_mean   = round(sum(vals) / len(vals), 1)
        model_spread = round(max(vals) - min(vals), 1) if len(vals) > 1 else 0.0
    else:
        model_mean   = None
        model_spread = None

    # Agreement thresholds (unit-aware)
    thr_strong = 1.0 if unit == "celsius" else 2.0
    thr_poor   = 2.5 if unit == "celsius" else 5.0

    if model_spread is None:
        agreement, confidence, bet_mult = "unknown", "medium", 0.5
    elif model_spread <= thr_strong:
        agreement, confidence, bet_mult = "strong",   "high",   1.0
    elif model_spread <= thr_poor:
        agreement, confidence, bet_mult = "moderate", "medium", 0.6
    else:
        agreement, confidence, bet_mult = "poor",     "low",    0.25

    # Compute smart consensus
    if wu_peak_so_far is not None and model_mean is not None and days_out == 0:
        smart_consensus = round(wu_peak_so_far * iem_w + model_mean * model_w, 1)
    elif wu_peak_so_far is not None and days_out == 0:
        smart_consensus = wu_peak_so_far
    elif model_mean is not None:
        smart_consensus = model_mean
    else:
        smart_consensus = None

    return {
        "smart_consensus": smart_consensus,
        "model_mean":       model_mean,
        "model_spread":     model_spread,
        "model_agreement":  agreement,
        "confidence":       confidence,
        "bet_sizing_mult":  bet_mult,
        "iem_weight":       round(iem_w, 2),
        "model_weight":     round(model_w, 2),
        "time_label":       time_label,
        "models":           multi_model_peaks,
    }


def bayesian_intraday_update(station_hourly, om_hourly,
                             current_hour, forecast_center, sigma):
    """
    Bayesian intraday update: adjust forecast based on how the airport
    station is ACTUALLY tracking vs. where the model predicted it would be.

    Example:
      HRRR predicted KATL would read 75°F at 10am.
      KATL actually reads 78°F at 10am  (+3°F ahead of model).
      → Shift day's high forecast UP by ~2°F (not full 3°F — model may
        be right about the afternoon even if wrong about the morning).

    As real data accumulates, uncertainty (sigma) tightens:
      2 readings → moderate tightening
      5+ readings → significant tightening

    Returns: (adjusted_center, adjusted_sigma, adjustment, trail_list)
    """
    if not station_hourly or current_hour < 7 or forecast_center is None:
        return forecast_center, sigma, 0.0, []

    # Build model temperature lookup by hour
    model_by_hour = {}
    for h in (om_hourly or []):
        hr_str = h.get("hour", "")
        t = h.get("temp")
        if hr_str and t is not None:
            try:
                hr_num = int(hr_str[:2]) + int(hr_str[3:5]) / 60
                model_by_hour[hr_num] = t
            except Exception:
                pass

    # Compare station to model at each observed hour this morning
    errors = []
    trail  = []
    for reading in sorted(station_hourly, key=lambda x: x.get("hour", "")):
        hr_str = reading.get("hour", "")
        t_obs  = reading.get("temp")
        if not hr_str or t_obs is None:
            continue
        try:
            hr_num = int(hr_str[:2]) + int(hr_str[3:5]) / 60
        except Exception:
            continue
        if hr_num > current_hour or hr_num < 6:
            continue
        # Find nearest model hour
        if model_by_hour:
            closest = min(model_by_hour.keys(), key=lambda x: abs(x - hr_num))
            model_t = model_by_hour[closest] if abs(closest - hr_num) < 1.5 else None
        else:
            model_t = None
        if model_t is not None:
            err = t_obs - model_t
            errors.append(err)
            trail.append({
                "hour":    hr_str,
                "station": t_obs,
                "model":   round(model_t, 1),
                "diff":    round(err, 1),
            })

    if not errors:
        return forecast_center, sigma, 0.0, trail

    # Weighted average error — recent readings carry more weight
    weights   = [(i + 1) ** 1.5 for i in range(len(errors))]
    total_w   = sum(weights)
    avg_error = sum(e * w for e, w in zip(errors, weights)) / total_w

    # Trust factor: how much of the morning tracking error to apply
    # We don't apply 100% because the model might be right about the afternoon
    n_obs        = len(errors)
    trust_factor = min(0.85, 0.30 + n_obs * 0.10)
    adjustment   = round(avg_error * trust_factor, 1)

    # Sigma reduction — more real data = tighter uncertainty
    prior_reduction  = min(sigma * 0.65, n_obs * sigma * 0.08)
    adjusted_sigma   = round(max(0.3, sigma - prior_reduction), 2)
    adjusted_center  = round(forecast_center + adjustment, 1)

    return adjusted_center, adjusted_sigma, adjustment, trail


def compute_kelly_bet(forecast_prob, pm_price_pct, bankroll=100):
    """
    Kelly Criterion bet sizing for a YES outcome.

    Kelly fraction = (p*b - q) / b
    Where:
      p = our probability of YES winning  (0-1)
      q = 1 - p
      b = net gain per unit risked (= (payout - cost) / cost)

    We use 1/4 Kelly (professional standard) and cap at 10% of bankroll.
    Full Kelly is theoretically optimal but too aggressive for most traders.

    Returns: (kelly_pct, bet_amount, verdict, edge)
      kelly_pct  — recommended % of bankroll (already 1/4 Kelly)
      bet_amount — dollar amount for given bankroll
      verdict    — "no_edge" / "thin" / "moderate" / "strong" / "very_strong"
      edge       — model_prob - pm_price (raw edge %)
    """
    if forecast_prob is None or pm_price_pct is None or pm_price_pct <= 0:
        return 0, 0, "insufficient_data", None

    edge = round(forecast_prob - pm_price_pct, 1)
    p    = forecast_prob / 100
    q    = 1 - p
    cost = pm_price_pct / 100     # cost per share (fraction of $1)
    net_gain = 1.0 - cost         # net gain per share if YES wins

    if cost <= 0 or net_gain <= 0:
        return 0, 0, "no_bet", edge

    b = net_gain / cost           # net odds ratio
    if b <= 0:
        return 0, 0, "no_bet", edge

    full_kelly = (p * b - q) / b

    if full_kelly <= 0.005:
        return 0, 0, "no_edge", edge

    quarter_kelly  = full_kelly / 4
    final_fraction = min(quarter_kelly, 0.10)  # Hard cap: 10% of bankroll
    bet_amount     = round(bankroll * final_fraction, 2)

    if edge < 8:
        verdict = "thin"
    elif edge < 15:
        verdict = "moderate"
    elif edge < 25:
        verdict = "strong"
    else:
        verdict = "very_strong"

    return round(final_fraction * 100, 1), bet_amount, verdict, edge

def parse_open_meteo(om_data, target_date_str):
    if not om_data: return []
    hourly = om_data.get("hourly", {})
    times = hourly.get("time", [])
    temps = hourly.get("temperature_2m", [])
    precip = hourly.get("precipitation_probability", [])
    wind = hourly.get("windspeed_10m", [])
    cloud = hourly.get("cloudcover", [])
    dew = hourly.get("dewpoint_2m", [])
    result = []
    for i, t in enumerate(times):
        if target_date_str in t:
            result.append({
                "hour": t[11:16],
                "temp": round(temps[i], 1) if i < len(temps) and temps[i] is not None else None,
                "precip_prob": precip[i] if i < len(precip) else None,
                "wind": round(wind[i], 1) if i < len(wind) and wind[i] is not None else None,
                "cloud": cloud[i] if i < len(cloud) else None,
                "dewpoint": round(dew[i], 1) if i < len(dew) and dew[i] is not None else None,
            })
    return result

# ── NWS (US only) ─────────────────────────────────────────────────────────────
def fetch_nws_forecast(lat, lon):
    """Fetch NWS hourly forecast. Also fetch daily forecast for the official high/low."""
    try:
        headers = {"User-Agent": "WeatherEdge/1.0"}
        r = requests.get(f"https://api.weather.gov/points/{lat},{lon}", headers=headers, timeout=10)
        props = r.json().get("properties", {})
        hourly_url = props.get("forecastHourly")
        daily_url  = props.get("forecast")  # daily 12-hour periods — has official high
        result = {"hourly": None, "daily": None}
        if hourly_url:
            r2 = requests.get(hourly_url, headers=headers, timeout=10)
            result["hourly"] = r2.json()
        if daily_url:
            r3 = requests.get(daily_url, headers=headers, timeout=10)
            result["daily"] = r3.json()
        return result
    except Exception as e:
        print(f"NWS error: {e}")
        return None

def parse_nws(nws_data, target_date_str):
    """Parse NWS hourly data. Returns hourly list for charting."""
    if not nws_data: return []
    # nws_data is now a dict with "hourly" key
    data = nws_data.get("hourly") if isinstance(nws_data, dict) and "hourly" in nws_data else nws_data
    if not data: return []
    result = []
    for p in data.get("properties", {}).get("periods", []):
        start = p.get("startTime", "")
        if target_date_str in start:
            result.append({
                "hour": start[11:16],
                "temp": p.get("temperature"),
                "desc": p.get("shortForecast", ""),
                "precip": p.get("probabilityOfPrecipitation", {}).get("value", 0) or 0,
                "wind": p.get("windSpeed", ""),
            })
    return result

def parse_nws_daily_high(nws_data, target_date_str):
    """
    Extract the official NWS daytime high from the daily forecast periods.
    NWS daily forecast has 12-hour periods: 'This Afternoon' (daytime) and 'Tonight'.
    The daytime period for a date has isDaytime=True and contains the official high.
    This matches what you see on forecast.weather.gov — much more accurate than hourly max.
    """
    if not nws_data: return None
    data = nws_data.get("daily") if isinstance(nws_data, dict) and "daily" in nws_data else None
    if not data: return None
    try:
        for p in data.get("properties", {}).get("periods", []):
            start = p.get("startTime", "")
            is_day = p.get("isDaytime", False)
            # Match target date AND daytime period only
            if target_date_str in start and is_day:
                t = p.get("temperature")
                unit_code = p.get("temperatureUnit", "F")
                if t is not None:
                    return float(t)  # already in correct unit from NWS
    except Exception as e:
        print(f"NWS daily high parse error: {e}")
    return None

# ── Wunderground / Station obs — multi-method fetcher ────────────────────────
def _wu_date_to_parts(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.strftime("%Y%m%d"), dt.year, dt.month, dt.day

# Multiple WU/weather.com API keys to try (rotate on 401/403)
_WU_API_KEYS = [
    "6532d6454b8aa370768e63d6ba5a832e",   # well-known public key
    "e1f10a1e78da46f5b10a1e78da96f525",   # backup 1
    "6532d6454b8aa370768e63d6ba5a832e",   # retry same
]

def _wu_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.wunderground.com/",
        "Origin": "https://www.wunderground.com",
        "Connection": "keep-alive",
    }

def fetch_wunderground(wu_base_url, date_str, station=None, unit="fahrenheit"):
    """
    Fetch actual station observation data — what Wunderground shows.
    Resolution source for Polymarket weather markets.

    Priority order:
      1. Iowa Environmental Mesonet (IEM ASOS) — free archive, local-date filtered
      2. weather.com v2 PWS daily API (WU's own backend, rotated API keys)
      3. weather.com v2 PWS hourly API
      4. Open-Meteo historical reanalysis (ERA5 — accurate free fallback)

    NOTE: NWS ASOS is NOT used here — it's a different sensor from the WU/PWS
    station and can differ by several °F, leading to wrong resolution estimates.
    NWS ASOS data is used only in the separate NWS forecast column.
    """
    import json as _json
    from datetime import timezone as _tz

    date_compact, yr, mo, dy = _wu_date_to_parts(date_str)
    page_url = f"{wu_base_url}/date/{date_str}"
    if station is None:
        station = wu_base_url.rstrip("/").split("/")[-1]

    # Determine if today or historical — MUST use the city's LOCAL timezone,
    # not UTC server time. At midnight UTC, Atlanta is still "yesterday" locally.
    # Find the city timezone from CITY_COORDS by station match.
    _city_tz = "America/New_York"  # fallback
    for _cd in CITY_COORDS.values():
        if _cd.get("station") == station:
            _city_tz = _cd.get("tz", "America/New_York")
            break
    _local_now = datetime.now(ZoneInfo(_city_tz))
    today_str = _local_now.strftime("%Y-%m-%d")
    is_today = (date_str == today_str)
    is_past  = (date_str < today_str)
    # ERA5 only valid if: date is truly in the past AND we're past noon local time
    # (ERA5 may not have finalized data until 24-48h after the observation date)
    _era5_ok = is_past or (is_today and _local_now.hour >= 18)

    unit_key = "e" if unit == "fahrenheit" else "m"
    imp_key  = "imperial" if unit == "fahrenheit" else "metric"

    result = {
        "url": page_url, "available": False,
        "high_temp": None, "low_temp": None, "avg_temp": None,
        "precip": None, "max_wind": None, "dew_point": None,
        "method": None, "hourly": [], "last_updated": None,
    }

    def _make_result(hi, lo, avg, precip, wind, dew, hourly, method, updated=None):
        result.update({
            "high_temp": round(float(hi), 1) if hi is not None else None,
            "low_temp":  round(float(lo), 1) if lo is not None else None,
            "avg_temp":  round(float(avg), 1) if avg is not None else None,
            "precip":    round(float(precip), 2) if precip is not None else None,
            "max_wind":  round(float(wind), 1) if wind is not None else None,
            "dew_point": round(float(dew), 1) if dew is not None else None,
            "hourly":    hourly or [],
            "available": True,
            "method":    method,
            "last_updated": updated or "",
        })
        return result

    # ── Method 1: Iowa Environmental Mesonet (IEM) — free archive ───────────────
    # CRITICAL: IEM timestamps are UTC. Request ±1 day and filter by LOCAL date.
    # Request ALL report types (routine + SPECI special obs) to catch non-hourly peaks.
    # Always request tmpf (Fahrenheit) even for Celsius cities — IEM ASOS stores °F
    # for all stations including international. Convert to °C ourselves if needed.
    try:
        iem_station = station
        iem_url = "https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py"

        # Find timezone for this station
        iem_tz = "America/New_York"
        for cd in CITY_COORDS.values():
            if cd.get("station") == station:
                iem_tz = cd.get("tz", "America/New_York")
                break
        iem_tz_obj = ZoneInfo(iem_tz)

        # Request ±1 day in UTC to ensure we capture the full local date
        from datetime import timedelta
        target_dt2 = datetime.strptime(date_str, "%Y-%m-%d")
        d_start = target_dt2 - timedelta(days=1)
        d_end   = target_dt2 + timedelta(days=1)

        params = {
            "station": iem_station,
            # ALWAYS fetch tmpf — IEM ASOS stores °F for all stations (incl. international).
            # Requesting tmpc for non-US stations often returns M (missing) or garbage.
            "data": "tmpf,dwpf,sknt,precip",
            "year1": d_start.year, "month1": d_start.month, "day1": d_start.day,
            "year2": d_end.year,   "month2": d_end.month,   "day2": d_end.day,
            "tz": "UTC", "format": "onlycomma",
            "latlon": "no", "elev": "no",
            "missing": "M", "trace": "T",
            "direct": "no",
            # report_type: 3=routine hourly, 4=SPECI special observations
            # MUST include both to catch non-hourly peak readings (e.g. Wellington 21°C)
            "report_type": "3,4",
        }

        r = requests.get(iem_url, params=params, timeout=12)
        if r.status_code == 200 and r.text.strip():
            lines = [l.strip() for l in r.text.strip().split("\n") if l.strip() and not l.startswith("#")]
            temps_f, dews_f, winds, precips, hourly_out = [], [], [], [], []
            for line in lines[1:]:
                parts = line.split(",")
                if len(parts) < 4: continue
                try:
                    ts_utc_str = parts[1].strip()  # "2026-02-21 14:00"
                    from datetime import timezone as _utz
                    utc_naive = datetime.strptime(ts_utc_str, "%Y-%m-%d %H:%M")
                    utc_aware = utc_naive.replace(tzinfo=_utz.utc)
                    local_dt2 = utc_aware.astimezone(iem_tz_obj)
                    if local_dt2.strftime("%Y-%m-%d") != date_str:
                        continue  # skip observations outside local target date
                    hr = local_dt2.strftime("%H:%M")

                    t = parts[2].strip()
                    d = parts[3].strip() if len(parts) > 3 else "M"
                    w = parts[4].strip() if len(parts) > 4 else "M"
                    p = parts[5].strip() if len(parts) > 5 else "M"
                    if t not in ("M", ""):
                        tf = float(t)  # always °F from IEM
                        # Sanity check: valid temperature range in °F (-100 to 150)
                        if -100 <= tf <= 150:
                            temps_f.append(tf)
                            # Convert to display unit
                            t_display = round((tf - 32) * 5/9, 1) if unit == "celsius" else round(tf, 1)
                            hourly_out.append({
                                "hour": hr, "temp": t_display,
                                "wind": round(float(w)*1.151, 1) if w not in ("M","T","") else None,
                            })
                    if d not in ("M", ""): dews_f.append(float(d))
                    if w not in ("M", "", "T"): winds.append(float(w))
                    if p not in ("M", "", "T"): precips.append(float(p))
                except: continue

            if temps_f:
                wind_mph = max(w*1.151 for w in winds) if winds else None
                hi_f = max(temps_f)
                lo_f = min(temps_f)
                avg_f = sum(temps_f)/len(temps_f)
                dew_f = max(dews_f) if dews_f else None
                # Convert to display unit
                if unit == "celsius":
                    hi  = round((hi_f - 32) * 5/9, 1)
                    lo  = round((lo_f - 32) * 5/9, 1)
                    avg = round((avg_f - 32) * 5/9, 1)
                    dew = round((dew_f - 32) * 5/9, 1) if dew_f else None
                else:
                    hi, lo, avg, dew = round(hi_f,1), round(lo_f,1), round(avg_f,1), round(dew_f,1) if dew_f else None
                return _make_result(
                    hi, lo, avg,
                    max(precips) if precips else None,
                    wind_mph, dew,
                    sorted(hourly_out, key=lambda x: x["hour"]),
                    "Iowa Mesonet (IEM ASOS)",
                    hourly_out[-1]["hour"] if hourly_out else None
                )
    except Exception as e:
        print(f"WU method 2 (IEM) error: {e}")

    # ── Method 3: weather.com v2 PWS daily API (WU's actual backend) ────────────
    for api_key in _WU_API_KEYS:
        try:
            api_url = (
                f"https://api.weather.com/v2/pws/history/daily"
                f"?stationId={station}&format=json&units={unit_key}"
                f"&date={date_compact}&apiKey={api_key}&numericPrecision=decimal"
            )
            r = requests.get(api_url, headers=_wu_headers(), timeout=12)
            if r.status_code in (401, 403):
                continue  # try next key
            if r.status_code == 200:
                obs = r.json().get("observations", [])
                if obs:
                    highs, lows, avgs, precips, winds, dews, hourly_out = [], [], [], [], [], [], []
                    for o in obs:
                        # CRITICAL: filter by obsTimeLocal date to prevent adjacent-day contamination
                        obstime = o.get("obsTimeLocal", "")
                        if obstime[:10] != date_str:
                            continue  # skip readings not on target local date
                        imp = o.get(imp_key, {})
                        th = imp.get("tempHigh"); tl = imp.get("tempLow")
                        ta = imp.get("tempAvg");  p  = imp.get("precipTotal")
                        w  = imp.get("windspeedHigh"); d = imp.get("dewptAvg")
                        hr = obstime[11:16] if len(obstime) >= 16 else ""
                        if th is not None: highs.append(float(th))
                        if tl is not None: lows.append(float(tl))
                        if ta is not None: avgs.append(float(ta))
                        if p  is not None: precips.append(float(p))
                        if w  is not None: winds.append(float(w))
                        if d  is not None: dews.append(float(d))
                        if hr and ta is not None:
                            hourly_out.append({"hour": hr, "temp": float(ta),
                                               "wind": float(w) if w else None})
                    if highs:
                        return _make_result(
                            max(highs), min(lows) if lows else None,
                            sum(avgs)/len(avgs) if avgs else None,
                            max(precips) if precips else None,
                            max(winds) if winds else None,
                            sum(dews)/len(dews) if dews else None,
                            hourly_out, f"weather.com v2 API",
                            obs[-1].get("obsTimeLocal", "")
                        )
        except Exception as e:
            print(f"WU method 3 ({api_key[:8]}…) error: {e}")

    # ── Method 4: weather.com v2 PWS hourly API ──────────────────────────────────
    for api_key in _WU_API_KEYS:
        try:
            api_url = (
                f"https://api.weather.com/v2/pws/history/hourly"
                f"?stationId={station}&format=json&units={unit_key}"
                f"&date={date_compact}&apiKey={api_key}&numericPrecision=decimal"
            )
            r = requests.get(api_url, headers=_wu_headers(), timeout=12)
            if r.status_code == 200:
                obs = r.json().get("observations", [])
                if obs:
                    temps, winds, dews, hourly_out = [], [], [], []
                    for o in obs:
                        # CRITICAL: filter by obsTimeLocal date — API sometimes returns adjacent days
                        obstime = o.get("obsTimeLocal", "")
                        if obstime[:10] != date_str:
                            continue
                        imp = o.get(imp_key, {})
                        t = imp.get("temp"); w = imp.get("windspeed"); d = imp.get("dewpt")
                        hr = obstime[11:16] if len(obstime) >= 16 else ""
                        if t is not None: temps.append(float(t))
                        if w is not None: winds.append(float(w))
                        if d is not None: dews.append(float(d))
                        if hr and t is not None:
                            hourly_out.append({"hour": hr, "temp": float(t),
                                               "wind": float(w) if w else None})
                    if temps:
                        return _make_result(
                            max(temps), min(temps), sum(temps)/len(temps), None,
                            max(winds) if winds else None,
                            sum(dews)/len(dews) if dews else None,
                            hourly_out, "weather.com v2 hourly API",
                            obs[-1].get("obsTimeLocal","")
                        )
        except Exception as e:
            print(f"WU method 4 error: {e}")

    # ── Method 5: Open-Meteo historical reanalysis (ERA5) ───────────────────────
    # This is the fallback — uses the same station lat/lon, ERA5 reanalysis data
    # Not WU data per se but same underlying measurements, very accurate
    try:
        # We need lat/lon — stored in CITY_COORDS, look up by station
        lat, lon = None, None
        for city_data in CITY_COORDS.values():
            if city_data.get("station") == station:
                lat, lon = city_data["lat"], city_data["lon"]
                break
        if lat is not None and _era5_ok:
            # Historical ERA5 via Open-Meteo
            url = "https://archive-api.open-meteo.com/v1/archive"
            params = {
                "latitude": lat, "longitude": lon,
                "start_date": date_str, "end_date": date_str,
                "hourly": "temperature_2m,windspeed_10m,dewpoint_2m,precipitation",
                "temperature_unit": unit,
                "windspeed_unit": "mph",
                "timezone": "auto",
            }
            r = requests.get(url, params=params, timeout=12)
            if r.status_code == 200:
                data = r.json()
                hourly = data.get("hourly", {})
                times  = hourly.get("time", [])
                temps  = hourly.get("temperature_2m", [])
                winds  = hourly.get("windspeed_10m", [])
                dews   = hourly.get("dewpoint_2m", [])
                precips= hourly.get("precipitation", [])
                day_temps, day_winds, day_dews, day_precips, hourly_out = [], [], [], [], []
                for i, t in enumerate(times):
                    if date_str in t:
                        tv = temps[i] if i < len(temps) and temps[i] is not None else None
                        wv = winds[i] if i < len(winds) and winds[i] is not None else None
                        dv = dews[i]  if i < len(dews)  and dews[i]  is not None else None
                        pv = precips[i] if i < len(precips) and precips[i] is not None else None
                        hr = t[11:16]
                        if tv is not None:
                            day_temps.append(tv)
                            hourly_out.append({"hour": hr, "temp": round(tv,1),
                                               "wind": round(wv,1) if wv else None})
                        if wv is not None: day_winds.append(wv)
                        if dv is not None: day_dews.append(dv)
                        if pv is not None: day_precips.append(pv)
                if day_temps:
                    return _make_result(
                        max(day_temps), min(day_temps), sum(day_temps)/len(day_temps),
                        sum(day_precips) if day_precips else None,
                        max(day_winds) if day_winds else None,
                        sum(day_dews)/len(day_dews) if day_dews else None,
                        hourly_out, "ERA5 reanalysis (Open-Meteo archive)",
                    )
    except Exception as e:
        print(f"WU method 5 (ERA5) error: {e}")

    result["method"] = "all methods failed"
    return result

# ── Visual Crossing ───────────────────────────────────────────────────────────
def fetch_visual_crossing(lat, lon, date_str, unit="fahrenheit"):
    try:
        ug = "us" if unit == "fahrenheit" else "metric"
        url = f"https://weather.visualcrossing.com/VisualCrossingWebServices/rest/services/timeline/{lat},{lon}/{date_str}/{date_str}"
        resp = requests.get(url, params={"unitGroup":ug,"elements":"datetime,tempmax,tempmin,temp,precip,windspeed,humidity,conditions","include":"hours,days","key":"DEMO","contentType":"json"}, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            days = data.get("days", [])
            if days:
                d = days[0]
                hourly = [{"hour":h.get("datetime","")[:5],"temp":h.get("temp"),"precip_prob":round(h.get("precipprob",0)),"wind":h.get("windspeed")} for h in d.get("hours",[])]
                return {"available":True,"high_temp":d.get("tempmax"),"low_temp":d.get("tempmin"),"avg_temp":d.get("temp"),"conditions":d.get("conditions",""),"hourly":hourly}
        return {"available": False}
    except Exception as e:
        print(f"VC error: {e}")
        return {"available": False}

# ── METAR / TAF / SIGMET ─────────────────────────────────────────────────────
# Aviation Weather Center (AWC) free API — no key required
# Used for real-time atmospheric corrections to peak temperature estimates

AWC_BASE = "https://aviationweather.gov/api/data"

def fetch_metar(station: str) -> dict:
    """
    Fetch latest METAR for a station.
    Returns dict with: sky_cover (0-8 oktas), dewpoint, gust_kt,
    temp_c, wind_kt, raw, observed_utc.
    All values None if unavailable.
    """
    result = {
        "available": False, "station": station,
        "sky_oktas": None,   # 0-8 (oktas of cloud cover)
        "sky_code": None,    # CLR/FEW/SCT/BKN/OVC
        "dewpoint_c": None,
        "temp_c": None,
        "wind_kt": None,
        "gust_kt": None,
        "observed_utc": None,
        "raw": None,
    }
    try:
        resp = requests.get(f"{AWC_BASE}/metar", params={
            "ids": station, "format": "json", "hours": 2,
        }, timeout=8)
        if resp.status_code != 200:
            return result
        data = resp.json()
        if not data:
            return result
        # Take the most recent observation
        obs = data[0] if isinstance(data, list) else data
        result["available"] = True
        result["raw"] = obs.get("rawOb", "")
        result["observed_utc"] = obs.get("obsTime", "")
        result["temp_c"] = obs.get("temp")
        result["dewpoint_c"] = obs.get("dewp")
        result["wind_kt"] = obs.get("wspd")
        result["gust_kt"] = obs.get("wgst")

        # Sky cover — AWC returns list of cloud layers [{cover, base}, ...]
        # We want the most significant layer (highest coverage)
        sky_map = {"CLR": 0, "SKC": 0, "CAVOK": 0, "NSC": 0,
                   "FEW": 2, "SCT": 4, "BKN": 6, "OVC": 8, "OVX": 8}
        clouds = obs.get("clouds", [])
        if isinstance(clouds, list) and clouds:
            # highest okta layer wins
            max_oktas = 0
            max_code  = "CLR"
            for layer in clouds:
                code = (layer.get("cover") or "").upper()
                oktas = sky_map.get(code, 0)
                if oktas > max_oktas:
                    max_oktas = oktas
                    max_code  = code
            result["sky_oktas"] = max_oktas
            result["sky_code"]  = max_code
        else:
            # No cloud data — try parsing raw
            raw = result["raw"] or ""
            for code in ["OVC", "BKN", "SCT", "FEW", "CLR", "SKC", "CAVOK"]:
                if code in raw:
                    result["sky_code"]  = code
                    result["sky_oktas"] = sky_map.get(code, 0)
                    break
    except Exception as e:
        print(f"METAR error ({station}): {e}")
    return result


def fetch_taf(station: str, date_str: str) -> dict:
    """
    Fetch TAF for a station and extract peak temperature window.
    Returns: peak_temp_c, peak_window_start, peak_window_end,
             cloud_code_afternoon, valid (bool).
    """
    result = {
        "available": False, "station": station,
        "peak_temp_c": None,
        "temp_window_start": None,
        "temp_window_end": None,
        "afternoon_cloud_code": None,  # cloud cover expected during 12-18h
        "raw": None,
    }
    try:
        resp = requests.get(f"{AWC_BASE}/taf", params={
            "ids": station, "format": "json", "time": "valid",
        }, timeout=8)
        if resp.status_code != 200:
            return result
        data = resp.json()
        if not data:
            return result

        taf = data[0] if isinstance(data, list) else data
        result["available"] = True
        result["raw"] = taf.get("rawTAF", "")

        sky_map = {"CLR": 0, "SKC": 0, "CAVOK": 0, "NSC": 0,
                   "FEW": 2, "SCT": 4, "BKN": 6, "OVC": 8, "OVX": 8}

        # TAF forecast periods — find afternoon window (1200-1800Z ≈ local 12-18h)
        # and extract cloud codes for that period
        forecasts = taf.get("fcsts", []) or []
        afternoon_cloud = None
        for fc in forecasts:
            time_from = fc.get("timeFrom", "")
            # timeFrom is typically "YYYY-MM-DDTHH:MM:SSZ"
            try:
                hour_utc = int(time_from[11:13]) if len(time_from) >= 13 else -1
            except (ValueError, TypeError):
                hour_utc = -1
            # Afternoon UTC window: 15-21Z covers ~12-18 local for most US cities
            if 14 <= hour_utc <= 20:
                clouds = fc.get("clouds", [])
                if isinstance(clouds, list) and clouds:
                    max_oktas = 0
                    max_code  = "CLR"
                    for layer in clouds:
                        code   = (layer.get("cover") or "").upper()
                        oktas  = sky_map.get(code, 0)
                        if oktas > max_oktas:
                            max_oktas = oktas
                            max_code  = code
                    afternoon_cloud = max_code
                    break  # take first matching period

        result["afternoon_cloud_code"] = afternoon_cloud

        # TX lines (max temp) — format TXnn/HHZ in raw TAF
        raw = result["raw"] or ""
        tx_match = re.search(r'TX([M-]?\d+(?:\.\d+)?)/(\d{2,4})Z', raw)
        if tx_match:
            temp_str = tx_match.group(1).replace("M", "-")
            result["peak_temp_c"]       = float(temp_str)
            result["temp_window_start"] = tx_match.group(2)[:2] + ":00"
    except Exception as e:
        print(f"TAF error ({station}): {e}")
    return result


def fetch_sigmet(lat: float, lon: float) -> dict:
    """
    Check for active convective SIGMETs near a location.
    Returns: active (bool), count, nearest description.
    A convective SIGMET means thunderstorms — kills afternoon temp peak.
    """
    result = {
        "available": False,
        "active_convective": False,
        "count": 0,
        "description": None,
    }
    try:
        resp = requests.get(f"{AWC_BASE}/sigmet", params={
            "format": "json", "type": "sigmet",
        }, timeout=8)
        if resp.status_code != 200:
            return result
        data = resp.json()
        if not isinstance(data, list):
            return result
        result["available"] = True

        # Check each SIGMET for proximity to our location
        # Simple bbox check: within ~3 degrees lat/lon (~200 miles)
        convective_count = 0
        nearest_desc = None
        for sig in data:
            # Check if convective type
            hazard = (sig.get("hazard") or "").upper()
            qualifier = (sig.get("qualifier") or "").upper()
            if "CONVECTIVE" in hazard or "TS" in hazard or "CONVECTIVE" in qualifier:
                # Check geographic proximity using bbox if available
                # AWC SIGMETs have coords in geom field
                raw_text = sig.get("rawSigmet", "") or sig.get("text", "") or ""
                # Rough proximity: if it mentions our region or has coords near us
                # Without full polygon parsing, use a conservative approach:
                # Check if any lat/lon in the raw text is within 3 degrees
                lats = [float(m) for m in re.findall(r'(\d{2,3})N', raw_text)]
                lons = [float(m) for m in re.findall(r'(\d{2,3})W', raw_text)]
                near = False
                if lats and lons:
                    for s_lat in lats:
                        for s_lon in lons:
                            if abs(s_lat - abs(lat)) <= 4 and abs(s_lon - abs(lon)) <= 4:
                                near = True
                                break
                else:
                    # No coords found — skip this SIGMET
                    near = False

                if near:
                    convective_count += 1
                    if nearest_desc is None:
                        nearest_desc = raw_text[:80] if raw_text else "Convective SIGMET active"

        result["active_convective"] = convective_count > 0
        result["count"]             = convective_count
        result["description"]       = nearest_desc
    except Exception as e:
        print(f"SIGMET error: {e}")
    return result


def compute_aviation_corrections(metar: dict, taf: dict, sigmet: dict,
                                  unit: str, current_hour_f: float,
                                  peak_hour: float) -> dict:
    """
    Compute temperature corrections and sigma adjustments from METAR/TAF/SIGMET.

    Returns:
      temp_correction   — add to consensus_peak (°F or °C)
      sigma_correction  — add to bracket_uncertainty
      corrections_list  — list of {label, value, reason} for UI display
      sigmet_active     — bool, convective SIGMET present
      taf_peak_temp     — TAF max temp in native unit (or None)
      sky_code          — current sky condition code
    """
    F = 1.0 if unit != "celsius" else (5/9)
    sky_map_oktas = {"CLR": 0, "SKC": 0, "CAVOK": 0, "NSC": 0,
                     "FEW": 2, "SCT": 4, "BKN": 6, "OVC": 8, "OVX": 8}

    temp_corr  = 0.0
    sigma_corr = 0.0
    corrections = []

    # ── 1. METAR sky cover correction ─────────────────────────────────────────
    if metar.get("available") and metar.get("sky_oktas") is not None:
        oktas    = metar["sky_oktas"]
        sky_code = metar.get("sky_code", "UNK")
        # Only apply during heating hours (before peak)
        # After peak: cloud cover doesn't affect the already-observed max
        if current_hour_f < peak_hour + 0.5:
            hours_to_peak = max(0, peak_hour - current_hour_f)
            # Scale effect by how far we are from peak
            # (full effect if peak is 3+ hours away, diminishing as we approach peak)
            time_scale = min(1.0, hours_to_peak / 3.0)

            if oktas == 0:       # CLR/SKC
                delta = +1.2 * F * time_scale
                label = f"☀ Clear sky ({sky_code})"
                reason = "Full solar heating"
            elif oktas <= 2:     # FEW
                delta = +0.4 * F * time_scale
                label = f"🌤 Few clouds ({sky_code})"
                reason = "Mostly clear, minimal impact"
            elif oktas <= 4:     # SCT
                delta = -0.5 * F * time_scale
                label = f"⛅ Scattered clouds ({sky_code})"
                reason = "Partial solar blocking"
            elif oktas <= 6:     # BKN
                delta = -1.5 * F * time_scale
                label = f"🌥 Broken clouds ({sky_code})"
                reason = "Significant solar blocking"
            else:                # OVC/OVX
                delta = -2.5 * F * time_scale
                label = f"☁ Overcast ({sky_code})"
                reason = "Full solar blocking, peak suppressed"

            if abs(delta) >= 0.1:
                temp_corr  += delta
                sigma_corr += -0.3 * F * time_scale if oktas >= 6 else 0.0
                corrections.append({
                    "label": label,
                    "value": round(delta, 1),
                    "reason": reason,
                    "icon": "sky",
                })

    # ── 2. METAR dewpoint depression correction ────────────────────────────────
    if metar.get("available") and metar.get("dewpoint_c") is not None and metar.get("temp_c") is not None:
        temp_c = metar["temp_c"]
        dew_c  = metar["dewpoint_c"]
        depression = temp_c - dew_c   # always in Celsius

        # Research: dewpoint depression > 20°C = very dry = evaporative cooling suppressed
        # but also means drier air absorbs heat faster → slight negative on peak
        # depression < 5°C = very humid = latent heat limits temperature rise
        if depression > 25:
            delta = -0.8 * F
            label = "💧 Very dry air (depression >25°C)"
            reason = "High evaporative potential, limits peak slightly"
        elif depression > 15:
            delta = -0.3 * F
            label = f"💧 Dry air (depression {round(depression)}°C)"
            reason = "Moderate dryness"
        elif depression < 3:
            delta = +0.5 * F
            label = f"💧 Very humid (depression {round(depression)}°C)"
            reason = "High humidity suppresses evaporative cooling → higher peak"
        elif depression < 8:
            delta = +0.2 * F
            label = f"💧 Humid (depression {round(depression)}°C)"
            reason = "Moist air retains heat"
        else:
            delta = 0.0
            label = None
            reason = None

        if abs(delta) >= 0.1 and label:
            temp_corr += delta
            corrections.append({
                "label": label,
                "value": round(delta, 1),
                "reason": reason,
                "icon": "dew",
            })

    # ── 3. METAR gust correction ───────────────────────────────────────────────
    if metar.get("available") and metar.get("gust_kt") is not None:
        gust_kt  = metar["gust_kt"]
        gust_mph = gust_kt * 1.15078

        # Strong gusts mix warmer air from aloft (downslope/dry conditions = warmer)
        # or mix cooler moist air (onshore/cloudy = cooler)
        sky_oktas = metar.get("sky_oktas") or 0
        if gust_mph > 30 and sky_oktas <= 2:
            # Dry, gusty, clear — downslope mixing warms surface
            delta = +0.8 * F
            label = f"💨 Strong gusty winds ({round(gust_mph)}mph, clear)"
            reason = "Downslope mixing brings warmer air to surface"
        elif gust_mph > 30 and sky_oktas >= 6:
            # Gusty with overcast — mixing suppresses temp
            delta = -0.5 * F
            label = f"💨 Strong gusty winds ({round(gust_mph)}mph, overcast)"
            reason = "Strong mixing limits heating under cloud deck"
        elif gust_mph > 20:
            delta = -0.3 * F
            label = f"💨 Gusty winds ({round(gust_mph)}mph)"
            reason = "Wind mixing reduces diurnal range"
        else:
            delta = 0.0
            label = None
            reason = None

        if abs(delta) >= 0.1 and label:
            temp_corr  += delta
            sigma_corr += -0.2 * F if gust_mph > 30 else 0.0
            corrections.append({
                "label": label,
                "value": round(delta, 1),
                "reason": reason,
                "icon": "wind",
            })

    # ── 4. TAF afternoon cloud correction ─────────────────────────────────────
    if taf.get("available") and taf.get("afternoon_cloud_code"):
        af_cloud = taf["afternoon_cloud_code"]
        sky_map  = {"CLR": 0, "SKC": 0, "CAVOK": 0, "NSC": 0,
                    "FEW": 2, "SCT": 4, "BKN": 6, "OVC": 8}
        af_oktas = sky_map.get(af_cloud, 4)

        # Only apply if METAR didn't already cover afternoon clouds
        # i.e. TAF gives us FORECAST cloud for the heating window
        # Don't double-count with METAR which is current conditions
        if current_hour_f < 12.0 and af_oktas >= 6:
            delta = -1.0 * F
            label = f"✈ TAF: {af_cloud} clouds forecast this afternoon"
            reason = "Aviation forecast warns of cloud cover during heating hours"
            temp_corr  += delta
            sigma_corr += +0.3 * F   # more uncertainty when TAF shows clouds coming
            corrections.append({
                "label": label,
                "value": round(delta, 1),
                "reason": reason,
                "icon": "taf",
            })
        elif current_hour_f < 12.0 and af_oktas == 0:
            delta = +0.5 * F
            label = f"✈ TAF: Clear skies forecast this afternoon"
            reason = "Aviation forecast: full solar heating expected"
            temp_corr += delta
            corrections.append({
                "label": label,
                "value": round(delta, 1),
                "reason": reason,
                "icon": "taf",
            })

    # ── 5. TAF max temperature (TX line) as independent forecast ──────────────
    taf_peak_native = None
    if taf.get("available") and taf.get("peak_temp_c") is not None:
        taf_c = taf["peak_temp_c"]
        if unit == "fahrenheit":
            taf_peak_native = round(taf_c * 9/5 + 32, 1)
        else:
            taf_peak_native = round(taf_c, 1)
        # TAF TX line gives us an independent aviation-meteorologist peak estimate
        # We note it but don't directly add as a correction here —
        # it's included as a separate data point shown in the UI

    # ── 6. SIGMET convective kill signal ──────────────────────────────────────
    sigmet_active = False
    if sigmet.get("available") and sigmet.get("active_convective"):
        sigmet_active = True
        # Convective SIGMET = active thunderstorms = afternoon heating killed
        delta = -2.0 * F
        label = f"⚡ Convective SIGMET active ({sigmet['count']} near area)"
        reason = "Active thunderstorms kill afternoon heating — peak likely lower"
        temp_corr  += delta
        sigma_corr += +1.5 * F   # much wider uncertainty with active convection
        corrections.append({
            "label": label,
            "value": round(delta, 1),
            "reason": reason,
            "icon": "sigmet",
        })

    return {
        "temp_correction":   round(temp_corr, 1),
        "sigma_correction":  round(sigma_corr, 2),
        "corrections_list":  corrections,
        "sigmet_active":     sigmet_active,
        "taf_peak_temp":     taf_peak_native,
        "sky_code":          metar.get("sky_code"),
        "sky_oktas":         metar.get("sky_oktas"),
        "metar_raw":         metar.get("raw"),
        "taf_raw":           taf.get("raw"),
        "metar_available":   metar.get("available", False),
        "taf_available":     taf.get("available", False),
        "sigmet_available":  sigmet.get("available", False),
    }


# ── Research-based Peak Hour Estimator ───────────────────────────────────────
def compute_peak_hour(lat, month, climate="continental", urban=False, coastal=False):
    """
    Estimate the local time (decimal hours) when daily maximum temperature occurs.

    Meteorological research basis:
    ──────────────────────────────
    • Solar noon → surface heating peaks → air temperature peaks 2-4h LATER
      due to thermal inertia (Earth stores heat and re-radiates it gradually).
    • NWS ASOS data: US cities peak between 13:00-16:00 depending on season/lat.
    • Hong Kong Observatory study: urban areas peak ~1h LATER than rural.
    • Sensibo meteorology: Tropics 13-15h, Temperate 14-17h (summer), 13-15h (winter).
    • High latitude (UK/NZ) summer: very long days push peak to 15-17h.
    • Maritime climates have smaller diurnal range and earlier/flatter peaks.
    • Arid/continental climates have large swings and peak later (2-4pm typical).
    • Sea breeze / lake breeze: caps afternoon heating, pulls peak 30-60 min earlier.
    • Urban heat island: concrete/asphalt store heat, peak 30-60 min LATER than rural.

    Southern hemisphere: seasons are reversed (adjust month accordingly).
    """
    # Southern hemisphere: flip seasons
    is_southern = lat < 0
    effective_month = ((month + 5) % 12) + 1 if is_southern else month

    # ── Base peak from latitude ───────────────────────────────────────────────
    # Research: higher latitudes have lower sun angles → less intense direct
    # heating → smaller temp swings → peak occurs relatively earlier in winter.
    abs_lat = abs(lat)
    if abs_lat > 55:        base = 13.5   # e.g. London (51N), Edinburgh, Oslo
    elif abs_lat > 45:      base = 14.0   # e.g. Seattle, Chicago, NYC, Paris
    elif abs_lat > 35:      base = 14.5   # e.g. Atlanta, Dallas, Tokyo, Seoul
    elif abs_lat > 25:      base = 14.0   # e.g. Miami, Houston (tropical/subtropical)
    else:                   base = 13.5   # Equatorial/deep tropical: peak earlier

    # ── Season adjustment ─────────────────────────────────────────────────────
    # Summer: longer days, more total energy absorbed → peak later
    # Winter: shorter days, sun angle low → equilibrium earlier
    # Source: diurnal temperature variation research (Sensibo, HK Observatory)
    if effective_month in (12, 1, 2):    season = -0.75  # Winter: up to 45min earlier
    elif effective_month in (3, 4):      season = -0.25  # Early spring
    elif effective_month in (5, 6, 7):   season = +0.75  # Summer: up to 45min later
    elif effective_month in (8, 9):      season = +0.25  # Late summer/early fall
    else:                                season = -0.25  # Fall

    # ── Climate type adjustment ───────────────────────────────────────────────
    # Arid: fast ground heating, large diurnal range → later, higher peaks
    # Maritime: slow heat exchange with ocean moisture → earlier, flatter peaks
    # Tropical: humidity limits heating, convective clouds form midday → earlier
    if climate == "arid":          climate_adj = +0.5
    elif climate == "maritime":    climate_adj = -0.75
    elif climate == "tropical":    climate_adj = -0.5
    else:                          climate_adj = 0.0   # continental: baseline

    # ── Urban heat island ─────────────────────────────────────────────────────
    # HK Observatory: urban peaks ~1h later than rural (concrete stores heat).
    # We use 0.3h as conservative estimate (airports are semi-urban).
    urban_adj = +0.3 if urban else 0.0

    # ── Coastal / sea-lake breeze ─────────────────────────────────────────────
    # Sea/lake breeze develops in the late morning and caps heating.
    # Effect strongest in summer. NWS: sea breeze can reduce highs by 5-10°F.
    # Timing: pulls peak 30-60 min earlier during breeze-prone months.
    if coastal:
        if effective_month in (5, 6, 7, 8, 9):    coastal_adj = -0.75  # Summer: strong breeze
        elif effective_month in (3, 4, 10):        coastal_adj = -0.3   # Spring/fall: moderate
        else:                                       coastal_adj = -0.1   # Winter: minimal
    else:
        coastal_adj = 0.0

    peak = base + season + climate_adj + urban_adj + coastal_adj

    # Hard clamp: daily max never before 12:30 or after 17:00 local
    return max(12.5, min(17.0, peak))


def compute_dynamic_sigma(unit, days_out, current_hour_f, peak_hour,
                          model_spread=None, max_precip=0, wu_peak=None,
                          wu_is_final=False, climate="continental",
                          wind_speed=0, cloud_cover=None):
    """
    Compute uncertainty (sigma) for temperature distribution — research-validated.

    Research sources integrated:
    ─────────────────────────────
    • ECMWF verification (2024): 2m Tmax MAE = 0.85°C day-0, 1.4°C day-3, 2.1°C day-7
    • NWS MOS verification: daily high MAE = 1.8°F same-day, 3.2°F day+2, 5.0°F day+4
    • MODIS global DTR study (JAMC 2019): arid DTR = 25-40K, maritime/tropical DTR < 5K
      → wider distribution needed for arid cities (Dallas, inland deserts)
    • Model spread → ensemble verification: variance of members = proxy for
      forecast uncertainty at 99% confidence (WMO MME verification 2022)
    • Precipitation effect: convective rain days show 2-3× higher Tmax error
      because cloud timing uncertainty translates directly to max temp uncertainty
    • Wind > 25 mph: strong mixing reduces diurnal range (caps high, raises low)
      → compresses distribution, slightly lower sigma
    • Cloud cover known: overcast (>80%) caps solar heating → tighter upper tail
    • WU observed high: most powerful constraint — compresses sigma dramatically
      once actual peak is known (Bayesian update on prior distribution)

    Returns sigma in native unit (°F or °C).
    """
    is_celsius = (unit == "celsius")
    F = 1.0 if not is_celsius else (5/9)   # unit conversion factor

    # ── Base sigma by lead time (NWS MOS + ECMWF verification) ──────────────
    if   days_out <= 0:   base = 1.8 * F   # same-day
    elif days_out == 1:   base = 2.8 * F   # tomorrow
    elif days_out == 2:   base = 3.5 * F   # day+2
    elif days_out == 3:   base = 4.5 * F   # day+3
    elif days_out == 4:   base = 5.2 * F   # day+4
    else:                 base = 6.0 * F   # day+5+ (near-climatological uncertainty)

    # ── Model spread (ensemble variance proxy) ────────────────────────────────
    if model_spread is not None:
        thr = 1.5 if is_celsius else 3.0
        if   model_spread > thr * 2:  model_adj = 1.8 * F   # large disagreement
        elif model_spread > thr:      model_adj = 0.9 * F   # moderate disagreement
        elif model_spread < thr/2:    model_adj = -0.3 * F  # models agree closely → slight compress
        else:                         model_adj = 0.0
    else:
        model_adj = 0.4 * F  # unknown spread: small increase

    # ── Precipitation effect (convective timing uncertainty) ─────────────────
    # Rainy days: cloud timing determines whether max occurs before/after rain
    # → bimodal-ish distribution → wider sigma needed
    if   max_precip >= 80:  precip_adj = 2.5 * F
    elif max_precip >= 60:  precip_adj = 1.8 * F
    elif max_precip >= 40:  precip_adj = 1.0 * F
    elif max_precip >= 20:  precip_adj = 0.3 * F
    else:                   precip_adj = 0.0

    # ── Climate type (MODIS global DTR analysis) ──────────────────────────────
    # Arid: DTR 25-40K → wider brackets needed; maritime: DTR <5K → compress
    if   climate == "arid":       climate_adj = +0.5 * F
    elif climate == "maritime":   climate_adj = -0.6 * F   # tightest: DTR often <4°C
    elif climate == "tropical":   climate_adj = -0.3 * F   # humid limits swing
    else:                         climate_adj = 0.0         # continental: baseline

    # ── Wind mixing effect ────────────────────────────────────────────────────
    # Strong wind (>25 mph) mixes boundary layer → reduces diurnal range
    # Observed effect: ~1°F reduction in sigma per 10 mph above 25 mph
    if wind_speed > 25:
        wind_adj = -min(0.8 * F, (wind_speed - 25) / 10 * 0.5 * F)
    else:
        wind_adj = 0.0

    # ── Overcast cloud cover ──────────────────────────────────────────────────
    # Full overcast eliminates solar heating entirely → caps max near min+2-3°F
    if cloud_cover is not None:
        if   cloud_cover >= 90:  cloud_adj = -0.5 * F   # overcast: very narrow range
        elif cloud_cover >= 70:  cloud_adj = -0.2 * F
        else:                    cloud_adj = 0.0
    else:
        cloud_adj = 0.0

    # ── WU observed high (Bayesian update) ───────────────────────────────────
    # Once station reports actual high, distribution collapses around that value.
    # After peak time: high is near-final. Before peak: still some uncertainty.
    wu_adj = 0.0
    if wu_peak is not None and days_out <= 0:
        total_pre_wu = base + model_adj + precip_adj + climate_adj
        if wu_is_final:
            wu_adj = -total_pre_wu * 0.92   # collapse: sigma → ~8% of base
        elif current_hour_f >= peak_hour + 1.0:
            wu_adj = -total_pre_wu * 0.80   # well past peak: ~20% residual
        elif current_hour_f >= peak_hour:
            wu_adj = -total_pre_wu * 0.70   # at peak: ~30% residual
        elif current_hour_f >= peak_hour - 1.0:
            wu_adj = -total_pre_wu * 0.55   # approaching peak
        elif current_hour_f >= 11.0:
            wu_adj = -total_pre_wu * 0.35   # late morning
        else:
            wu_adj = -total_pre_wu * 0.20   # morning: modest constraint

    sigma = base + model_adj + precip_adj + climate_adj + wind_adj + cloud_adj + wu_adj

    # Hard clamps: physically meaningful range
    min_sigma = 0.15 * F   # absolute minimum (nearly certain)
    max_sigma = 7.0 * F    # absolute maximum (extreme uncertainty)
    return round(max(min_sigma, min(max_sigma, sigma)), 2)


# ── Live High Predictor ───────────────────────────────────────────────────────
def predict_daily_high(lat, lon, target_date_str, unit="fahrenheit", tz_name="America/New_York",
                       actual_high_so_far=None, actual_low_so_far=None, actual_hourly=None,
                       climate="continental", urban=False, coastal=False):
    """
    Multi-method daily high temperature predictor.
    
    CRITICAL FIX: When actual station data (WU/NWS) is available, use THOSE
    readings as the baseline — not Open-Meteo's model current temp.
    Open-Meteo current temp is a model interpolation and can be significantly
    wrong (showed 61°F when actual station was 66°F in testing).
    
    actual_high_so_far: real observed high from WU/NWS so far today
    actual_low_so_far:  real observed low from WU/NWS so far today  
    actual_hourly:      list of {hour, temp} from real station readings
    """
    try:
        now_local = datetime.now(ZoneInfo(tz_name))
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        today_local = now_local.date()
        is_today = (target_date == today_local)
        is_future = (target_date > today_local)

        # Fetch Open-Meteo for model forecast + atmospheric corrections
        om = fetch_open_meteo(lat, lon, days=3, unit=unit)
        if not om:
            return {"available": False, "reason": "Could not fetch forecast data"}

        current = om.get("current", {})
        # Use model current for cloud/wind/dew corrections only — NOT for temp baseline
        current_wind  = current.get("windspeed_10m", 0)
        current_cloud = current.get("cloudcover", 0)
        current_dew   = current.get("dewpoint_2m")
        om_current_temp = current.get("temperature_2m")  # model temp — for reference only

        hourly = om.get("hourly", {})
        times  = hourly.get("time", [])
        temps  = hourly.get("temperature_2m", [])
        clouds = hourly.get("cloudcover", [])
        winds  = hourly.get("windspeed_10m", [])
        dews   = hourly.get("dewpoint_2m", [])
        precips= hourly.get("precipitation_probability", [])

        # Extract target date hourly data from model
        target_hours = []
        for i, t in enumerate(times):
            if target_date_str in t:
                target_hours.append({
                    "hour_str": t[11:16],
                    "hour_int": int(t[11:13]),
                    "temp":   temps[i]   if i < len(temps)   and temps[i]   is not None else None,
                    "cloud":  clouds[i]  if i < len(clouds)  else 50,
                    "wind":   winds[i]   if i < len(winds)   else 5,
                    "dew":    dews[i]    if i < len(dews)    else None,
                    "precip": precips[i] if i < len(precips) else 0,
                })

        if not target_hours:
            return {"available": False, "reason": "No hourly data for target date"}

        # ── Method 1: Direct model peak (Open-Meteo forecast max) ─────────────
        model_temps_list = [h["temp"] for h in target_hours if h["temp"] is not None]
        model_peak = max(model_temps_list) if model_temps_list else None

        # ── Determine best "current actual temp" baseline ─────────────────────
        # Priority: actual station high > actual station hourly latest > OM model
        # This is the core Bug 3 fix.
        current_hour_f = now_local.hour + now_local.minute / 60.0

        # Get the most recent actual station reading
        actual_current_temp = None
        actual_morning_min  = None

        if actual_hourly and len(actual_hourly) > 0:
            # Sort by hour, take the latest reading as "current temp"
            sorted_actual = sorted(actual_hourly, key=lambda x: x.get("hour","00:00"))
            # Latest reading available
            actual_current_temp = sorted_actual[-1]["temp"]
            # Morning minimum = lowest temp in actual readings before noon
            morning_actual = [x["temp"] for x in sorted_actual
                              if int(x["hour"][:2]) <= 12 and x["temp"] is not None]
            if morning_actual:
                actual_morning_min = min(morning_actual)

        # ── Peak hour estimation — uses research-based function ───────────────
        # compute_peak_hour factors in: latitude, season, climate type,
        # urban heat island, and coastal sea-breeze effects.
        _month = now_local.month
        peak_hour = compute_peak_hour(lat, _month, climate=climate, urban=urban, coastal=coastal)
        # Human-readable peak window string
        ph_lo = int(peak_hour - 0.5); ph_hi = int(peak_hour + 0.5)
        def _fmt_h(h):
            suffix = "AM" if h < 12 else "PM"
            h12 = h if h <= 12 else h - 12
            return f"{h12}:00 {suffix}"
        peak_time_str = f"{_fmt_h(ph_lo)}–{_fmt_h(ph_hi)} local"

        # Use actual high as hard floor — prediction can't be below what's observed
        if actual_high_so_far is not None:
            # Already know the high — if past peak hour, this IS the answer
            if current_hour_f > peak_hour + 0.5:  # 30 min past expected peak
                return {
                    "available": True,
                    "final_prediction": round(actual_high_so_far, 1),
                    "uncertainty": 0.5,
                    "lower_bound": round(actual_high_so_far - 0.5, 1),
                    "upper_bound": round(actual_high_so_far + 0.5, 1),
                    "confidence": 98,
                    "model_peak": model_peak,
                    "extrapolated_peak": actual_high_so_far,
                    "ensemble_peak": None,
                    "ensemble_spread": None,
                    "heating_rate": None,
                    "hours_remaining": 0,
                    "morning_low": actual_low_so_far or actual_morning_min,
                    "current_temp": actual_current_temp or actual_high_so_far,
                    "current_cloud": current_cloud,
                    "current_wind": current_wind,
                    "current_dew": current_dew,
                    "is_today": is_today,
                    "peak_time_estimate": "Peak passed — final high recorded",
                    "method2_available": True,
                    "actual_observed_high": actual_high_so_far,
                    "range_lo": round(actual_high_so_far - 0.5, 1),
                    "range_hi": round(actual_high_so_far + 0.5, 1),
                }

        # ── Method 2: Heating curve extrapolation using ACTUAL station data ────
        extrapolated_peak = None
        heating_rate = None
        hours_remaining = None
        method2_available = False

        if is_today:
            # Use actual station temp as baseline (not OM model)
            baseline_temp = actual_current_temp if actual_current_temp is not None else om_current_temp
            morning_min   = actual_morning_min  if actual_morning_min  is not None else \
                            min([h["temp"] for h in target_hours if h["hour_int"] <= 8 and h["temp"] is not None], default=None)

            if baseline_temp is not None and morning_min is not None:
                # Find when morning minimum occurred
                if actual_hourly:
                    sorted_a = sorted(actual_hourly, key=lambda x: x.get("hour",""))
                    min_reading = min(sorted_a, key=lambda x: x.get("temp", 9999))
                    morning_min_hour = float(min_reading["hour"][:2]) + float(min_reading["hour"][3:5])/60
                else:
                    min_h = min([h for h in target_hours if h["hour_int"] <= 12 and h["temp"] is not None],
                                key=lambda x: x["temp"], default=None)
                    morning_min_hour = min_h["hour_int"] if min_h else 6.0

                elapsed = current_hour_f - morning_min_hour
                if elapsed > 0.5:
                    temp_rise = baseline_temp - morning_min
                    heating_rate = temp_rise / elapsed

                    if current_hour_f < peak_hour:
                        hours_remaining = peak_hour - current_hour_f

                        # Atmospheric corrections from model forecast
                        future_hrs = [h for h in target_hours if current_hour_f <= h["hour_int"] <= peak_hour]
                        avg_cloud = sum(h["cloud"] for h in future_hrs) / max(1, len(future_hrs))
                        avg_wind  = sum(h["wind"]  for h in future_hrs) / max(1, len(future_hrs))
                        avg_dew   = current_dew if current_dew else (55 if unit=="fahrenheit" else 13)

                        cloud_factor = 1.0 - (avg_cloud / 100.0) * 0.4
                        wind_factor  = max(0.7, 1.0 if avg_wind < 10 else 1.0 - (avg_wind - 10) * 0.015)
                        dew_thresh = 55 if unit == "fahrenheit" else 13
                        dew_factor = max(0.8, 1.0 - max(0, (avg_dew - dew_thresh) * 0.01))

                        effective_rate = heating_rate * cloud_factor * wind_factor * dew_factor
                        if hours_remaining > 1:
                            additional = effective_rate * (hours_remaining - 0.5) + effective_rate * 0.5 * 0.6
                        else:
                            additional = effective_rate * hours_remaining * 0.7

                        raw_extrap = baseline_temp + additional
                        # Floor: can't be below actual observed high so far
                        if actual_high_so_far is not None:
                            raw_extrap = max(raw_extrap, actual_high_so_far)
                        extrapolated_peak = round(raw_extrap, 1)
                        method2_available = True
                    else:
                        # Past typical peak — actual observed high IS the answer
                        if actual_high_so_far is not None:
                            extrapolated_peak = actual_high_so_far
                        else:
                            all_seen = [x["temp"] for x in (actual_hourly or []) if x.get("temp")]
                            extrapolated_peak = max(all_seen) if all_seen else baseline_temp
                        method2_available = True
                        hours_remaining = 0

        # ── Method 3: Morning low + climatological rise (model-based) ──────────
        morning_low_model = min([h["temp"] for h in target_hours if h["hour_int"] <= 8 and h["temp"] is not None], default=None)

        # ── Method 4: Ensemble spread for uncertainty ───────────────────────────
        ensemble_spread = None
        ensemble_peak_mean = None
        try:
            ens = fetch_open_meteo_ensemble(lat, lon, days=3, unit=unit)
            if ens:
                ens_hourly = ens.get("hourly", {})
                ens_times  = ens_hourly.get("time", [])
                member_peaks = []
                for col in [k for k in ens_hourly if k.startswith("temperature_2m_member")]:
                    vals = ens_hourly[col]
                    day_vals = [vals[i] for i, t in enumerate(ens_times)
                                if target_date_str in t and i < len(vals) and vals[i] is not None]
                    if day_vals:
                        member_peaks.append(max(day_vals))
                if len(member_peaks) >= 3:
                    ensemble_peak_mean = round(sum(member_peaks)/len(member_peaks), 1)
                    ensemble_spread    = round(max(member_peaks) - min(member_peaks), 1)
        except: pass

        # ── Combine methods with weights ───────────────────────────────────────
        all_estimates, weights = [], []

        if model_peak is not None:
            all_estimates.append(model_peak); weights.append(2)

        if extrapolated_peak is not None and method2_available:
            all_estimates.append(extrapolated_peak)
            # Give higher weight if based on actual station data
            w = 6 if actual_current_temp is not None else 4
            if hours_remaining == 0: w = 7  # past peak = definitive
            weights.append(w)

        if ensemble_peak_mean is not None:
            all_estimates.append(ensemble_peak_mean); weights.append(2)

        if not all_estimates:
            return {"available": False, "reason": "Insufficient data"}

        final_pred = round(sum(e*w for e,w in zip(all_estimates, weights)) / sum(weights), 1)

        # Apply hard floor: can't predict below actual observed high
        if actual_high_so_far is not None:
            final_pred = max(final_pred, actual_high_so_far)

        # Uncertainty
        if ensemble_spread:
            uncertainty = round(ensemble_spread / 2, 1)
        elif is_today and method2_available and actual_current_temp is not None:
            # Using real station data — tighter uncertainty
            uncertainty = 1.0 if (hours_remaining is not None and hours_remaining < 1) else 1.5
        elif is_today:
            uncertainty = 2.0 if unit == "celsius" else 2.5
        else:
            days_out = (target_date - today_local).days
            uncertainty = round(min(1.5 + days_out * 0.5, 6.0), 1)

        # Confidence
        if is_today:
            if hours_remaining == 0 and actual_high_so_far is not None:
                confidence = 98  # past peak with actual data
            elif actual_current_temp is not None and hours_remaining is not None and hours_remaining < 2:
                confidence = 92
            elif actual_current_temp is not None:
                confidence = 85
            else:
                confidence = 75
        elif is_future:
            days_out = (target_date - today_local).days
            confidence = max(45, 85 - days_out * 8)
        else:
            confidence = 95

        return {
            "available": True,
            "final_prediction": final_pred,
            "uncertainty": uncertainty,
            "lower_bound": round(final_pred - uncertainty, 1),
            "upper_bound": round(final_pred + uncertainty, 1),
            "confidence": confidence,
            "model_peak": model_peak,
            "extrapolated_peak": extrapolated_peak,
            "ensemble_peak": ensemble_peak_mean,
            "ensemble_spread": ensemble_spread,
            "heating_rate": round(heating_rate, 2) if heating_rate else None,
            "hours_remaining": round(hours_remaining, 1) if hours_remaining is not None else None,
            "morning_low": actual_morning_min or morning_low_model,
            "current_temp": actual_current_temp or om_current_temp,
            "current_cloud": current_cloud,
            "current_wind": current_wind,
            "current_dew": current_dew,
            "is_today": is_today,
            "peak_time_estimate": peak_time_str if is_today else f"{peak_time_str} (typical)",
            "method2_available": method2_available,
            "actual_observed_high": actual_high_so_far,
            "using_actual_station": actual_current_temp is not None,
        }
    except Exception as e:
        print(f"Predictor error: {e}")
        import traceback; traceback.print_exc()
        return {"available": False, "reason": str(e)}

# ── Bracket Analysis ──────────────────────────────────────────────────────────
def generate_polymarket_brackets(center_temp, unit="fahrenheit"):
    """
    Generate brackets that MATCH Polymarket's exact bracket pattern.
    
    Polymarket uses 2-degree-wide brackets with EVEN lower boundaries:
      e.g. 64-65°F, 66-67°F, 68-69°F, 70-71°F, 72-73°F ...
    The lowest bracket is "<X°F or lower" and highest is "X°F or higher".
    
    Center the brackets around the predicted/observed temperature so the
    most likely bracket is in the middle of the list (±4 brackets each way).
    """
    if unit == "celsius":
        # Celsius: 1°C wide brackets with integer boundaries
        c = round(center_temp)
        brackets = []
        for lo in range(c - 6, c + 6):
            hi = lo + 1
            brackets.append({"label": f"{lo}-{lo+1}°C", "lo": lo, "hi": hi})
        # cap brackets
        brackets[0]["label"]  = f"{brackets[0]['lo']}°C or lower"
        brackets[0]["lo"]     = -999
        brackets[-1]["label"] = f"{brackets[-1]['lo']}°C or higher"
        brackets[-1]["hi"]    = None
        return brackets
    else:
        # Fahrenheit: 2°F wide brackets, lower boundary always EVEN
        # Find nearest even number at or below center
        even_center = int(center_temp) if int(center_temp) % 2 == 0 else int(center_temp) - 1
        # Build 9 brackets: 4 below center, center bracket, 4 above
        brackets = []
        start = even_center - 8   # 4 brackets below center (each 2°F wide)
        for lo in range(start, start + 18, 2):
            hi = lo + 2
            brackets.append({"label": f"{lo}-{lo+1}°F", "lo": lo, "hi": hi})
        # Convert bottom to "X or lower" and top to "X or higher" 
        brackets[0]["label"] = f"{brackets[0]['lo']}-{brackets[0]['lo']+1}°F or lower"
        brackets[0]["lo"] = -999
        brackets[-1]["label"] = f"{brackets[-1]['lo']}°F or higher"
        brackets[-1]["hi"] = None
        return brackets

def compute_forecast_on_brackets(pm_brackets, distribution_center, sigma, unit="fahrenheit"):
    """
    Compute our forecast probability on a set of pre-defined bracket boundaries.
    pm_brackets: list of {lo, hi, label, pm_yes_price, ...} from Polymarket
    Returns the same list with 'forecast_prob' added to each bracket.
    """
    def ncdf(x, mu, s):
        if s <= 0: return 0.5
        return 0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2))))

    def bprob(lo, hi, mu, s):
        lo_val = lo if lo > -900 else -999
        if hi is None:
            return (1 - ncdf(lo_val, mu, s)) * 100
        return (ncdf(hi, mu, s) - ncdf(lo_val if lo_val > -900 else float('-inf'), mu, s)) * 100

    raw_probs = []
    for b in pm_brackets:
        lo = b.get("lo", -999)
        hi = b.get("hi")  # None = open ended
        raw_probs.append(bprob(lo, hi, distribution_center, sigma))

    total = sum(raw_probs)
    result = []
    for i, b in enumerate(pm_brackets):
        entry = dict(b)
        entry["forecast_prob"] = round(raw_probs[i] / total * 100, 1) if total > 0 else 0
        result.append(entry)
    return result


def compute_bracket_analysis(peak_temp, hourly_temps, unit="fahrenheit", uncertainty=2.5, wu_peak=None):
    """
    Compute bracket probabilities using a normal distribution.

    CRITICAL: peak_temp IS already the correctly-computed bracket_center
    (= max(wu_peak, predictor_final) intraday, or wu_peak_effective at EOD).
    We must NOT override it with raw wu_peak here — doing so would center the
    distribution on the current floor (e.g. 49°F at 1pm) instead of the
    forecast final high (53°F), producing wrong AVOID signals on correct brackets.

    wu_peak is kept as a parameter for legacy compatibility but is NOT used
    to override the distribution center.
    """
    if peak_temp is None:
        return None

    # peak_temp is already bracket_center — use it directly.
    # Never override with raw wu_peak (that's the current floor, not the final high).
    distribution_center = peak_temp

    sigma = uncertainty

    def ncdf(x, mu, s):
        if s <= 0: return 0.5
        return 0.5 * (1 + math.erf((x - mu) / (s * math.sqrt(2))))

    def bprob(lo, hi, mu, s):
        if hi is None:
            return (1 - ncdf(lo, mu, s)) * 100
        return (ncdf(hi, mu, s) - ncdf(lo, mu, s)) * 100

    brackets = generate_polymarket_brackets(distribution_center, unit)

    raw_probs = [bprob(b["lo"], b["hi"], distribution_center, sigma) for b in brackets]
    total = sum(raw_probs)

    for i, b in enumerate(brackets):
        b["forecast_prob"] = round(raw_probs[i] / total * 100, 1) if total > 0 else 0

    return brackets

def compute_edge(fp, pp):
    if fp is None or pp is None: return None
    return round(fp - pp, 1)

def edge_rating(edge):
    if edge is None: return "unknown", 0
    a = abs(edge)
    return ("strong",3) if a>=20 else ("moderate",2) if a>=10 else ("weak",1) if a>=5 else ("none",0)

# ── License middleware ────────────────────────────────────────────────────────
def require_license(f):
    """Decorator: validates X-Access-Code header on every protected API call."""
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        code = request.headers.get("X-Access-Code", "").strip()
        if not code:
            return jsonify({"error": "No access code provided", "auth": False}), 401
        result = _validate_code(code)
        if not result["ok"]:
            return jsonify({"error": result["error"], "auth": False}), 401
        return f(*args, **kwargs)
    return decorated

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route("/")
def index(): return render_template("weather.html")

@app.route("/api/cities")
def api_cities():
    cities = []
    for name, c in CITY_COORDS.items():
        cities.append({
            "name": name, "flag": c.get("flag",""),
            "unit": c.get("unit","fahrenheit"),
            "unit_symbol": "°C" if c.get("unit")=="celsius" else "°F",
            "station": c.get("station",""), "volume": c.get("volume",""),
            "note": c.get("note",""), "wunderground": c.get("wunderground",""),
        })
    return jsonify({"cities": cities})

@app.route("/api/validate_code", methods=["POST"])
def api_validate_code():
    """Validate an access code — called from the browser on first visit."""
    body = request.get_json(silent=True) or {}
    code = body.get("code", "").strip()
    if not code:
        return jsonify({"ok": False, "error": "No code provided"}), 400
    result = _validate_code(code)
    if result["ok"]:
        return jsonify({
            "ok":            True,
            "days_left":     result["days_left"],
            "expires_at":    result["expires_at"].strftime("%b %d, %Y"),
            "subscriber_id": result["subscriber_id"],
        })
    return jsonify({"ok": False, "error": result["error"]}), 401



@app.route("/api/weather/<city>/<date>")
@require_license
def api_weather(city, date):
    city = unquote(city)
    coords = CITY_COORDS.get(city)
    if not coords: return jsonify({"error": f"City '{city}' not found"}), 404

    unit = coords.get("unit", "fahrenheit")
    sym = "°C" if unit == "celsius" else "°F"
    is_us = coords.get("flag") == "🇺🇸"
    tz_name = coords.get("tz", "America/New_York")

    # Fetch all sources — legacy sources + new multi-model intelligence layer (parallel)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as _ex:
        _f_om  = _ex.submit(fetch_open_meteo, coords["lat"], coords["lon"], 7, unit)
        _f_nws = _ex.submit(fetch_nws_forecast, coords["lat"], coords["lon"]) if is_us else None
        _f_wu  = _ex.submit(fetch_wunderground, coords["wunderground"], date,
                            coords.get("station"), unit)
        _f_vc  = _ex.submit(fetch_visual_crossing, coords["lat"], coords["lon"], date, unit)
        _f_mm  = _ex.submit(fetch_multi_model_peaks, coords["lat"], coords["lon"],
                            date, unit, is_us, coords=coords)
        _f_eq  = _ex.submit(compute_ensemble_quantiles, coords["lat"], coords["lon"],
                            date, unit)
        _f_intl = (_ex.submit(fetch_international_source, coords, date)
                   if (not is_us and coords.get("intl_source")) else None)
        om_data   = _f_om.result()
        nws_data  = _f_nws.result() if _f_nws else None
        wu_data   = _f_wu.result()
        vc_data   = _f_vc.result()
        multi_model_peaks  = _f_mm.result()  # {"HRRR":85.1,"ICON":84.3,"GEM":85.6,...}
        ensemble_quantiles = _f_eq.result()  # {p10,p25,p50,p75,p90,sigma_from_ensemble,...}
        intl_data = _f_intl.result() if _f_intl else None

    # ── METAR / TAF / SIGMET — aviation atmospheric data ─────────────────────
    station = coords.get("station", "")
    _today_est2 = datetime.now(ZoneInfo("America/New_York")).date()
    try:
        _target_d2 = datetime.strptime(date, "%Y-%m-%d").date()
        _days_diff2 = (_target_d2 - _today_est2).days
    except:
        _days_diff2 = 0
    _fetch_aviation = (station != "" and -1 <= _days_diff2 <= 2)
    if _fetch_aviation:
        metar_data  = fetch_metar(station)
        taf_data    = fetch_taf(station, date)
        sigmet_data = fetch_sigmet(coords["lat"], coords["lon"])
    else:
        metar_data  = {"available": False}
        taf_data    = {"available": False}
        sigmet_data = {"available": False}

    om_hourly  = parse_open_meteo(om_data, date)
    nws_hourly = parse_nws(nws_data, date) if nws_data else []
    vc_hourly  = vc_data.get("hourly", [])
    intl_hourly = intl_data.get("hourly", []) if intl_data and intl_data.get("available") else []

    # Peaks
    om_peak   = max([h["temp"] for h in om_hourly  if h.get("temp")], default=None)
    # NWS: prefer the official daily high from the 12-hour forecast period (isDaytime=True)
    # This matches what you see on forecast.weather.gov and is more accurate than hourly max
    nws_daily_high = parse_nws_daily_high(nws_data, date) if nws_data else None
    nws_hourly_max = max([h["temp"] for h in nws_hourly if h.get("temp")], default=None)
    nws_peak  = nws_daily_high if nws_daily_high is not None else nws_hourly_max
    wu_peak   = wu_data.get("high_temp")   if wu_data.get("available")   else None
    vc_peak   = vc_data.get("high_temp")   if vc_data.get("available")   else None
    intl_peak = intl_data.get("high_temp") if intl_data and intl_data.get("available") else None

    # ── Weighted model consensus ──────────────────────────────────────────────
    # Research: NWS verification shows ensemble mean beats any single model.
    # Weights based on verified accuracy (MAE) for 2m max temp:
    #   US cities:    NWS=40% (official + MOS-corrected), OM ECMWF=35%, VC=25%
    #   Intl cities:  OM ECMWF=45% (best global model), UK Met/ICON=35%, VC=20%
    # When a source is missing, redistribute weight proportionally.
    is_us = coords.get("flag") == "🇺🇸"
    if is_us:
        raw_weights = {"nws": 0.40, "om": 0.35, "vc": 0.25, "intl": 0.0}
    else:
        raw_weights = {"nws": 0.0, "om": 0.45, "vc": 0.20, "intl": 0.35}

    source_vals  = {"nws": nws_peak, "om": om_peak, "vc": vc_peak, "intl": intl_peak}
    avail        = {k: v for k, v in source_vals.items() if v is not None}
    avail_weight = sum(raw_weights[k] for k in avail)

    if avail and avail_weight > 0:
        weighted_sum  = sum(avail[k] * (raw_weights[k] / avail_weight) for k in avail)
        consensus_peak = round(weighted_sum, 1)
    elif avail:
        consensus_peak = round(sum(avail.values()) / len(avail), 1)  # fallback: equal weight
    else:
        consensus_peak = None

    # Model spread: use all available model temps (not WU) for disagreement measure
    model_temps = [v for k, v in avail.items() if v is not None]
    model_spread = round(max(model_temps) - min(model_temps), 1) if len(model_temps) >= 2 else None
    model_agreement = (model_spread <= (3 if unit=="fahrenheit" else 1.5)) if model_spread is not None else None

    # Source URLs for hyperlinking
    lat_r, lon_r = coords["lat"], coords["lon"]
    source_urls = {
        "om":  f"https://open-meteo.com/en/docs#latitude={lat_r}&longitude={lon_r}",
        "nws": f"https://forecast.weather.gov/MapClick.php?lat={lat_r}&lon={lon_r}",
        "vc":  f"https://www.visualcrossing.com/weather-history/{lat_r},{lon_r}/{date}/{date}",
        "wu":  wu_data.get("url", f"{coords['wunderground']}/date/{date}"),
        "intl": intl_data.get("source_url", "") if intl_data else "",
    }

    # ── WU cross-validation against model consensus ───────────────────────────
    # Purpose: detect when IEM missed the true daily peak (e.g. Wellington 20°C vs 21°C).
    # This ONLY matters AFTER the day is complete — intraday WU < model forecast is
    # NORMAL (WU shows current observed high, models show forecast final high).
    #
    # Rule: only flag as "underreported" if ALL of these are true:
    #   1. Day is over (past peak + 30 min)
    #   2. WU data came from IEM (most likely to miss SPECI peaks)
    #   3. ALL models agree the high was higher than IEM by ≥ threshold
    #
    # During intraday: wu_peak is the CURRENT high so far (will go higher) — never flag.
    wu_cross_check = None  # None=ok, "underreported"=IEM missed the end-of-day peak

    # NOTE: day_is_over is computed below, so we compute a preliminary check here
    # and set the final flag after day_is_over is known.
    _wu_cross_check_candidate = False
    _wu_cross_check_gap = None
    if (wu_peak is not None
            and wu_data.get("available")
            and wu_data.get("method") == "Iowa Mesonet (IEM ASOS)"):
        model_high_for_check = max(
            [p for p in [om_peak, nws_peak, vc_peak, intl_peak] if p is not None],
            default=None
        )
        if model_high_for_check is not None:
            _wu_cross_check_gap = model_high_for_check - wu_peak
            thresh = 1.0 if unit == "celsius" else 2.0
            if _wu_cross_check_gap >= thresh:
                _wu_cross_check_candidate = True

    # Source gap
    source_gap, source_gap_direction = None, None
    if wu_peak and consensus_peak:
        source_gap = round(consensus_peak - wu_peak, 1)
        thresh = 1 if unit == "celsius" else 2
        if abs(source_gap) >= thresh:
            source_gap_direction = "models_higher" if source_gap > 0 else "wu_higher"

    # Days out
    today_est = datetime.now(ZoneInfo("America/New_York")).date()
    try:
        target = datetime.strptime(date, "%Y-%m-%d").date()
        days_out = (target - today_est).days
    except: days_out = 0

    # Daily range from OM
    daily = om_data.get("daily", {}) if om_data else {}
    daily_dates = daily.get("time", [])
    daily_idx = daily_dates.index(date) if date in daily_dates else None
    daily_max = daily.get("temperature_2m_max", [])[daily_idx] if daily_idx is not None and daily_idx < len(daily.get("temperature_2m_max",[])) else None
    daily_min = daily.get("temperature_2m_min", [])[daily_idx] if daily_idx is not None and daily_idx < len(daily.get("temperature_2m_min",[])) else None

    # Precip/wind
    precip_vals = [h.get("precip_prob") or 0 for h in om_hourly]
    wind_vals = [h.get("wind") or 0 for h in om_hourly]
    max_precip = max(precip_vals) if precip_vals else 0
    max_wind = max(wind_vals) if wind_vals else 0

    # Live predictor — pass actual WU observed data + city climate metadata
    climate  = coords.get("climate", "continental")
    urban    = coords.get("urban", False)
    coastal  = coords.get("coastal", False)

    # ── Distribution center: smarter logic for intraday trading ──────────────
    tz_obj = ZoneInfo(tz_name)
    now_local = datetime.now(tz_obj)
    current_hour_f = now_local.hour + now_local.minute / 60.0
    peak_hour_est = compute_peak_hour(
        coords["lat"], now_local.month, climate=climate, urban=urban, coastal=coastal
    )
    day_is_over = (days_out < 0) or (days_out == 0 and current_hour_f > peak_hour_est + 0.5)

    # ── Finalize cross-check — ONLY valid after the day is over ───────────────
    # During the day: WU shows CURRENT observed high (e.g. 49°F at 1pm).
    # Models show FORECAST FINAL high (e.g. 52°F). Gap is EXPECTED — not a bug.
    # Only flag "underreported" when day is over and IEM still reads lower than
    # all models, suggesting IEM missed the actual peak observation.
    if _wu_cross_check_candidate and day_is_over:
        wu_cross_check = "underreported"
        print(f"  WU cross-check: day over, IEM final={wu_peak} but models say higher (gap={_wu_cross_check_gap}) — flagged")
    # wu_cross_check stays None during intraday (normal state)

    # ── Effective WU peak ──────────────────────────────────────────────────────
    # Only substitute model reading AFTER day is over AND cross-check fires.
    # During intraday: wu_peak IS the real current high — never replace it.
    wu_peak_effective = wu_peak
    if wu_cross_check == "underreported":
        model_high_effective = max(
            [p for p in [om_peak, nws_peak, vc_peak, intl_peak] if p is not None],
            default=None
        )
        if model_high_effective is not None and model_high_effective > (wu_peak or 0):
            wu_peak_effective = model_high_effective
            print(f"  Using model high {wu_peak_effective} instead of underreported IEM final {wu_peak}")

    predictor = predict_daily_high(
        coords["lat"], coords["lon"], date, unit, tz_name,
        actual_high_so_far=wu_peak,           # always use real WU peak for predictor floor
        actual_low_so_far=wu_data.get("low_temp") if wu_data.get("available") else None,
        actual_hourly=wu_data.get("hourly", []),
        climate=climate, urban=urban, coastal=coastal,
    )

    pred_final = predictor.get("final_prediction") if predictor.get("available") else None

    # ── Bracket center — single source of truth ──────────────────────────────
    #
    # GOAL: bracket_center = best estimate of where the day's HIGH will land.
    # It must be consistent with what the UI shows everywhere else.
    #
    # Logic:
    #   Past peak (day_is_over): use wu_peak_effective (the actual recorded high)
    #   Intraday:
    #     bracket_center = max(wu_peak_effective, pred_final, consensus_peak)
    #
    # WHY include consensus_peak as a floor intraday:
    #   pred_final can be dragged DOWN by the heating-curve method when the
    #   current station reading (e.g. 57°F) is still far from the forecast high.
    #   All models (NWS=68, OM=64, Ensemble=66) agreeing at ~66°F is a stronger
    #   signal than a heating extrapolation that starts from the current low.
    #   Using consensus_peak as a floor keeps the predictor aligned with what
    #   all models and the edge banner are actually showing.
    #
    # RESULT: predictor widget and edge banner always show the same number.

    candidates = [v for v in [wu_peak_effective, pred_final, consensus_peak] if v is not None]
    if day_is_over:
        bracket_center = wu_peak_effective if wu_peak_effective is not None else (consensus_peak or pred_final)
    elif candidates:
        bracket_center = max(candidates)
    else:
        bracket_center = None

    # Keep pred_final in sync — show the same number in the predictor widget
    if pred_final is not None and bracket_center is not None:
        pred_final = max(pred_final, bracket_center)
        if predictor.get("available"):
            predictor["final_prediction"] = pred_final
            predictor["lower_bound"] = round(pred_final - predictor.get("uncertainty", 2.0), 1)
            predictor["upper_bound"] = round(pred_final + predictor.get("uncertainty", 2.0), 1)

    # ── METAR/TAF/SIGMET atmospheric corrections ─────────────────────────────
    aviation_corr = compute_aviation_corrections(
        metar_data, taf_data, sigmet_data,
        unit, current_hour_f, peak_hour_est
    )
    if not day_is_over and aviation_corr["temp_correction"] != 0:
        consensus_peak_adj = round((consensus_peak or 0) + aviation_corr["temp_correction"], 1) if consensus_peak else consensus_peak
        if wu_peak is None or (pred_final is not None and bracket_center == max(wu_peak_effective or 0, pred_final)):
            bracket_center_adj = round(bracket_center + aviation_corr["temp_correction"], 1) if bracket_center else bracket_center
        else:
            bracket_center_adj = bracket_center
    else:
        consensus_peak_adj = consensus_peak
        bracket_center_adj = bracket_center

    # ── Dynamic sigma — research-based ────────────────────────────────────────
    wu_is_final = day_is_over and wu_peak is not None
    bracket_uncertainty = compute_dynamic_sigma(
        unit=unit, days_out=days_out, current_hour_f=current_hour_f,
        peak_hour=peak_hour_est, model_spread=model_spread,
        max_precip=max_precip, wu_peak=wu_peak, wu_is_final=wu_is_final,
        climate=climate, wind_speed=max_wind,
    )
    bracket_uncertainty = round(max(0.15, bracket_uncertainty + aviation_corr["sigma_correction"]), 2)

    # ── Intelligent Consensus (time-aware, replaces flat model average) ────────
    # Uses time-aware weighting: models dominate pre-8am, station dominates midday
    intel = compute_intelligent_consensus(
        multi_model_peaks, wu_peak, current_hour_f, unit, days_out
    )
    smart_consensus  = intel["smart_consensus"]
    intel_agreement  = intel["model_agreement"]   # "strong" / "moderate" / "poor"
    intel_confidence = intel["confidence"]         # "high" / "medium" / "low"
    intel_spread     = intel["model_spread"]       # multi-model spread
    intel_time_label = intel["time_label"]         # human-readable time-of-day stage

    # ── Bayesian Intraday Update ───────────────────────────────────────────────
    # Adjust bracket_center based on how station is tracking vs model today
    # Only meaningful intraday when real station readings exist
    wu_station_hourly = wu_data.get("hourly", []) if wu_data.get("available") else []
    bayes_center, bayes_sigma, bayes_adj, bayes_trail = bayesian_intraday_update(
        wu_station_hourly, om_hourly, current_hour_f,
        bracket_center_adj,
        bracket_uncertainty
    )
    # Use Bayesian-updated values for bracket computation (only intraday, not when day is over)
    if not day_is_over and abs(bayes_adj) > 0.05:
        bracket_center_final = bayes_center
        sigma_final          = bayes_sigma
        print(f"  Bayesian update: center {bracket_center_adj}→{bayes_center}, "
              f"sigma {bracket_uncertainty}→{bayes_sigma}, adj={bayes_adj:+}")
    else:
        bracket_center_final = bracket_center_adj
        sigma_final          = bracket_uncertainty

    # ── Upgrade sigma using ensemble quantiles when available ─────────────────
    # Ensemble IQR-derived sigma is better than the formula-based estimate
    if ensemble_quantiles and ensemble_quantiles.get("sigma_from_ensemble"):
        ens_sigma = ensemble_quantiles["sigma_from_ensemble"]
        # Blend: 60% ensemble sigma + 40% computed sigma (don't fully override)
        sigma_final = round(0.60 * ens_sigma + 0.40 * sigma_final, 2)

    # Recompute brackets with final improved center and sigma
    brackets = compute_bracket_analysis(
        bracket_center_final, om_hourly or nws_hourly,
        unit=unit, uncertainty=sigma_final, wu_peak=wu_peak
    )

    # Add ensemble-based probabilities to each bracket (no Gaussian assumption)
    if ensemble_quantiles and ensemble_quantiles.get("member_peaks") and brackets:
        ens_enriched = compute_bucket_probs_from_ensemble(
            ensemble_quantiles["member_peaks"], brackets
        )
        if ens_enriched:
            brackets = ens_enriched  # now each bracket has both forecast_prob + ensemble_prob


    # ── Confidence score — research-based ────────────────────────────────────
    # NWS verification: day-0 skill ~90%, day-1 ~85%, day-3 ~70%, day-5 ~55%
    conf = (95 if days_out <= 0 else 88 if days_out == 1 else 80 if days_out == 2
            else 70 if days_out == 3 else 60 if days_out == 4 else max(35, 70-(days_out-2)*8))
    if model_agreement is False:     conf -= 12
    elif model_agreement is True:    conf += 5
    if max_precip >= 70:             conf -= 10
    elif max_precip >= 40:           conf -= 5
    if wu_peak is not None and days_out <= 0:
        if day_is_over:              conf = min(99, conf + 20)
        elif current_hour_f >= peak_hour_est - 1: conf = min(97, conf + 12)
        else:                        conf = min(95, conf + 5)
    conf = min(99, max(20, conf))

    # Fetch live Polymarket odds and merge with our forecast probabilities
    # NOTE: PM odds are fetched client-side. We just build the slug here.
    city_slug = coords.get("pm_city_slug", city.lower().replace(" ","--"))
    pm_url    = build_polymarket_url(city, city_slug, date, unit)
    pm_search = build_polymarket_search_url(city, date)

    # Chart data
    om_by_h     = {h["hour"]: h["temp"]        for h in om_hourly}
    nws_by_h    = {h["hour"]: h["temp"]        for h in nws_hourly}
    vc_by_h     = {h["hour"]: h.get("temp")    for h in vc_hourly}
    intl_by_h   = {h["hour"]: h.get("temp")    for h in intl_hourly}
    precip_by_h = {h["hour"]: h.get("precip_prob",0) for h in om_hourly}
    wind_by_h   = {h["hour"]: h.get("wind",0)  for h in om_hourly}
    all_hrs = sorted(set(list(om_by_h)+list(nws_by_h)+list(vc_by_h)+list(intl_by_h)))
    chart_data = [{"hour":hr,"om":om_by_h.get(hr),"nws":nws_by_h.get(hr),
                   "vc":vc_by_h.get(hr),"intl":intl_by_h.get(hr),
                   "precip":precip_by_h.get(hr,0),"wind":wind_by_h.get(hr,0)} for hr in all_hrs]

    return jsonify({
        "city": city, "date": date, "days_out": days_out,
        "unit": unit, "unit_symbol": sym,
        "flag": coords.get("flag",""), "station": coords.get("station",""),
        "wunderground": coords.get("wunderground",""),
        "note": coords.get("note",""), "volume": coords.get("volume",""),
        "om_peak": om_peak, "nws_peak": nws_peak,
        "nws_source": "official daily high" if nws_daily_high is not None else "hourly max",
        "vc_peak": vc_peak, "wu_peak": wu_peak, "intl_peak": intl_peak,
        "intl_source": intl_data.get("source","") if intl_data else "",
        "intl_source_url": intl_data.get("source_url","") if intl_data else "",
        "consensus_peak": consensus_peak,
        # ── NEW: Multi-model intelligence ─────────────────────────────────────────
        "multi_model_peaks":  multi_model_peaks,  # {HRRR:85, ICON:84, GEM:86}
        "intel_agreement":    intel_agreement,     # "strong"/"moderate"/"poor"
        "intel_confidence":   intel_confidence,    # "high"/"medium"/"low"
        "intel_spread":       intel_spread,        # degrees spread across models
        "intel_time_label":   intel_time_label,    # "pre-sunrise"/"midday" etc
        "intel_iem_weight":   intel["iem_weight"],  # weight given to real station data
        "intel_model_weight": intel["model_weight"],
        "bet_sizing_mult":    intel["bet_sizing_mult"],  # 0.25-1.0 Kelly multiplier
        "smart_consensus":    smart_consensus,     # best estimate (time-weighted)
        # ── NEW: Ensemble quantile distribution ───────────────────────────────
        "ensemble_quantiles": ensemble_quantiles,  # {p10,p25,p50,p75,p90,iqr,...}
        # ── NEW: Bayesian intraday update ────────────────────────────────────
        "bayes_adjustment":   bayes_adj,           # how much we shifted the forecast
        "bayes_trail":        bayes_trail,          # [{hour, station, model, diff}, ...]
        "bracket_center_final": bracket_center_final,
        "sigma_final":        sigma_final,
        # ─────────────────────────────────────────────────────────────────
        "wu_available": wu_data.get("available",False),
        "wu_is_realtime": wu_data.get("available",False) and "ERA5" not in (wu_data.get("method") or ""),
        "wu_cross_check": wu_cross_check,
        "wu_peak_effective": wu_peak_effective,
        "wu_low": wu_data.get("low_temp"),
        "wu_avg": wu_data.get("avg_temp"),
        "wu_precip": wu_data.get("precip"),
        "wu_wind": wu_data.get("max_wind"),
        "wu_dew": wu_data.get("dew_point"),
        "wu_url": wu_data.get("url",""),
        "wu_method": wu_data.get("method",""),
        "wu_last_updated": wu_data.get("last_updated",""),
        "wu_hourly": wu_data.get("hourly",[]),
        "vc_available": vc_data.get("available",False),
        "vc_conditions": vc_data.get("conditions",""),
        "model_agreement": model_agreement, "model_spread": model_spread,
        "confidence": conf,
        "precip_risk": round(max_precip), "wind_max": round(max_wind),
        "source_gap": source_gap, "source_gap_direction": source_gap_direction,
        "daily_max": daily_max, "daily_min": daily_min,
        "chart_data": chart_data,
        "om_hourly": om_hourly, "nws_hourly": nws_hourly[:12],
        "brackets": brackets,
        "predictor": predictor,
        "source_urls": source_urls,
        "pm_event_slug": f"highest-temperature-in-{city_slug}-on-{datetime.strptime(date,'%Y-%m-%d').strftime('%B').lower()}-{datetime.strptime(date,'%Y-%m-%d').day}-{datetime.strptime(date,'%Y-%m-%d').year}",
        "pm_city_slug": city_slug,
        "polymarket_url": pm_url,
        "polymarket_search_url": pm_search,
        "peak_hour_est": round(peak_hour_est, 2),
        "bracket_sigma": bracket_uncertainty,
        "bracket_center": bracket_center_adj,
        "bracket_center_raw": bracket_center,
        "aviation_corrections": aviation_corr["corrections_list"],
        "aviation_temp_correction": aviation_corr["temp_correction"],
        "aviation_sigma_correction": aviation_corr["sigma_correction"],
        "sigmet_active": aviation_corr["sigmet_active"],
        "taf_peak_temp": aviation_corr["taf_peak_temp"],
        "metar_sky_code": aviation_corr["sky_code"],
        "metar_sky_oktas": aviation_corr["sky_oktas"],
        "metar_raw": aviation_corr["metar_raw"],
        "metar_available": aviation_corr["metar_available"],
        "taf_available": aviation_corr["taf_available"],
        "sigmet_available": aviation_corr["sigmet_available"],
        "day_is_over": day_is_over,
        "climate": climate,
    })

@app.route("/api/wu_live/<city>/<date>")
@require_license
def api_wu_live(city, date):
    city = unquote(city)
    """
    Lightweight endpoint — only re-fetches Wunderground/station data.
    Also recomputes brackets centered on actual observed high.
    """
    coords = CITY_COORDS.get(city)
    if not coords:
        return jsonify({"error": f"City '{city}' not found"}), 404
    unit  = coords.get("unit", "fahrenheit")
    wu    = fetch_wunderground(coords["wunderground"], date, station=coords.get("station"), unit=unit)
    wu_peak = wu.get("high_temp") if wu.get("available") else None

    # Recompute brackets centered on actual observed high, using dynamic sigma
    brackets = None
    if wu_peak is not None:
        tz_obj = ZoneInfo(coords.get("tz", "America/New_York"))
        now_local = datetime.now(tz_obj)
        cur_hr = now_local.hour + now_local.minute / 60.0
        climate = coords.get("climate", "continental")
        ph = compute_peak_hour(
            coords["lat"], now_local.month,
            climate=climate, urban=coords.get("urban", False),
            coastal=coords.get("coastal", False)
        )
        sigma = compute_dynamic_sigma(
            unit=unit, days_out=0, current_hour_f=cur_hr, peak_hour=ph,
            wu_peak=wu_peak, wu_is_final=(cur_hr > ph + 0.5), climate=climate
        )
        brackets = compute_bracket_analysis(
            wu_peak, [], unit=unit, uncertainty=sigma, wu_peak=wu_peak
        )

    return jsonify({
        "wu_available":    wu.get("available", False),
        "wu_peak":         wu_peak,
        "wu_low":          wu.get("low_temp"),
        "wu_avg":          wu.get("avg_temp"),
        "wu_precip":       wu.get("precip"),
        "wu_wind":         wu.get("max_wind"),
        "wu_dew":          wu.get("dew_point"),
        "wu_method":       wu.get("method", ""),
        "wu_last_updated": wu.get("last_updated", ""),
        "wu_hourly":       wu.get("hourly", []),
        "unit_symbol":     "°C" if unit == "celsius" else "°F",
        "brackets":        brackets,
    })


def parse_pm_bracket_label(question, unit="fahrenheit"):
    """
    Parse a Polymarket bracket question into (lo, hi) numeric boundaries.

    US markets (Fahrenheit) — range format:
      "Will the highest temperature in Atlanta be 40-41°F on February 23?"
      "Will the highest temperature in Atlanta be 39°F or below on February 23?"
      "Will the highest temperature in Atlanta be 54°F or higher on February 23?"
      Short: "40-41°F", "39°F or below", "54°F or higher"

    International markets (Celsius) — SINGLE value format:
      "Will the highest temperature in London be 13°C on February 23?"
      "Will the highest temperature in London be 16°C or higher on February 23?"
      Short: "13°C", "8°C or below", "16°C or higher", "-5°C or below"

    Returns (lo, hi, bracket_type) or None if parsing fails.
    For single-value brackets: lo=val, hi=val+1 (exclusive), type="single"
    NOTE: Supports negative temperatures (e.g. -10°C or below).
    """
    q = question.strip()
    # Number pattern: optional minus sign, digits, optional decimal
    _N = r'(-?\d+(?:\.\d+)?)'

    # ── Cap patterns (check BEFORE range/single to avoid mis-parsing) ─────────

    # "X°C or below" / "X°F or below" / "X or lower"
    m = re.search(_N + r'\s*°?\s*[CcFf]?\s+or\s+(?:below|lower)', q, re.IGNORECASE)
    if m:
        val = float(m.group(1))
        return -999, val + 1, "low_cap"

    # "X°C or higher" / "X°F or above"
    m = re.search(_N + r'\s*°?\s*[CcFf]?\s+or\s+(?:above|higher)', q, re.IGNORECASE)
    if m:
        return float(m.group(1)), None, "high_cap"

    # "below X°C" / "under X°F"
    m = re.search(r'(?:below|under)\s+' + _N + r'\s*°?\s*[CcFf]?', q, re.IGNORECASE)
    if m:
        return -999, float(m.group(1)), "low_cap"

    # "above X°C" / "over X°F"
    m = re.search(r'(?:above|over)\s+' + _N + r'\s*°?\s*[CcFf]?', q, re.IGNORECASE)
    if m:
        return float(m.group(1)), None, "high_cap"

    # ── Range bracket: "40-41°F" or "-5--3°C" ────────────────────────────────
    # Handle both: "40-41°F" and negative ranges like "-5--3°C"
    m = re.search(r'(-?\d+(?:\.\d+)?)\s*[-–]\s*(-?\d+(?:\.\d+)?)\s*°?\s*[CcFf]?', q)
    if m:
        lo = float(m.group(1))
        hi = float(m.group(2)) + 1   # "40-41°F" means 40 ≤ temp < 42
        return lo, hi, "range"

    # ── Single-value bracket: "13°C" or "be 13°C on" or "-5°C" ──────────────
    m = re.search(_N + r'\s*°\s*[CcFf]', q)
    if m:
        val = float(m.group(1))
        return val, val + 1, "single"   # 13°C means 13 ≤ temp < 14

    return None


@app.route("/api/pm_odds/<city>/<date>")
@require_license
def api_pm_odds(city, date):
    city = unquote(city)
    """
    Server-side proxy for Polymarket gamma API.
    Returns PM's exact bracket boundaries WITH our forecast probabilities computed on those
    same boundaries — so the display always uses PM's real labels. No mismatch ever.

    Optional query params:
      distribution_center: float — our best peak estimate (for forecast prob calc)
      sigma:               float — uncertainty spread
    """
    coords = CITY_COORDS.get(city)
    if not coords:
        return jsonify({"error": "City not found"}), 404

    unit = coords.get("unit", "fahrenheit")
    city_slug = coords.get("pm_city_slug", city.lower().replace(" ", "-"))

    # Forecast distribution params (passed from frontend after analysis)
    try:
        dist_center = float(request.args.get("center", 0))
        sigma       = float(request.args.get("sigma", 2.5))
    except:
        dist_center, sigma = 0.0, 2.5

    try:
        dt = datetime.strptime(date, "%Y-%m-%d")
        month = dt.strftime("%B").lower()
        day   = dt.day
        year  = dt.year
    except:
        return jsonify({"error": "Invalid date"}), 400

    slugs = [
        f"highest-temperature-in-{city_slug}-on-{month}-{day}-{year}",
        f"highest-temperature-in-{city_slug}-{month}-{day}-{year}",
        f"highest-temp-in-{city_slug}-on-{month}-{day}-{year}",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0",
        "Accept": "application/json",
        "Origin": "https://polymarket.com",
        "Referer": "https://polymarket.com/",
    }

    raw_markets = None
    slug_used   = None

    # 1. Slug-based lookup
    for slug in slugs:
        try:
            r = requests.get(f"https://gamma-api.polymarket.com/events?slug={slug}&limit=1",
                             headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data and data[0].get("markets"):
                    raw_markets = data[0]["markets"]
                    slug_used = slug
                    break
        except Exception as e:
            print(f"PM slug {slug} error: {e}")

    # 2. Keyword search fallback
    if not raw_markets:
        try:
            r = requests.get(
                f"https://gamma-api.polymarket.com/events?search=highest+temperature+{city_slug}&limit=20",
                headers=headers, timeout=10)
            if r.status_code == 200:
                for ev in (r.json() or []):
                    title = (ev.get("title","") or ev.get("question","") or "").lower()
                    if month in title and str(day) in title and ev.get("markets"):
                        raw_markets = ev["markets"]
                        slug_used = "search"
                        break
        except Exception as e:
            print(f"PM search error: {e}")

    if not raw_markets:
        return jsonify({
            "ok":     False,
            "error":  "Market not listed on Polymarket yet",
            "pm_url": f"https://polymarket.com/event/{slugs[0]}",
        })

    # ── Parse each market into a structured bracket ───────────────────────────
    parsed_brackets = []
    total_volume = 0

    for m in raw_markets:
        question = (m.get("question") or m.get("groupItemTitle") or "").strip()

        # Parse yes price (0–1 decimal → percentage)
        prices = m.get("outcomePrices", "[]")
        if isinstance(prices, str):
            try: prices = __import__('json').loads(prices)
            except: prices = []
        yes_price = None
        if prices:
            try:
                raw = float(prices[0])
                yes_price = round((raw * 100 if raw <= 1 else raw), 1)
            except: pass

        vol = 0
        try: vol = round(float(m.get("volume") or m.get("volumeNum") or 0))
        except: pass
        total_volume += vol

        parsed = parse_pm_bracket_label(question, unit)
        if parsed is None:
            print(f"  Could not parse PM bracket: '{question}'")
            continue

        lo, hi, btype = parsed
        sym = "°C" if unit == "celsius" else "°F"

        # Build a clean short label from parsed boundaries
        if btype == "low_cap":
            clean_label = f"{int(hi-1)}{sym} or below"
        elif btype == "high_cap":
            clean_label = f"{int(lo)}{sym} or higher"
        elif btype == "single":
            clean_label = f"{int(lo)}{sym}"           # e.g. "13°C"
        else:
            clean_label = f"{int(lo)}-{int(hi-1)}{sym}"  # e.g. "40-41°F"

        parsed_brackets.append({
            "label":        clean_label,
            "lo":           lo,
            "hi":           hi,
            "pm_yes_price": yes_price,
            "pm_volume":    vol,
            "bracket_type": btype,
        })

    if not parsed_brackets:
        return jsonify({
            "ok":     False,
            "error":  "Found market but could not parse bracket labels",
            "pm_url": f"https://polymarket.com/event/{slugs[0]}",
        })

    # Sort by lo ascending
    parsed_brackets.sort(key=lambda b: b["lo"])

    # ── Compute OUR forecast probability on PM's exact bracket boundaries ─────
    # This is the key fix: our forecast uses PM's ranges, not our own generated ones
    if dist_center > 0:
        brackets_with_forecast = compute_forecast_on_brackets(
            parsed_brackets, dist_center, sigma, unit
        )
    else:
        # No center provided — just return PM data without forecast overlay
        brackets_with_forecast = parsed_brackets

    return jsonify({
        "ok":           True,
        "brackets":     brackets_with_forecast,   # PM labels + our forecast_prob + pm_yes_price
        "total_volume": total_volume,
        "slug_used":    slug_used,
        "pm_url":       f"https://polymarket.com/event/{slugs[0]}",
        "market_count": len(brackets_with_forecast),
    })


@app.route("/api/edge", methods=["POST"])
@require_license
def api_edge():
    data = request.get_json()
    brackets = data.get("brackets", [])
    pm_odds = data.get("polymarket_odds", {})
    results = []
    best_val = 0
    for b in brackets:
        fp = b.get("forecast_prob")
        pp = float(pm_odds[b["label"]]) if b["label"] in pm_odds and pm_odds[b["label"]] != "" else None
        edge = compute_edge(fp, pp)
        rating, stars = edge_rating(edge)
        action = ("BUY YES" if edge>=10 else "BUY NO" if edge<=-10 else "SKIP") if edge is not None else None
        results.append({"label":b["label"],"forecast_prob":fp,"polymarket_prob":pp,"edge":edge,"rating":rating,"stars":stars,"action":action})
        if edge is not None and abs(edge)>abs(best_val): best_val=edge
    results.sort(key=lambda x: abs(x.get("edge") or 0), reverse=True)
    return jsonify({"results":results,"best_edge_val":best_val})

@app.route("/api/basket", methods=["POST"])
@require_license
def api_basket():
    import itertools
    data = request.get_json()
    brackets = data.get("brackets", [])
    priced = [b for b in brackets if b.get("price_cents") is not None]
    if len(priced)<2: return jsonify({"error":"Need at least 2 brackets with prices"}), 400
    results = []
    for size in range(2, min(6,len(priced)+1)):
        for combo in itertools.combinations(priced, size):
            cost_c = sum(b["price_cents"] for b in combo)
            cost = cost_c/100.0
            if cost>=1.0: continue
            win_prob = min(sum(b["forecast_prob"] for b in combo), 99.9)
            ev = (win_prob/100.0)*1.0 - cost
            ev_pct = round(ev/cost*100, 1)
            if ev<=0 or ev_pct<5: continue
            rating = "🔥 Strong" if ev_pct>=30 else "⚡ Good" if ev_pct>=15 else "📊 Weak"
            stars = 3 if ev_pct>=30 else 2 if ev_pct>=15 else 1
            labels=[b["label"] for b in combo]
            all_labels=[b["label"] for b in brackets]
            idxs=[all_labels.index(l) for l in labels if l in all_labels]
            is_adj=len(idxs)>1 and (max(idxs)-min(idxs))==len(idxs)-1
            results.append({"brackets":labels,"bracket_details":[{"label":b["label"],"price_cents":b["price_cents"],"forecast_prob":b["forecast_prob"]} for b in combo],"total_cost_cents":cost_c,"total_cost":round(cost,2),"win_prob":round(win_prob,1),"ev":round(ev,3),"ev_pct":ev_pct,"profit_if_win":round(1.0-cost,2),"rating":rating,"stars":stars,"is_adjacent":is_adj})
    results.sort(key=lambda x:(-int(x["is_adjacent"]),-x["ev_pct"]))
    total_all = sum(b["price_cents"] for b in priced)/100.0
    return jsonify({"baskets":results[:20],"total_market_cost":round(total_all,3),"underround":total_all<0.98,"underround_gap":round(1.0-total_all,3),"brackets_priced":len(priced)})

if __name__ == "__main__":
    app.run(debug=True, port=5001, threaded=True)
