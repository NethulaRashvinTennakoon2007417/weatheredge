#!/usr/bin/env python3
"""
WeatherEdge — Render Web Server Entry Point
This replaces launch.py for hosted deployment.
License validation happens per-request in the browser (localStorage + API).
"""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
APP_DIR  = BASE_DIR / "app"

sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(BASE_DIR))

os.environ["WEATHER_TEMPLATE_DIR"] = str(APP_DIR / "templates")

import importlib.util
spec = importlib.util.spec_from_file_location("weather", str(APP_DIR / "weather.py"))
mod  = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

app = mod.app

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
