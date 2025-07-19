#!/usr/bin/env python3
"""
Synology DS920+ Advanced Fan Controller
- Implements 3 fan modes with proper thresholds: adjust as necessary
  * Quiet mode (<40°C)
  * Cool mode (40-55°C)
  * Full mode (≥55°C)
- Uses multiple temperature sources for reliability
- Includes proper state management and error handling
"""

import json
import os
import time
import pathlib
import requests
from typing import Optional, Tuple

# ----------------- CONFIGURATION -----------------
DSM_HOST = "https://domain.synology.me:5001"            # DSM host address, use a synology DDNS & Cert
DSM_USER = "dedicatedscriptusername"                     # DSM username
DSM_PASS = "randompass"              # DSM password
VERIFY_SSL = True                       # Verify SSL certificate, if https:// workwing with the Doamain. 
SESSION_NAME = "fancontrol"             # Session name for API

# Temperature thresholds (in Celsius)
TEMP_QUIET_MAX = 40                     # Below this: quiet mode, above: cool mode
TEMP_COOL_MAX = 55                      # Below this: cool mode, above: full mode

# Fan modes (verify these match your DSM's available modes)
QUIET_MODE = "quietfan"
COOL_MODE = "coolfan"
FULL_MODE = "fullfan"

# State management
STATE_FILE = "/volume1/scripts/.fanstate.json"  # Chnage to the folder where scripts are hosted. 
FORCE_REFRESH_INTERVAL = 300            # Re-apply mode every 5 minutes (seconds)
MIN_MODE_CHANGE_INTERVAL = 60           # Minimum seconds between mode changes

# API endpoints
API_AUTH = "/webapi/auth.cgi"
API_ENTRY = "/webapi/entry.cgi"
# ------------------------------------------------

