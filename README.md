# G733PZ Lightweight OpenRGB Animation

A lightweight, low-resource OpenRGB animation service tailored for the ASUS ROG Strix SCAR 17 (G733PZ) laptop keyboard, mouse, and chassis lightbar.

> **Note**: This is a focused custom animation service implementing **only reactive press** (fade-on-press with per-group decay) and **static baseline lighting** animations, deliberately avoiding heavy dynamic wave or rainbow cycles to maintain minimal CPU usage.

## Features

- **Reactive Keystrokes & Mouse Clicks**: Keys and mouse clicks light up instantly on press and fade back to base colors according to per-group timing.
- **Static Base Lighting**: Configurable static resting colors per key group (keyboard, special keys, most-used keys, Fn key, lightbar).
- **Zero-CPU Idle Sleep**: Fades LEDs off completely when system-wide user inactivity exceeds the configured timeout, restoring full brightness immediately upon input.
- **Interactive Visual Configurator (`--gui`)**: Real-time layout mapper, live color picker with hardware sync, and keystroke heatmap.
- **Layout Editor**: Interactive GUI to adjust and arrange individual key coordinates and dimensions (`layout_coords.json`).
- **Hardware Probe**: PowerShell utility (`probe.ps1`) for testing and identifying specific LED index mappings.

## Requirements

- Windows 10/11
- [OpenRGB](https://openrgb.org/) running with the SDK Server enabled (default port `6742`)
- Python 3.10+ with required libraries:
  ```bash
  pip install openrgb-python pynput pywin32
  ```

## Usage

### 1. Interactive Configurator (`--gui`)
Run with the `--gui` flag to configure colors, timeouts, key group assignments, or inspect the keystroke heatmap:
```bash
python animation.py --gui
```

### 2. Background Service (Windows Task Scheduler)
For day-to-day use, this script is designed to run silently in the background without a persistent console window. It should be scheduled via **Windows Task Scheduler**:

1. Open **Task Scheduler** (`taskschd.msc`).
2. Select **Create Task...** (not Basic Task):
   - **General**:
     - Name: `OpenRGB-Animation`
     - Check: *Run only when user is logged on* (or *Run whether user is logged on or not* if using appropriate credentials)
     - Check: *Run with highest privileges* (recommended for global hotkey/raw input hooks)
   - **Triggers**:
     - New Trigger -> At log on of user.
     - Delay task for: `5 seconds` (ensures OpenRGB server has initialized).
   - **Actions**:
     - Action: *Start a program*
     - Program/script: `pythonw.exe` (use the full path to `pythonw.exe` in your Python environment to suppress console window)
     - Add arguments: `animation.py`
     - Start in: `<path-to-repository-folder>`
   - **Conditions**:
     - Uncheck *Start the task only if the computer is on AC power*.
   - **Settings**:
     - Check *Run task as soon as possible after a scheduled start is missed*.
     - Uncheck *Stop the task if it runs longer than...*.

### 3. LED Index Probe Utility
To sweep or identify specific keyboard/chassis LED index addresses:
```powershell
.\probe.ps1 <index>          # Light a single LED index (e.g. .\probe.ps1 174)
.\probe.ps1 -Step            # Step through candidates one by one
.\probe.ps1 -Range 165,180   # Auto sweep a range of indices
.\probe.ps1 -Reset           # Turn off probe and restore normal control
```

## Hardware Quirks & Troubleshooting

### G733PZ Front Lightbar Direct Mode Mirroring
On the ASUS ROG Strix SCAR 17 (G733PZ), a hardware initialization quirk may cause the 6 front chassis lightbar LEDs to link to keyboard keys (`Left Ctrl`, `Fn`, `Win`, `Num 0`, `Num .`, and `Num Enter`) instead of acting as independent addressable zones.

**Resolution**:
1. Open the **OpenRGB** application.
2. In the device settings, switch the mode from **Direct** to any other mode (e.g. *Static* or *Breathing*).
3. Switch the mode back to **Direct**.

Toggling modes forces OpenRGB to transmit the proper Direct mode initialization sequence to the laptop's controller, restoring discrete addressability to the lightbar segments.

> **Tip**: Save this configuration as an OpenRGB profile to load automatically on boot.

