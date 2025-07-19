# Synology DS920+ Fan Control Script

This Python script provides **advanced fan control** for Synology NAS devices (tested on DS920+).  
It allows for **3 custom fan modes (Quiet, Cool, Full)** based on configurable temperature thresholds.

---

## Features

- **Three fan modes** with temperature thresholds:
  - **Quiet Mode**: Below `TEMP_QUIET_MAX` (default: 40°C)
  - **Cool Mode**: Between `TEMP_QUIET_MAX` and `TEMP_COOL_MAX` (default: 40°C–55°C)
  - **Full Mode**: Above `TEMP_COOL_MAX` (default: 55°C+)
- Pulls temperature data from multiple sources:
  - DSM API (`SYNO.Core.Hardware.Thermal`)
  - DSM Core System Info
  - Direct hardware sensors via `/sys/class/hwmon`
- **State persistence** to avoid frequent fan speed changes.
- **Configurable refresh intervals** and **error handling**.
- Designed to be run via **Synology Task Scheduler** (e.g., every 1–5 minutes).

---

## Installation

1. **Create a dedicated DSM user** for the script (e.g., `fancontrol`) **without 2FA**.
2. Edit the **configuration variables** at the top of `syno_fan_control.py`:
   - DSM host, username, and password.
   - Temperature thresholds: `TEMP_QUIET_MAX` and `TEMP_COOL_MAX`.
   - State file path (`STATE_FILE`).
3. Copy the script to your NAS, for example:
   ```bash
   /volume1/script/syno_fan_control.py


Ensure Python 3 is installed on your NAS.
Test the script manually via SSH if you want. 
/usr/bin/python3 /volume1/script/syno_fan_control.py

output should be like: 
[SUCCESS] Fan mode set to coolfan
[STATUS] Temp=47.3°C (from SYNO.Core.Hardware.Thermal) |
Current mode: coolfan | Desired mode: coolfan | Changed: Yes


Automation (Task Scheduler)
Open Control Panel → Task Scheduler on DSM.
Create a User-defined Script task.
Set it to run as root.
Add the command:

/usr/bin/python3 /volume1/script/syno_fan_control.py

Set the schedule (e.g., every 1 minute or every 5 minutes).

License
This project is open-source. You may modify and use it at your own risk.

Disclaimer. 
This script modifies the fan control behavior of your NAS.
Use with caution—incorrect settings may affect system cooling.
