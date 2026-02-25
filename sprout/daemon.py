"""launchd plist generation and install/uninstall for macOS."""

import subprocess
import sys
from pathlib import Path

PLIST_NAME = "com.sprout.scheduler"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{PLIST_NAME}.plist"
PROJECT_DIR = Path(__file__).parent.parent
LOG_DIR = PROJECT_DIR / "logs"


def _generate_plist() -> str:
    uv_path = subprocess.run(
        ["which", "uv"], capture_output=True, text=True
    ).stdout.strip() or "/usr/local/bin/uv"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{PLIST_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>{uv_path}</string>
        <string>run</string>
        <string>--directory</string>
        <string>{PROJECT_DIR}</string>
        <string>python</string>
        <string>-m</string>
        <string>sprout.scheduler</string>
        <string>daemon</string>
    </array>
    <key>WorkingDirectory</key>
    <string>{PROJECT_DIR}</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{LOG_DIR}/scheduler.log</string>
    <key>StandardErrorPath</key>
    <string>{LOG_DIR}/scheduler.log</string>
</dict>
</plist>
"""


def start():
    """Install and load the launchd daemon."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.write_text(_generate_plist())
    subprocess.run(["launchctl", "load", str(PLIST_PATH)], check=True)
    print(f"Sprout scheduler daemon started. Logs: {LOG_DIR}/scheduler.log")


def stop():
    """Unload and remove the launchd daemon."""
    if PLIST_PATH.exists():
        subprocess.run(["launchctl", "unload", str(PLIST_PATH)], check=False)
        PLIST_PATH.unlink()
        print("Sprout scheduler daemon stopped.")
    else:
        print("Daemon not installed.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m sprout.daemon start|stop")
    elif sys.argv[1] == "start":
        start()
    elif sys.argv[1] == "stop":
        stop()
    else:
        print(f"Unknown command: {sys.argv[1]}")
