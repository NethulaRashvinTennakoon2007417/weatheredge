#!/usr/bin/env python3
"""
Weather Edge Analyzer — Main Launcher
Works as both: python launch.py  AND  WeatherEdge.exe (double-click)
"""

import sys
import os
import time
import threading
import webbrowser
import importlib.util
from pathlib import Path

# ── Path resolution: works for .py AND PyInstaller .exe ──────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = Path(sys._MEIPASS)   # PyInstaller temp extraction folder
else:
    BASE_DIR = Path(__file__).parent

APP_DIR = BASE_DIR / "app"
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(BASE_DIR))

# ── STEP 1: License check ────────────────────────────────────────────────────
try:
    from license import check_license_or_prompt
    license_info = check_license_or_prompt()
except ImportError as e:
    print(f"\n  ERROR loading license: {e}\n  Base: {BASE_DIR}")
    input("  Press Enter to exit...")
    sys.exit(1)

# ── STEP 2: Update check (non-blocking, silent if offline) ───────────────────
try:
    from updater import check_async
    check_async(license_info)
except Exception:
    pass

# ── STEP 3: Launch Flask app ─────────────────────────────────────────────────
PORT = 5000

def open_browser():
    time.sleep(1.8)
    webbrowser.open(f"http://localhost:{PORT}")

threading.Thread(target=open_browser, daemon=True).start()

print(f"  Starting Weather Edge Analyzer...")
print(f"  Opening http://localhost:{PORT} in your browser...")
print(f"  Keep this window open while using the app.")
print(f"  Press Ctrl+C to stop.\n")

try:
    # Tell Flask where templates are (critical inside bundled exe)
    os.environ["WEATHER_TEMPLATE_DIR"] = str(APP_DIR / "templates")

    spec = importlib.util.spec_from_file_location("weather", str(APP_DIR / "weather.py"))
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    mod.app.config["SUBSCRIBER_ID"] = license_info.get("subscriber_id", "")
    mod.app.config["DAYS_LEFT"]     = license_info.get("days_left", 0)
    mod.app.config["EXPIRES_AT"]    = str(license_info.get("expires_at", ""))

    mod.app.run(host="127.0.0.1", port=PORT, debug=False, use_reloader=False)

except KeyboardInterrupt:
    print("\n\n  Weather Edge stopped. See you next time! ⚡")
    sys.exit(0)

except OSError as e:
    if "Address already in use" in str(e) or "10048" in str(e):
        print(f"\n  Port {PORT} is already in use — another instance is running.")
        print(f"  Open your browser and go to: http://localhost:{PORT}")
    else:
        print(f"\n  Network error: {e}")
    input("\n  Press Enter to exit...")

except Exception as e:
    print(f"\n  ERROR: {e}")
    import traceback; traceback.print_exc()
    print("\n  Screenshot this and DM @YourXHandle on X.")
    input("\n  Press Enter to exit...")
    sys.exit(1)
