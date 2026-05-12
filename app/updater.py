"""
Weather Edge Analyzer — Update Checker
=======================================
Checks a GitHub Gist you control for new versions.
If a newer version is available, notifies the user in the terminal.

How to set up your update gist:
  1. Go to gist.github.com
  2. Create a PUBLIC gist called "weather-edge-version.json"
  3. Content:
     {
       "version": "1.0.0",
       "notes": "Initial release",
       "required": false
     }
  4. Copy the raw URL and paste it into GIST_URL below
  5. When you release v1.1.0, just edit the gist — all users see it next launch

Fields:
  version  — new version string
  notes    — what's new (shown to user)
  required — if true, app exits until they get the update (use sparingly)
"""

import urllib.request
import urllib.error
import json
import threading
from packaging import version as pkg_version

# ─────────────────────────────────────────────────────────────────────────────
# Paste your GitHub Gist RAW URL here after creating it
# Example: https://gist.githubusercontent.com/YourUsername/abc123/raw/weather-edge-version.json
# ─────────────────────────────────────────────────────────────────────────────
"https://gist.githubusercontent.com/NethulaRashvinTennakoon2007417/abc123def456/raw/weather-edge-version.json"

CURRENT_VERSION = "1.1.0"
CHECK_TIMEOUT   = 4   # seconds — don't slow down startup


def _compare_versions(current: str, latest: str) -> bool:
    """Returns True if latest > current."""
    try:
        # Simple comparison without packaging dependency
        def parse(v):
            return tuple(int(x) for x in v.strip().split("."))
        return parse(latest) > parse(current)
    except Exception:
        return False


def check_for_updates(silent_if_current: bool = True) -> dict | None:
    """
    Check for updates. Returns update info dict or None.
    Runs fast — times out after CHECK_TIMEOUT seconds.
    Never crashes the app if gist is unreachable.
    """
    try:
        req = urllib.request.Request(
            GIST_URL,
            headers={"User-Agent": "WeatherEdge/1.0", "Cache-Control": "no-cache"}
        )
        with urllib.request.urlopen(req, timeout=CHECK_TIMEOUT) as resp:
            data = json.loads(resp.read().decode())

        latest   = data.get("version", CURRENT_VERSION)
        notes    = data.get("notes", "")
        required = data.get("required", False)

        if _compare_versions(CURRENT_VERSION, latest):
            return {
                "available": True,
                "current":   CURRENT_VERSION,
                "latest":    latest,
                "notes":     notes,
                "required":  required,
            }
        return {"available": False}

    except Exception:
        # Network down, gist unreachable, etc — silently skip
        return None


def check_and_display(license_info: dict = None) -> None:
    """
    Check for updates and print a notification if one is available.
    Called at startup — non-blocking.
    """
    result = check_for_updates()
    if not result or not result.get("available"):
        return

    latest   = result["latest"]
    notes    = result["notes"]
    required = result["required"]

    print("┌─ UPDATE AVAILABLE ─────────────────────────────────┐")
    print(f"│  v{CURRENT_VERSION}  →  v{latest}")
    if notes:
        print(f"│  What's new: {notes[:46]}")
    print("│")
    print("│  DM @YourXHandle on X to get the update.")
    if required:
        print("│  ⚠ This update is REQUIRED to continue.")
    print("└────────────────────────────────────────────────────┘\n")

    if required:
        import sys
        print("  App will not start until updated. DM for the new version.")
        sys.exit(0)


def check_async(license_info: dict = None) -> None:
    """Run update check in background thread — doesn't slow startup."""
    t = threading.Thread(target=check_and_display, args=(license_info,), daemon=True)
    t.start()
    t.join(timeout=CHECK_TIMEOUT + 1)   # wait max 5s so message shows before Flask starts