class FanController:
    def __init__(self):
        self.session = requests.Session()
        self.sid = None
        self.token = None
        self.state = {
            "last_mode": None,
            "last_change": 0,
            "last_temp": None,
            "temp_source": None
        }
        
    def login(self) -> str:
        """Authenticate with DSM and return session ID"""
        params = {
            "api": "SYNO.API.Auth",
            "version": "7.22",
            "method": "login",
            "account": DSM_USER,
            "passwd": DSM_PASS,
            "session": SESSION_NAME,
            "format": "sid",
        }
        try:
            r = self.session.get(
                DSM_HOST + API_AUTH,
                params=params,
                verify=VERIFY_SSL,
                timeout=10
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("success"):
                raise RuntimeError(f"DSM login failed: {data}")
            self.sid = data["data"]["sid"]
            return self.sid
        except Exception as e:
            raise RuntimeError(f"Login error: {str(e)}")

    def get_temperature(self) -> Tuple[Optional[float], str]:
        """
        Get current temperature from multiple possible sources
        Returns (temperature, source) or (None, error_message)
        """
        # Try SYNO.Core.Hardware.Thermal first (most reliable)
        params = {
            "api": "SYNO.Core.Hardware.Thermal",
            "version": "1",
            "method": "status",
            "_sid": self.sid
        }
        try:
            r = self.session.get(
                DSM_HOST + API_ENTRY,
                params=params,
                verify=VERIFY_SSL,
                timeout=10
            )
            r.raise_for_status()
            j = r.json()
            if j.get("success"):
                temp = j["data"].get("cpu_temp") or j["data"].get("system_temp")
                if temp is not None:
                    return float(temp), "SYNO.Core.Hardware.Thermal"
        except Exception:
            pass

        # Fallback to SYNO.Core.System
        params = {
            "api": "SYNO.Core.System",
            "version": "1",
            "method": "info",
            "_sid": self.sid
        }
        try:
            r = self.session.get(
                DSM_HOST + API_ENTRY,
                params=params,
                verify=VERIFY_SSL,
                timeout=10
            )
            r.raise_for_status()
            j = r.json()
            if j.get("success") and "temp" in j.get("data", {}):
                return float(j["data"]["temp"]), "SYNO.Core.System"
        except Exception:
            pass

        # Final fallback to sysfs (direct hardware reading)
        try:
            for p in pathlib.Path("/sys/class/hwmon").glob("hwmon*/temp*_input"):
                with open(p) as fh:
                    temp = int(fh.read().strip()) / 1000
                if 10 < temp < 110:  # Basic sanity check
                    return temp, f"sysfs:{p}"
        except Exception:
            pass

        return None, "No temperature source available"

    def get_fan_token(self) -> Optional[str]:
        """Get SynoToken if available (not strictly necessary)"""
        params = {
            "api": "SYNO.Core.Hardware.FanSpeed",
            "version": "1",
            "method": "get",
            "_sid": self.sid
        }
        try:
            r = self.session.get(
                DSM_HOST + API_ENTRY,
                params=params,
                verify=VERIFY_SSL,
                timeout=10
            )
            r.raise_for_status()
            j = r.json()
            if j.get("success"):
                self.token = j.get("data", {}).get("SynoToken")
                return self.token
        except Exception:
            return None
        return None

    def set_fan_mode(self, mode: str) -> bool:
        """Set the fan mode and return success status"""
        # Don't change mode too frequently
        if time.time() - self.state["last_change"] < MIN_MODE_CHANGE_INTERVAL:
            print(f"[DEBUG] Skipping mode change (too recent last change)")
            return False

        params = {
            "api": "SYNO.Core.Hardware.FanSpeed",
            "version": "1",
            "method": "set",
            "dual_fan_speed": mode,
            "_sid": self.sid
        }
        if self.token:
            params["SynoToken"] = self.token

        try:
            r = self.session.get(
                DSM_HOST + API_ENTRY,
                params=params,
                verify=VERIFY_SSL,
                timeout=10
            )
            r.raise_for_status()
            result = r.json()
            
            if result.get("success"):
                self.state["last_mode"] = mode
                self.state["last_change"] = time.time()
                print(f"[SUCCESS] Fan mode set to {mode}")
                return True
            else:
                print(f"[ERROR] Failed to set fan mode: {result}")
                return False
        except Exception as e:
            print(f"[ERROR] Fan control error: {str(e)}")
            return False

    def determine_mode(self, temp: float) -> str:
        """Determine appropriate fan mode based on temperature"""
        if temp < TEMP_QUIET_MAX:
            return QUIET_MODE
        elif temp < TEMP_COOL_MAX:
            return COOL_MODE
        else:
            return FULL_MODE

    def load_state(self):
        """Load persistent state from file"""
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE) as f:
                    self.state.update(json.load(f))
            except Exception as e:
                print(f"[WARNING] Could not load state: {str(e)}")

    def save_state(self):
        """Save current state to file"""
        try:
            tmp = STATE_FILE + ".tmp"
            with open(tmp, "w") as f:
                json.dump(self.state, f)
            os.replace(tmp, STATE_FILE)
        except Exception as e:
            print(f"[WARNING] Could not save state: {str(e)}")

    def run(self):
        """Main control loop"""
        self.load_state()
        
        try:
            # Step 1: Authenticate
            self.login()
            
            # Step 2: Get current temperature
            temp, source = self.get_temperature()
            if temp is None:
                print("[ERROR] Could not read temperature")
                return
            
            self.state["last_temp"] = temp
            self.state["temp_source"] = source
            
            # Step 3: Get fan token (optional)
            self.get_fan_token()
            
            # Step 4: Determine desired mode
            desired_mode = self.determine_mode(temp)
            
            # Step 5: Check if we need to change the mode
            current_time = time.time()
            mode_changed = False
            
            # Conditions for changing mode:
            # 1. Mode is different from current
            # 2. OR it's time to force refresh
            if (desired_mode != self.state["last_mode"]) or (
                current_time - self.state["last_change"] > FORCE_REFRESH_INTERVAL
            ):
                mode_changed = self.set_fan_mode(desired_mode)
            
            # Log current status
            status_msg = (
                f"[STATUS] Temp={temp:.1f}°C (from {source}) | "
                f"Current mode: {self.state['last_mode']} | "
                f"Desired mode: {desired_mode} | "
                f"Changed: {'Yes' if mode_changed else 'No'}"
            )
            print(status_msg)
            
        except Exception as e:
            print(f"[ERROR] Controller error: {str(e)}")
        finally:
            self.save_state()

def main():
    controller = FanController()
    controller.run()

if __name__ == "__main__":
    main()
