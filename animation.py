import argparse
import atexit
import ctypes
from ctypes import wintypes
import json
import logging
import os
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import colorchooser, ttk
import traceback

# Optional pywin32 imports for single-instance named mutex
try:
    import win32api
    import win32event
    import winerror
    PYWIN32_AVAILABLE = True
except ImportError:
    PYWIN32_AVAILABLE = False

# Optional hardware imports (graceful fallback if testing without OpenRGB running)
try:
    from openrgb import OpenRGBClient
    from openrgb.utils import DeviceType, RGBColor, OpenRGBDisconnected
    OPENRGB_AVAILABLE = True
except ImportError:
    OPENRGB_AVAILABLE = False

from pynput import keyboard, mouse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(SCRIPT_DIR, "led_config.json")
STATS_FILE = os.path.join(SCRIPT_DIR, "key_stats.json")
LAYOUT_FILE = os.path.join(SCRIPT_DIR, "layout_coords.json")
LOG_FILE = os.path.join(SCRIPT_DIR, "effect.log")

# Under pythonw, sys.stdout and sys.stderr are None; redirect safely to prevent crashes
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8"
)

_mutex = None

def acquire_mutex():
    global _mutex
    if not PYWIN32_AVAILABLE:
        logging.warning("pywin32 not installed; proceeding without named mutex.")
        return

    try:
        _mutex = win32event.CreateMutex(None, False, "Global\\kb_effect_mutex")
        if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
            logging.warning("Another instance of kb-effect is already running. Exiting.")
            sys.exit(0)
    except Exception as e:
        try:
            _mutex = win32event.CreateMutex(None, False, "kb_effect_mutex")
            if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
                logging.warning("Another instance of kb-effect is already running. Exiting.")
                sys.exit(0)
        except Exception as e2:
            logging.error(f"Failed to create mutex: {e2}")

def release_mutex():
    global _mutex
    if _mutex and PYWIN32_AVAILABLE:
        try:
            win32api.CloseHandle(_mutex)
        except Exception:
            pass
        _mutex = None

atexit.register(release_mutex)

def load_layout_coords() -> dict | None:
    if os.path.exists(LAYOUT_FILE):
        try:
            with open(LAYOUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

# Full ASUS ROG Strix SCAR 17 Layout (Macros, ISO/ANSI Keyboard with Numpad & Bottom Lightbar)
KB_LAYOUT = [
    # Row 0: Dedicated Macro Keys
    [
        ("vol_down", "Vol-", 1.0),
        ("vol_up", "Vol+", 1.0),
        ("mute", "Mute", 1.0),
        ("fan", "Fan", 1.0),
        ("rog", "ROG", 1.0),
    ],
    # Row 1: Function & Top Navigation
    [
        ("esc", "Esc", 1.0),
        ("spacer_f1", "", 0.4),
        ("f1", "F1", 1.0),
        ("f2", "F2", 1.0),
        ("f3", "F3", 1.0),
        ("f4", "F4", 1.0),
        ("spacer_f2", "", 0.3),
        ("f5", "F5", 1.0),
        ("f6", "F6", 1.0),
        ("f7", "F7", 1.0),
        ("f8", "F8", 1.0),
        ("spacer_f3", "", 0.3),
        ("f9", "F9", 1.0),
        ("f10", "F10", 1.0),
        ("f11", "F11", 1.0),
        ("f12", "F12", 1.0),
        ("spacer_nav", "", 0.5),
        ("delete", "Del", 1.0),
        ("pause", "Pause", 1.0),
        ("print_screen", "PrtSc", 1.0),
        ("home", "Home", 1.0),
    ],
    # Row 2: Numbers & Numpad Top
    [
        ("`", "`", 1.0),
        ("1", "1", 1.0),
        ("2", "2", 1.0),
        ("3", "3", 1.0),
        ("4", "4", 1.0),
        ("5", "5", 1.0),
        ("6", "6", 1.0),
        ("7", "7", 1.0),
        ("8", "8", 1.0),
        ("9", "9", 1.0),
        ("0", "0", 1.0),
        ("-", "-", 1.0),
        ("=", "=", 1.0),
        ("backspace", "Bksp", 2.0),
        ("spacer_num1", "", 0.4),
        ("num_lock", "Num", 1.0),
        ("num_divide", "/", 1.0),
        ("num_multiply", "*", 1.0),
        ("num_subtract", "-", 1.0),
    ],
    # Row 3: Tab / QWERTY & Numpad 7-9 / +
    [
        ("tab", "Tab", 1.5),
        ("q", "Q", 1.0),
        ("w", "W", 1.0),
        ("e", "E", 1.0),
        ("r", "R", 1.0),
        ("t", "T", 1.0),
        ("y", "Y", 1.0),
        ("u", "U", 1.0),
        ("i", "I", 1.0),
        ("o", "O", 1.0),
        ("p", "P", 1.0),
        ("[", "[", 1.0),
        ("]", "]", 1.0),
        ("\\", "\\", 1.5),
        ("spacer_num2", "", 0.4),
        ("num_7", "7", 1.0),
        ("num_8", "8", 1.0),
        ("num_9", "9", 1.0),
        ("num_add", "+", 1.0),
    ],
    # Row 4: Caps / Home Row & Numpad 4-6
    [
        ("caps_lock", "Caps", 1.8),
        ("a", "A", 1.0),
        ("s", "S", 1.0),
        ("d", "D", 1.0),
        ("f", "F", 1.0),
        ("g", "G", 1.0),
        ("h", "H", 1.0),
        ("j", "J", 1.0),
        ("k", "K", 1.0),
        ("l", "L", 1.0),
        (";", ";", 1.0),
        ("'", "'", 1.0),
        ("enter", "Enter", 2.2),
        ("spacer_num3", "", 0.4),
        ("num_4", "4", 1.0),
        ("num_5", "5", 1.0),
        ("num_6", "6", 1.0),
        ("spacer_num_plus", "", 1.0),
    ],
    # Row 5: Shift / ISO < > / ZXCV & Up Arrow & Numpad 1-3 / Enter
    [
        ("shift", "Shift", 1.3),
        ("iso_extra", "< >", 1.0),
        ("z", "Z", 1.0),
        ("x", "X", 1.0),
        ("c", "C", 1.0),
        ("v", "V", 1.0),
        ("b", "B", 1.0),
        ("n", "N", 1.0),
        ("m", "M", 1.0),
        (",", ",", 1.0),
        (".", ".", 1.0),
        ("/", "/", 1.0),
        ("shift_r", "RShift", 1.7),
        ("spacer_up1", "", 0.2),
        ("up", "↑", 1.0),
        ("spacer_up2", "", 0.2),
        ("num_1", "1", 1.0),
        ("num_2", "2", 1.0),
        ("num_3", "3", 1.0),
        ("num_enter", "Ent", 1.0),
    ],
    # Row 6: Bottom Row & Arrow Cluster & Numpad 0 / .
    [
        ("ctrl_l", "Ctrl", 1.4),
        ("fn", "Fn", 1.0),
        ("cmd", "Win", 1.0),
        ("alt_l", "Alt", 1.2),
        ("space", "Space", 5.2),
        ("alt_gr", "AltGr", 1.2),
        ("ctrl_r", "RCtrl", 1.2),
        ("spacer_arr1", "", 0.2),
        ("left", "←", 1.0),
        ("down", "↓", 1.0),
        ("right", "→", 1.0),
        ("spacer_arr2", "", 0.2),
        ("num_0", "0", 2.0),
        ("num_decimal", ".", 1.0),
        ("spacer_num_ent", "", 1.0),
    ],
    # Row 7: Chassis Front Lightbar (Underglow across the front edge)
    [
        ("spacer_lb1", "", 0.6),
        ("lightbar_l1", "Lightbar L1", 3.0),
        ("lightbar_l2", "Lightbar L2", 3.0),
        ("lightbar_l3", "Lightbar L3", 3.0),
        ("lightbar_r3", "Lightbar R3", 3.0),
        ("lightbar_r2", "Lightbar R2", 3.0),
        ("lightbar_r1", "Lightbar R1", 3.0),
        ("spacer_lb2", "", 0.6),
    ],
]

DEFAULT_CONFIG = {
    "idle_timeout_sec": 600,       # 10 minutes
    "idle_fade_sec": 4.0,          # Slow fade-off duration
    "fps": 40,
    "groups": {
        "lightbar":     {"default": "#000000", "active": "#000000", "fade_sec": 0.1},
        "fn_key":       {"default": "#0088FF", "active": "#0088FF", "fade_sec": 0.1},
        "mouse":        {"default": "#0055FF", "active": "#FF0055", "fade_sec": 1.2},
        "kb":           {"default": "#00AA88", "active": "#FFFFFF", "fade_sec": 1.0},
        "special_kb":   {"default": "#AA00FF", "active": "#FFCC00", "fade_sec": 1.5},
        "most_used_kb": {"default": "#FF3300", "active": "#00FF66", "fade_sec": 0.8},
    },
    "key_groups": {
        "w": "most_used_kb", "a": "most_used_kb", "s": "most_used_kb", "d": "most_used_kb",
        "space": "most_used_kb", "shift": "most_used_kb",
        "esc": "special_kb", "tab": "special_kb", "enter": "special_kb", "caps_lock": "special_kb",
        "vol_down": "special_kb", "vol_up": "special_kb", "mute": "special_kb", "fan": "special_kb", "rog": "special_kb",
        "fn": "fn_key"
    }
}

# --- Zero-CPU OS Idle Detection (Windows Win32 API) ---
class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

def get_os_idle_seconds() -> float:
    if os.name == "nt":
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0.0, millis / 1000.0)
    return 0.0

# --- Color Helpers ---
def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))

def lerp_rgb(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float, brightness: float = 1.0) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    r = int((c1[0] + (c2[0] - c1[0]) * t) * brightness)
    g = int((c1[1] + (c2[1] - c1[1]) * t) * brightness)
    b = int((c1[2] + (c2[2] - c1[2]) * t) * brightness)
    return (r, g, b)

def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"


# --- Hardware Key Parser (Hardware Scancodes & Extended Keys) ---
def parse_raw_key(vk: int, scan: int, flags: int) -> str | None:
    is_extended = bool(flags & 1)

    # 1. Virtual Key Explicit Priority (Disambiguates Pause vs NumLock and PrtSc vs Multiply)
    if vk == 19:
        return "pause"
    if vk == 44:
        return "print_screen"
    if vk == 144:
        return "num_lock"
    if vk == 106:
        return "num_multiply"
    if vk == 107:
        return "num_add"
    if vk == 109:
        return "num_subtract"
    if vk == 110:
        return "num_decimal"

    # 2. Extended Key Disambiguation (Separate Numpad Enter vs Main Enter, arrows, right modifiers)
    if is_extended:
        if scan == 0x1C or vk == 13:
            return "num_enter"
        if scan == 0x35 or vk == 111:
            return "num_divide"
        if vk == 38 or scan == 0x48:
            return "up"
        if vk == 40 or scan == 0x50:
            return "down"
        if vk == 37 or scan == 0x4B:
            return "left"
        if vk == 39 or scan == 0x4D:
            return "right"
        if vk == 46 or scan == 0x53:
            return "delete"
        if vk == 36 or scan == 0x47:
            return "home"
        if vk == 165 or scan == 0x38:
            return "alt_gr"
        if vk == 163 or scan == 0x1D:
            return "ctrl_r"
        if vk == 91:
            return "cmd"

    # 3. Hardware Scan Code Table (Physical keyboard matrix positions immune to software remapping)
    scancode_map = {
        0x29: "`",           # Physical key left of '1' (Grave / Backtick position)
        0x02: "1", 0x03: "2", 0x04: "3", 0x05: "4", 0x06: "5",
        0x07: "6", 0x08: "7", 0x09: "8", 0x0A: "9", 0x0B: "0",
        0x0C: "-",           # Physical key right of '0' (Main board minus)
        0x0D: "=",           # Physical key right of '-' (Equal)
        0x0E: "backspace",
        0x0F: "tab",
        0x10: "q", 0x11: "w", 0x12: "e", 0x13: "r", 0x14: "t",
        0x15: "y", 0x16: "u", 0x17: "i", 0x18: "o", 0x19: "p",
        0x1A: "[",           # Physical key right of 'P'
        0x1B: "]",           # Physical key right of '['
        0x2B: "\\",          # Physical key right of ']' (Backslash)
        0x3A: "caps_lock",
        0x1E: "a", 0x1F: "s", 0x20: "d", 0x21: "f", 0x22: "g",
        0x23: "h", 0x24: "j", 0x25: "k", 0x26: "l",
        0x27: ";",           # Physical key right of 'L'
        0x28: "'",           # Physical key right of ';'
        0x1C: "enter",       # Main board enter
        0x2A: "shift",       # Left shift
        0x56: "iso_extra",   # Physical ISO key between Left Shift and Z (< >)
        0x2C: "z", 0x2D: "x", 0x2E: "c", 0x2F: "v", 0x30: "b",
        0x31: "n", 0x32: "m",
        0x33: ",",
        0x34: ".",
        0x35: "/",           # Physical key right of '.' (Slash)
        0x36: "shift_r",     # Right shift
        0x1D: "ctrl_l",      # Left ctrl
        0x38: "alt_l",       # Left alt
        0x39: "space",

        # Numpad (non-extended scan codes)
        0x52: "num_0",
        0x4F: "num_1",
        0x50: "num_2",
        0x51: "num_3",
        0x4B: "num_4",
        0x4C: "num_5",
        0x4D: "num_6",
        0x47: "num_7",
        0x48: "num_8",
        0x49: "num_9",
        0x4E: "num_add",
        0x4A: "num_subtract",
        0x37: "num_multiply",
        0x53: "num_decimal",
        0x45: "num_lock",
    }
    if scan in scancode_map:
        return scancode_map[scan]

    # 4. Virtual Key fallback
    if 112 <= vk <= 123:
        return f"f{vk - 111}"
    if 96 <= vk <= 105:
        return f"num_{vk - 96}"

    vk_map = {
        27: "esc",
        44: "print_screen",
        19: "pause",
        174: "vol_down",
        175: "vol_up",
        173: "mute",
        131: "mute",        # VK_F20 (ASUS Mic Mute)
        182: "rog",         # Launch App 1 (Armoury Crate)
        183: "fan",         # Launch App 2 (Fan Mode)
        226: "iso_extra",   # VK_OEM_102 (< >)
    }
    return vk_map.get(vk, None)


# --- Core Animation & OpenRGB Engine ---
class LEDAnimationEngine:
    def __init__(self):
        self.lock = threading.Lock()
        self.config = self.load_json(CONFIG_FILE, DEFAULT_CONFIG)
        self.stats = self.load_json(STATS_FILE, {})
        
        # Ensure fn_key group exists in loaded config
        if "fn_key" not in self.config.setdefault("groups", {}):
            self.config["groups"]["fn_key"] = {"default": "#0088FF", "active": "#0088FF", "fade_sec": 0.1}
        if "fn" not in self.config.setdefault("key_groups", {}):
            self.config["key_groups"]["fn"] = "fn_key"
        
        # Runtime state: key_id -> float [0.0 to 1.0] representing active fade progress
        self.key_heat: dict[str, float] = {}
        self.mouse_heat: float = 0.0
        self.global_brightness: float = 1.0
        self.last_event_time: float = time.monotonic()
        
        # Real-time live color preview override: tuple[group_name, "default" | "active"] | None
        self.preview_override: tuple[str, str] | None = None
        
        self.running = True
        self.wake_event = threading.Event()
        self.wake_event.set()

        # AltGr debouncing timer for Windows synthetic VK_LCONTROL
        self._ctrl_l_timer: threading.Timer | None = None

        # OpenRGB Hardware References
        self.client = None
        self.kb_dev = None
        self.mouse_dev = None
        self.lightbar_devs = []
        self.kb_led_lookup: dict[str, list[int]] = {}
        self.led_index_to_key_id: dict[int, str] = {}
        self.connect_openrgb()

        # Start hotkey listeners (G-Helper log stream + WMI event query)
        self.start_hotkey_listeners()

    def load_json(self, path, default):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return json.loads(json.dumps(default))

    def save_config(self):
        with self.lock:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config, f, indent=2)
        self.wake_event.set()

    def save_stats(self):
        with self.lock:
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, indent=2)

    def connect_openrgb(self):
        if not OPENRGB_AVAILABLE:
            logging.warning("[OpenRGB] Library not available, running in offline mode.")
            return

        while self.running:
            try:
                logging.info("[OpenRGB] Connecting to OpenRGB server (127.0.0.1:6742)...")
                client = OpenRGBClient(address="127.0.0.1", port=6742, name="kb-effect")
                with self.lock:
                    self.client = client
                    self.kb_dev = None
                    self.mouse_dev = None
                    self.lightbar_devs.clear()
                    self.kb_led_lookup.clear()
                    self.led_index_to_key_id.clear()

                    for dev in self.client.devices:
                        dev.set_mode("Direct")
                        # Identify keyboard controller (including laptop controller with type 19 / LAPTOP)
                        if (dev.type == DeviceType.KEYBOARD or 
                            getattr(dev.type, "value", dev.type) == 19 or 
                            dev.name == "G733PZ" or 
                            any(z.name.lower() == "keyboard" for z in dev.zones)):
                            self.kb_dev = dev
                            self._build_kb_led_lookup(dev)
                        elif dev.type == DeviceType.MOUSE:
                            self.mouse_dev = dev
                        elif dev.type in (DeviceType.LIGHT, DeviceType.LEDSTRIP):
                            self.lightbar_devs.append(dev)
                            lb_rgb = hex_to_rgb(self.config["groups"]["lightbar"]["default"])
                            dev.set_colors([RGBColor(*lb_rgb)] * len(dev.leds), fast=True)

                dev_names = [d.name for d in self.client.devices]
                logging.info(f"[OpenRGB] Connected successfully. Devices detected: {dev_names}")
                self.wake_event.set()
                return
            except Exception as e:
                logging.warning(f"[OpenRGB] Connection failed ({e}). Retrying in 3 seconds...")
                for _ in range(6):
                    if not self.running:
                        return
                    time.sleep(0.5)

    def _build_kb_led_lookup(self, kb_dev):
        """Maps normalized key names to OpenRGB LED indices and builds reverse index map."""
        self.kb_led_lookup.clear()
        self.led_index_to_key_id.clear()

        aliases = {
            "media volume -": "vol_down",
            "media volume +": "vol_up",
            "media mute": "mute",
            "fan": "fan",
            "rog": "rog",
            "escape": "esc",
            "pause/break": "pause",
            "print screen": "print_screen",
            "left shift": "shift",
            "right shift": "shift_r",
            "left control": "ctrl_l",
            "right control": "ctrl_r",
            "left alt": "alt_l",
            "right alt": "alt_gr",
            "left windows": "cmd",
            "left fn": "fn",
            "caps lock": "caps_lock",
            "return": "enter",
            "back": "backspace",
            "up arrow": "up",
            "down arrow": "down",
            "left arrow": "left",
            "right arrow": "right",
            "\\ (ansi)": "\\",
            "\\ (iso)": "iso_extra",
            "num lock": "num_lock",
            "number pad /": "num_divide",
            "number pad *": "num_multiply",
            "number pad -": "num_subtract",
            "number pad +": "num_add",
            "number pad enter": "num_enter",
            "number pad .": "num_decimal",
            "number pad 0": "num_0",
            "number pad 1": "num_1",
            "number pad 2": "num_2",
            "number pad 3": "num_3",
            "number pad 4": "num_4",
            "number pad 5": "num_5",
            "number pad 6": "num_6",
            "number pad 7": "num_7",
            "number pad 8": "num_8",
            "number pad 9": "num_9",
            "lightbar l1": "lightbar_l1",
            "lightbar l2": "lightbar_l2",
            "lightbar l3": "lightbar_l3",
            "lightbar r3": "lightbar_r3",
            "lightbar r2": "lightbar_r2",
            "lightbar r1": "lightbar_r1",
        }

        for idx, led in enumerate(kb_dev.leds):
            clean = led.name.lower().replace("key: ", "").strip()
            key_id = aliases.get(clean, clean)
            self.kb_led_lookup.setdefault(key_id, []).append(idx)
            self.led_index_to_key_id[idx] = key_id

    def start_hotkey_listeners(self):
        """Starts listeners for ASUS hotkeys: G-Helper real-time event tail + WMI event query."""
        def _ghelper_tail_worker():
            log_path = os.path.expandvars(r"%APPDATA%\GHelper\log.txt")
            if not os.path.exists(log_path):
                return
            try:
                with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(0, 2)  # Seek to end
                    while self.running:
                        line = f.readline()
                        if line:
                            line_s = line.strip()
                            if "Key: 124" in line_s:
                                self._trigger_key_press("mute")
                            elif "Key: 181" in line_s:
                                self._trigger_key_press("fan")
                            elif "Key: 56" in line_s:
                                self._trigger_key_press("rog")
                        else:
                            time.sleep(0.02)
            except Exception:
                pass

        def _wmi_worker():
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                wmi = win32com.client.GetObject('winmgmts://./root/wmi')
                watcher = wmi.ExecNotificationQuery("SELECT * FROM AsusAtkWmiEvent")
                while self.running:
                    try:
                        event = watcher.NextEvent(1000)
                        if event:
                            eid = int(event.Properties_("EventID").Value)
                            if eid == 124:
                                self._trigger_key_press("mute")
                            elif eid in (181, 174, 88):
                                self._trigger_key_press("fan")
                            elif eid == 56:
                                self._trigger_key_press("rog")
                    except Exception:
                        pass
                pythoncom.CoUninitialize()
            except Exception:
                pass

        t_gh = threading.Thread(target=_ghelper_tail_worker, daemon=True)
        t_gh.start()
        t_wmi = threading.Thread(target=_wmi_worker, daemon=True)
        t_wmi.start()

    def get_key_group(self, key_id: str) -> str:
        if key_id in self.config["key_groups"]:
            return self.config["key_groups"][key_id]
        if key_id.startswith("lightbar_"):
            return "lightbar"
        if key_id == "fn":
            return "fn_key"
        return "kb"

    def handle_raw_key_event(self, vk: int, scan: int, flags: int, is_down: bool):
        if not is_down:
            return

        key_id = parse_raw_key(vk, scan, flags)
        if not key_id:
            return

        # Filter AltGr synthetic Left Ctrl: Windows sends fake VK_LCONTROL immediately before VK_RMENU.
        if key_id == "ctrl_l":
            if self._ctrl_l_timer:
                self._ctrl_l_timer.cancel()
            self._ctrl_l_timer = threading.Timer(0.035, self._trigger_key_press, args=["ctrl_l"])
            self._ctrl_l_timer.daemon = True
            self._ctrl_l_timer.start()
            return

        if key_id == "alt_gr":
            if self._ctrl_l_timer:
                self._ctrl_l_timer.cancel()
                self._ctrl_l_timer = None

        self._trigger_key_press(key_id)

    def _trigger_key_press(self, key_id: str):
        if not key_id:
            return
        with self.lock:
            self.key_heat[key_id] = 1.0
            self.stats[key_id] = self.stats.get(key_id, 0) + 1
            self.last_event_time = time.monotonic()
        self.wake_event.set()

    def on_mouse_click(self, x, y, button, pressed):
        if pressed:
            with self.lock:
                self.mouse_heat = 1.0
                btn_id = f"mouse_{button.name}"
                self.stats[btn_id] = self.stats.get(btn_id, 0) + 1
                self.last_event_time = time.monotonic()
            self.wake_event.set()

    def get_current_key_rgb(self, key_id: str) -> tuple[int, int, int]:
        grp_name = self.get_key_group(key_id)
        grp = self.config["groups"].get(grp_name, self.config["groups"]["kb"])

        # Live Color Preview Override (preview any color including active fade-in)
        if self.preview_override and self.preview_override[0] == grp_name:
            p_kind = self.preview_override[1]
            p_hex = grp.get(p_kind, grp["default"])
            p_col = hex_to_rgb(p_hex)
            return lerp_rgb(p_col, p_col, 1.0, self.global_brightness)

        c_def = hex_to_rgb(grp["default"])
        c_act = hex_to_rgb(grp["active"])
        heat = self.key_heat.get(key_id, 0.0)
        return lerp_rgb(c_def, c_act, heat, self.global_brightness)

    def get_current_mouse_rgb(self) -> tuple[int, int, int]:
        grp = self.config["groups"]["mouse"]

        # Live Color Preview Override
        if self.preview_override and self.preview_override[0] == "mouse":
            p_kind = self.preview_override[1]
            p_hex = grp.get(p_kind, grp["default"])
            p_col = hex_to_rgb(p_hex)
            return lerp_rgb(p_col, p_col, 1.0, self.global_brightness)

        c_def = hex_to_rgb(grp["default"])
        c_act = hex_to_rgb(grp["active"])
        return lerp_rgb(c_def, c_act, self.mouse_heat, self.global_brightness)

    def render_loop(self):
        last_time = time.perf_counter()
        last_stats_save = time.monotonic()

        while self.running:
            now = time.perf_counter()
            dt = min(0.1, now - last_time)
            last_time = now

            # Check OS-wide idle time
            os_idle = get_os_idle_seconds()
            if os_idle == 0.0 and os.name != "nt":
                os_idle = time.monotonic() - self.last_event_time

            idle_timeout = self.config["idle_timeout_sec"]
            idle_fade = max(0.1, self.config["idle_fade_sec"])
            animating = False

            with self.lock:
                # 1. Idle Brightness Logic
                if os_idle < idle_timeout:
                    if self.global_brightness < 1.0:
                        self.global_brightness = 1.0
                        animating = True
                else:
                    over_idle = os_idle - idle_timeout
                    target_b = max(0.0, 1.0 - (over_idle / idle_fade))
                    if abs(target_b - self.global_brightness) > 0.005:
                        self.global_brightness = target_b
                        animating = True
                    else:
                        self.global_brightness = target_b

                # 2. Decay Active Keys
                expired_keys = []
                for k, heat in self.key_heat.items():
                    if heat > 0.005:
                        grp = self.config["groups"][self.get_key_group(k)]
                        fade_sec = max(0.05, float(grp["fade_sec"]))
                        self.key_heat[k] = max(0.0, heat - (dt / fade_sec))
                        animating = True
                    else:
                        expired_keys.append(k)
                for k in expired_keys:
                    del self.key_heat[k]

                # 3. Decay Mouse
                if self.mouse_heat > 0.005:
                    m_fade = max(0.05, float(self.config["groups"]["mouse"]["fade_sec"]))
                    self.mouse_heat = max(0.0, self.mouse_heat - (dt / m_fade))
                    animating = True
                else:
                    self.mouse_heat = 0.0

            # 4. Push Hardware Update
            if animating or self.wake_event.is_set():
                self.wake_event.clear()
                self._push_to_openrgb()

            # Periodic stats flush
            if time.monotonic() - last_stats_save > 300:
                self.save_stats()
                last_stats_save = time.monotonic()

            # Adaptive Sleep
            if animating:
                time.sleep(1.0 / max(15, self.config.get("fps", 40)))
            else:
                self.wake_event.wait(timeout=0.2)
                last_time = time.perf_counter()

    def _push_to_openrgb(self):
        if not self.client:
            return
        try:
            # Update Keyboard and integrated Lightbar
            if self.kb_dev:
                kb_colors = []
                for idx in range(len(self.kb_dev.leds)):
                    key_id = self.led_index_to_key_id.get(idx)
                    # Non-existent lid and keystone LEDs, plus unused ISO hash key remain off
                    if key_id in ("rog logo", "vertical cut left", "vertical cut right", "keystone", "#"):
                        kb_colors.append(RGBColor(0, 0, 0))
                    elif key_id:
                        r, g, b = self.get_current_key_rgb(key_id)
                        kb_colors.append(RGBColor(r, g, b))
                    else:
                        def_kb_rgb = lerp_rgb(
                            hex_to_rgb(self.config["groups"]["kb"]["default"]),
                            (0, 0, 0), 0.0, self.global_brightness
                        )
                        kb_colors.append(RGBColor(*def_kb_rgb))
                self.kb_dev.set_colors(kb_colors, fast=True)

            # Update Mouse
            if self.mouse_dev:
                mr, mg, mb = self.get_current_mouse_rgb()
                self.mouse_dev.set_colors([RGBColor(mr, mg, mb)] * len(self.mouse_dev.leds), fast=True)

            # Update Standalone Lightbars (if any)
            for lb in self.lightbar_devs:
                if self.preview_override and self.preview_override[0] == "lightbar":
                    lb_hex = self.config["groups"]["lightbar"].get(self.preview_override[1], self.config["groups"]["lightbar"]["default"])
                else:
                    lb_hex = self.config["groups"]["lightbar"]["default"]
                lb_rgb = hex_to_rgb(lb_hex)
                r, g, b = lerp_rgb(lb_rgb, (0, 0, 0), 0.0, self.global_brightness)
                lb.set_colors([RGBColor(r, g, b)] * len(lb.leds), fast=True)
        except Exception as e:
            logging.warning(f"[OpenRGB] Hardware communication failed: {e}. Reconnecting...")
            self._handle_disconnect()

    def _handle_disconnect(self):
        with self.lock:
            if self.client:
                try:
                    self.client.disconnect()
                except Exception:
                    pass
            self.client = None
            self.kb_dev = None
            self.mouse_dev = None
            self.lightbar_devs.clear()
            self.kb_led_lookup.clear()
            self.led_index_to_key_id.clear()
        self.connect_openrgb()


# --- Real-Time Live Color Picker Dialog ---
class LiveColorPicker(tk.Toplevel):
    PRESETS = [
        "#FFFFFF", "#D4D4D8", "#71717A", "#000000",
        "#EF4444", "#DC2626", "#F97316", "#F59E0B",
        "#EAB308", "#84CC16", "#10B981", "#059669",
        "#06B6D4", "#0EA5E9", "#3B82F6", "#8B5CF6",
        "#D946EF", "#EC4899", "#F43F5E", "#00FF66"
    ]

    def __init__(self, parent_ui: "ConfiguratorUI", group: str, kind: str):
        super().__init__(parent_ui.root)
        self.ui = parent_ui
        self.engine = parent_ui.engine
        self.group = group
        self.kind = kind

        self.original_color = self.engine.config["groups"][group][kind]
        self.current_color = self.original_color
        self.updating_internally = False

        # Activate real-time engine preview override immediately
        with self.engine.lock:
            self.engine.preview_override = (group, kind)
        self.engine.wake_event.set()

        self.title(f"Live Color Picker — {group.upper()} ({kind.upper()})")
        self.geometry("460x520")
        self.resizable(False, False)
        self.configure(bg="#18181B")
        self.transient(parent_ui.root)
        self.grab_set()

        self._build_widgets()
        self.protocol("WM_DELETE_WINDOW", self.on_cancel)
        self.bind("<Escape>", lambda e: self.on_cancel())
        self.bind("<Return>", lambda e: self.on_apply())

    def _build_widgets(self):
        # 1. Header with live status indicator
        header = tk.Frame(self, bg="#27272A", padx=14, pady=10)
        header.pack(fill="x")

        tk.Label(
            header,
            text=f"Group: {self.group}  |  Field: {self.kind.upper()}",
            fg="#60A5FA", bg="#27272A", font=("Segoe UI", 10, "bold")
        ).pack(anchor="w")

        info_text = "● Live preview is active on screen map & OpenRGB hardware LEDs."
        if self.kind == "active":
            info_text += "\n  (Previewing press/fade-in color live without striking keys!)"
        tk.Label(
            header, text=info_text, fg="#34D399" if self.kind == "active" else "#A1A1AA",
            bg="#27272A", font=("Segoe UI", 8), justify="left"
        ).pack(anchor="w", pady=(3, 0))

        # 2. Color comparison swatches
        swatch_frame = tk.Frame(self, bg="#18181B", padx=14, pady=10)
        swatch_frame.pack(fill="x")

        # Original swatch
        box_orig = tk.Frame(swatch_frame, bg="#27272A", padx=8, pady=6, bd=1, relief="solid")
        box_orig.pack(side="left", expand=True, fill="both", padx=(0, 6))
        tk.Label(box_orig, text="Original Color", fg="#A1A1AA", bg="#27272A", font=("Segoe UI", 8)).pack()
        self.lbl_orig_swatch = tk.Label(
            box_orig, text=self.original_color, bg=self.original_color,
            fg=self._text_contrast(self.original_color), width=16, height=2,
            font=("Segoe UI", 9, "bold")
        )
        self.lbl_orig_swatch.pack(pady=4)

        # Live swatch
        box_live = tk.Frame(swatch_frame, bg="#27272A", padx=8, pady=6, bd=1, relief="solid")
        box_live.pack(side="right", expand=True, fill="both", padx=(6, 0))
        tk.Label(box_live, text="Live Preview", fg="#34D399", bg="#27272A", font=("Segoe UI", 8, "bold")).pack()
        self.lbl_live_swatch = tk.Label(
            box_live, text=self.current_color, bg=self.current_color,
            fg=self._text_contrast(self.current_color), width=16, height=2,
            font=("Segoe UI", 9, "bold")
        )
        self.lbl_live_swatch.pack(pady=4)

        # 3. RGB Sliders
        sliders_box = tk.Frame(self, bg="#27272A", padx=14, pady=10, bd=1, relief="solid")
        sliders_box.pack(fill="x", padx=14, pady=4)

        orig_rgb = hex_to_rgb(self.original_color)
        self.val_r = tk.IntVar(value=orig_rgb[0])
        self.val_g = tk.IntVar(value=orig_rgb[1])
        self.val_b = tk.IntVar(value=orig_rgb[2])

        self._create_slider_row(sliders_box, "Red", "#EF4444", self.val_r)
        self._create_slider_row(sliders_box, "Green", "#10B981", self.val_g)
        self._create_slider_row(sliders_box, "Blue", "#3B82F6", self.val_b)

        # 4. Hex Input Row
        hex_row = tk.Frame(self, bg="#18181B", padx=14, pady=6)
        hex_row.pack(fill="x")

        tk.Label(hex_row, text="Hex Code:", fg="#A1A1AA", bg="#18181B", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.hex_entry_var = tk.StringVar(value=self.current_color)
        self.hex_entry = tk.Entry(
            hex_row, textvariable=self.hex_entry_var, width=10,
            bg="#27272A", fg="#FFFFFF", insertbackground="#FFFFFF", font=("Segoe UI", 9, "bold")
        )
        self.hex_entry.pack(side="left", padx=8)
        self.hex_entry.bind("<KeyRelease>", self._on_hex_entry_change)

        # 5. Preset Palette Swatches
        presets_box = tk.Frame(self, bg="#18181B", padx=14, pady=4)
        presets_box.pack(fill="x")
        tk.Label(presets_box, text="Quick Presets:", fg="#A1A1AA", bg="#18181B", font=("Segoe UI", 8)).pack(anchor="w")

        palette_frame = tk.Frame(presets_box, bg="#18181B")
        palette_frame.pack(fill="x", pady=2)

        for col_idx, hex_p in enumerate(self.PRESETS[:10]):
            btn = tk.Button(
                palette_frame, bg=hex_p, width=3, height=1, relief="flat", bd=1,
                command=lambda c=hex_p: self._set_hex(c)
            )
            btn.grid(row=0, column=col_idx, padx=2, pady=2)

        for col_idx, hex_p in enumerate(self.PRESETS[10:]):
            btn = tk.Button(
                palette_frame, bg=hex_p, width=3, height=1, relief="flat", bd=1,
                command=lambda c=hex_p: self._set_hex(c)
            )
            btn.grid(row=1, column=col_idx, padx=2, pady=2)

        # 6. Bottom action buttons
        actions = tk.Frame(self, bg="#18181B", padx=14, pady=10)
        actions.pack(fill="x", side="bottom")

        btn_apply = tk.Button(
            actions, text="✔ Apply & Save", bg="#2563EB", fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=14, pady=5,
            command=self.on_apply
        )
        btn_apply.pack(side="right", padx=4)

        if self.kind == "active":
            btn_test = tk.Button(
                actions, text="⚡ Test Fade Flash", bg="#8B5CF6", fg="#FFFFFF",
                font=("Segoe UI", 9), relief="flat", padx=10, pady=5,
                command=self.test_fade
            )
            btn_test.pack(side="right", padx=4)

        btn_cancel = tk.Button(
            actions, text="✖ Cancel", bg="#3F3F46", fg="#FFFFFF",
            font=("Segoe UI", 9), relief="flat", padx=12, pady=5,
            command=self.on_cancel
        )
        btn_cancel.pack(side="right", padx=4)

    def _create_slider_row(self, parent, label_text, accent_color, var):
        row = tk.Frame(parent, bg="#27272A")
        row.pack(fill="x", pady=2)

        tk.Label(row, text=label_text, fg=accent_color, bg="#27272A", width=6, anchor="w", font=("Segoe UI", 9, "bold")).pack(side="left")

        scale = tk.Scale(
            row, from_=0, to=255, orient="horizontal", variable=var,
            showvalue=False, bg="#27272A", fg="#FFFFFF", highlightthickness=0,
            troughcolor="#18181B", activebackground=accent_color,
            command=lambda v: self._on_slider_change()
        )
        scale.pack(side="left", fill="x", expand=True, padx=6)

        sp = tk.Spinbox(
            row, from_=0, to=255, textvariable=var, width=4,
            bg="#18181B", fg="#FFFFFF", insertbackground="#FFFFFF",
            command=self._on_slider_change
        )
        sp.pack(side="left")
        sp.bind("<KeyRelease>", lambda e: self._on_slider_change())

    def _text_contrast(self, hex_color: str) -> str:
        try:
            r, g, b = hex_to_rgb(hex_color)
            brightness = (r * 299 + g * 587 + b * 114) / 1000
            return "#000000" if brightness > 128 else "#FFFFFF"
        except Exception:
            return "#FFFFFF"

    def _on_slider_change(self):
        if self.updating_internally:
            return
        r = max(0, min(255, self.val_r.get()))
        g = max(0, min(255, self.val_g.get()))
        b = max(0, min(255, self.val_b.get()))
        hex_code = rgb_to_hex((r, g, b))
        self._apply_live_color(hex_code, update_sliders=False)

    def _on_hex_entry_change(self, event=None):
        raw = self.hex_entry_var.get().strip()
        if not raw.startswith("#"):
            raw = "#" + raw
        if len(raw) == 7:
            try:
                hex_to_rgb(raw)
                self._set_hex(raw.upper())
            except Exception:
                pass

    def _set_hex(self, hex_color: str):
        self._apply_live_color(hex_color, update_sliders=True)

    def _apply_live_color(self, hex_code: str, update_sliders: bool = False):
        self.current_color = hex_code
        self.updating_internally = True
        try:
            if update_sliders:
                r, g, b = hex_to_rgb(hex_code)
                self.val_r.set(r)
                self.val_g.set(g)
                self.val_b.set(b)

            self.hex_entry_var.set(hex_code)
            self.lbl_live_swatch.configure(
                text=hex_code, bg=hex_code, fg=self._text_contrast(hex_code)
            )

            # Push live change into engine config
            with self.engine.lock:
                self.engine.config["groups"][self.group][self.kind] = hex_code
                if self.group in ("fn_key", "lightbar"):
                    other = "active" if self.kind == "default" else "default"
                    self.engine.config["groups"][self.group][other] = hex_code
                    if (self.group, other) in self.ui.color_btns:
                        self.ui.color_btns[(self.group, other)].configure(bg=hex_code, text=hex_code)

            if (self.group, self.kind) in self.ui.color_btns:
                self.ui.color_btns[(self.group, self.kind)].configure(bg=hex_code, text=hex_code)

            # Wake up engine to render immediately to hardware and visual map
            self.engine.wake_event.set()
        finally:
            self.updating_internally = False

    def test_fade(self):
        # Temporarily clear preview override to demonstrate active -> default fade
        with self.engine.lock:
            self.engine.preview_override = None
            for k in self.ui.key_buttons:
                if self.engine.get_key_group(k) == self.group:
                    self.engine.key_heat[k] = 1.0
            if self.group == "mouse":
                self.engine.mouse_heat = 1.0
            self.engine.last_event_time = time.monotonic()
        self.engine.wake_event.set()

        # Restore preview override after fade duration
        fade_time = float(self.engine.config["groups"][self.group]["fade_sec"])
        self.after(int(fade_time * 1000 + 150), self._restore_preview_override)

    def _restore_preview_override(self):
        if self.winfo_exists():
            with self.engine.lock:
                self.engine.preview_override = (self.group, self.kind)
            self.engine.wake_event.set()

    def on_apply(self):
        with self.engine.lock:
            self.engine.preview_override = None
        self.engine.save_config()
        self.engine.wake_event.set()
        self.destroy()

    def on_cancel(self):
        # Revert to original color
        with self.engine.lock:
            self.engine.preview_override = None
            self.engine.config["groups"][self.group][self.kind] = self.original_color
            if self.group in ("fn_key", "lightbar"):
                other = "active" if self.kind == "default" else "default"
                self.engine.config["groups"][self.group][other] = self.original_color
                if (self.group, other) in self.ui.color_btns:
                    self.ui.color_btns[(self.group, other)].configure(bg=self.original_color, text=self.original_color)

        if (self.group, self.kind) in self.ui.color_btns:
            self.ui.color_btns[(self.group, self.kind)].configure(bg=self.original_color, text=self.original_color)

        self.engine.wake_event.set()
        self.destroy()


# --- Visual Map & Heatmap Configurator GUI ---
class ConfiguratorUI:
    def __init__(self, engine: LEDAnimationEngine):
        self.engine = engine
        self.root = tk.Tk()
        self.root.title("OpenRGB Interactive Group Mapper & Keystroke Heatmap")
        self.root.geometry("1300x820")
        self.root.configure(bg="#18181B")

        self.selected_brush = tk.StringVar(value="most_used_kb")
        self.live_preview = tk.BooleanVar(value=True)
        self.key_buttons: dict[str, tk.Button] = {}
        self.heatmap_buttons: dict[str, tuple[tk.Label, str]] = {}

        self._build_ui()
        self._refresh_ui_loop()

    def _build_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook", background="#18181B", borderwidth=0)
        style.configure("TNotebook.Tab", background="#27272A", foreground="#E4E4E7", padding=[14, 6])
        style.map("TNotebook.Tab", background=[("selected", "#3B82F6")], foreground=[("selected", "#FFFFFF")])

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=12, pady=12)

        # Tab 1: Visual Group Map & Animation Settings
        tab_map = tk.Frame(notebook, bg="#18181B")
        notebook.add(tab_map, text=" 1. Visual Map & Group Colors ")

        # Tab 2: Keypress Counter & Heatmap
        tab_heat = tk.Frame(notebook, bg="#18181B")
        notebook.add(tab_heat, text=" 2. Keypress Counter Heatmap ")

        self._build_map_tab(tab_map)
        self._build_heatmap_tab(tab_heat)
        notebook.bind("<<NotebookTabChanged>>", lambda e: self.update_heatmap_view())

    def _build_map_tab(self, parent):
        top_frame = tk.Frame(parent, bg="#27272A", padx=12, pady=10)
        top_frame.pack(fill="x", padx=10, pady=8)

        tk.Label(top_frame, text="Select Brush & Configure Groups:", fg="#FFFFFF", bg="#27272A", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, columnspan=5, sticky="w", pady=(0, 6))

        headers = ["Group (Click to Paint Keys)", "Default Color", "Active (Press) Color", "Fade Time (s)"]
        for col, text in enumerate(headers):
            tk.Label(top_frame, text=text, fg="#A1A1AA", bg="#27272A", font=("Segoe UI", 9)).grid(row=1, column=col, padx=8, sticky="w")

        self.fade_vars = {}
        self.color_btns = {}

        paintable_groups = ["kb", "special_kb", "most_used_kb", "lightbar", "fn_key", "mouse"]
        labels = {
            "kb": "Standard KB (kb)",
            "special_kb": "Special KB (special_kb)",
            "most_used_kb": "Most Used KB (most_used_kb)",
            "lightbar": "Lightbar (Front Edge)",
            "fn_key": "Fn Key (Static Color)",
            "mouse": "Mouse (Click Trigger)"
        }

        for idx, grp in enumerate(paintable_groups, start=2):
            g_cfg = self.engine.config["groups"][grp]
            
            # Radio brush selector for paintable groups
            if grp in ("kb", "special_kb", "most_used_kb", "lightbar", "fn_key"):
                rb = tk.Radiobutton(
                    top_frame, text=labels[grp], variable=self.selected_brush, value=grp,
                    bg="#27272A", fg="#FFFFFF", selectcolor="#3B82F6", activebackground="#27272A"
                )
                rb.grid(row=idx, column=0, sticky="w", padx=6, pady=2)
            else:
                tk.Label(top_frame, text=labels[grp], fg="#D4D4D8", bg="#27272A").grid(row=idx, column=0, sticky="w", padx=24, pady=2)

            # Default Color Picker
            btn_def = tk.Button(
                top_frame, text=g_cfg["default"], bg=g_cfg["default"], fg="#FFFFFF", width=10,
                relief="flat", command=lambda g=grp: self.pick_color(g, "default")
            )
            btn_def.grid(row=idx, column=1, padx=8, pady=2)

            # Active Color Picker
            btn_act = tk.Button(
                top_frame, text=g_cfg["active"], bg=g_cfg["active"], fg="#000000", width=10,
                relief="flat", command=lambda g=grp: self.pick_color(g, "active")
            )
            btn_act.grid(row=idx, column=2, padx=8, pady=2)
            self.color_btns[(grp, "default")] = btn_def
            self.color_btns[(grp, "active")] = btn_act

            # Fade Duration Spinbox (disabled for static single-color groups)
            var = tk.DoubleVar(value=g_cfg["fade_sec"])
            self.fade_vars[grp] = var
            if grp in ("lightbar", "fn_key"):
                sp = tk.Spinbox(top_frame, from_=0.1, to=10.0, increment=0.1, textvariable=var, width=7, state="disabled")
            else:
                sp = tk.Spinbox(top_frame, from_=0.1, to=10.0, increment=0.1, textvariable=var, width=7, command=self.apply_timing_changes)
                sp.bind("<Return>", lambda e: self.apply_timing_changes())
            sp.grid(row=idx, column=3, padx=8, pady=2)

        # Global Inactivity Controls on Right Side
        idle_frame = tk.Frame(top_frame, bg="#18181B", padx=12, pady=8)
        idle_frame.grid(row=1, column=4, rowspan=5, padx=20, sticky="ns")

        tk.Label(idle_frame, text="PC Inactivity Sleep", fg="#60A5FA", bg="#18181B", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        
        tk.Label(idle_frame, text="Timeout (sec):", fg="#A1A1AA", bg="#18181B").pack(anchor="w", pady=(4, 0))
        self.idle_timeout_var = tk.IntVar(value=self.engine.config["idle_timeout_sec"])
        tk.Spinbox(idle_frame, from_=5, to=3600, increment=30, textvariable=self.idle_timeout_var, width=10, command=self.apply_timing_changes).pack(anchor="w")

        tk.Label(idle_frame, text="Slow Fade-Off (sec):", fg="#A1A1AA", bg="#18181B").pack(anchor="w", pady=(4, 0))
        self.idle_fade_var = tk.DoubleVar(value=self.engine.config["idle_fade_sec"])
        tk.Spinbox(idle_frame, from_=0.5, to=30.0, increment=0.5, textvariable=self.idle_fade_var, width=10, command=self.apply_timing_changes).pack(anchor="w")

        tk.Checkbutton(
            idle_frame, text="Live Animation Preview", variable=self.live_preview,
            bg="#18181B", fg="#E4E4E7", selectcolor="#27272A"
        ).pack(anchor="w", pady=(8, 0))

        # Interactive Visual Keyboard Map + Mouse Widget
        kb_container = tk.Frame(parent, bg="#18181B")
        kb_container.pack(fill="both", expand=True, padx=10, pady=6)

        map_hdr = tk.Frame(kb_container, bg="#18181B")
        map_hdr.pack(fill="x", pady=(0, 6))

        tk.Label(
            map_hdr,
            text="Click any key or lightbar segment to assign it to the selected Brush Group (Live preview shows real-time colors):",
            fg="#A1A1AA", bg="#18181B"
        ).pack(side="left")

        tk.Button(
            map_hdr, text="🎨 Open Layout Editor", bg="#2563EB", fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"), relief="flat", padx=10, pady=2,
            command=self.open_layout_editor
        ).pack(side="right")

        board_and_mouse = tk.Frame(kb_container, bg="#18181B")
        board_and_mouse.pack(fill="x")

        layout_coords = load_layout_coords()
        if layout_coords:
            max_x = max(d["x"] + d["w"] for d in layout_coords.values()) + 16
            max_y = max(d["y"] + d["h"] for d in layout_coords.values()) + 16
            kb_frame = tk.Frame(board_and_mouse, bg="#09090B", width=max_x, height=max_y, bd=1, relief="solid")
            kb_frame.pack(side="left", padx=(0, 16))
            kb_frame.pack_propagate(False)

            for key_id, d in layout_coords.items():
                lbl = d.get("label", key_id)
                btn = tk.Button(
                    kb_frame, text=lbl,
                    fg="#FFFFFF", bg="#27272A", relief="raised", bd=2,
                    font=("Segoe UI", 8, "bold" if d["w"] >= 40 else "normal"),
                    command=lambda k=key_id: self.assign_key_to_brush(k)
                )
                btn.place(x=d["x"], y=d["y"], width=d["w"], height=d["h"])
                self.key_buttons[key_id] = btn
        else:
            kb_frame = tk.Frame(board_and_mouse, bg="#09090B", padx=10, pady=10, bd=1, relief="solid")
            kb_frame.pack(side="left", padx=(0, 16))

            for row in KB_LAYOUT:
                r_frame = tk.Frame(kb_frame, bg="#09090B")
                r_frame.pack(anchor="w", pady=2)
                for key_id, label, width_mult in row:
                    if not key_id or key_id.startswith("spacer_"):
                        spacer_px = int(width_mult * 36)
                        spacer = tk.Frame(r_frame, bg="#09090B", width=spacer_px, height=32)
                        spacer.pack(side="left")
                        continue
                    btn = tk.Button(
                        r_frame, text=label, width=int(width_mult * 5), height=2,
                        fg="#FFFFFF", bg="#27272A", relief="raised", bd=2,
                        font=("Segoe UI", 8, "bold"),
                        command=lambda k=key_id: self.assign_key_to_brush(k)
                    )
                    btn.pack(side="left", padx=2)
                    self.key_buttons[key_id] = btn

        # Visual Mouse Status Box
        mouse_frame = tk.Frame(board_and_mouse, bg="#09090B", padx=16, pady=16, bd=1, relief="solid")
        mouse_frame.pack(side="left", fill="y")
        tk.Label(mouse_frame, text="MOUSE ZONE", fg="#A1A1AA", bg="#09090B", font=("Segoe UI", 9, "bold")).pack()
        self.mouse_preview_box = tk.Label(
            mouse_frame, text="Left / Right Click\nInstant Color + Fade",
            width=16, height=7, bg="#0055FF", fg="#FFFFFF", font=("Segoe UI", 9, "bold")
        )
        self.mouse_preview_box.pack(pady=12)
        self.status_lbl = tk.Label(mouse_frame, text="State: Active (100%)", fg="#34D399", bg="#09090B", font=("Segoe UI", 8))
        self.status_lbl.pack()

    def open_layout_editor(self):
        script = os.path.join(SCRIPT_DIR, "layout_editor.py")
        subprocess.Popen([sys.executable, script])

    def _build_heatmap_tab(self, parent):
        top_bar = tk.Frame(parent, bg="#27272A", padx=12, pady=8)
        top_bar.pack(fill="x", padx=10, pady=8)

        self.total_presses_lbl = tk.Label(top_bar, text="Total Recorded Presses: 0", fg="#FFFFFF", bg="#27272A", font=("Segoe UI", 11, "bold"))
        self.total_presses_lbl.pack(side="left")

        tk.Button(
            top_bar, text="Reset Counter Stats", bg="#EF4444", fg="#FFFFFF", relief="flat", padx=10,
            command=self.reset_heatmap
        ).pack(side="right", padx=6)

        tk.Button(
            top_bar, text="Auto-Assign Top 8 Keys to 'most_used_kb'", bg="#3B82F6", fg="#FFFFFF", relief="flat", padx=10,
            command=self.auto_assign_top_keys
        ).pack(side="right", padx=6)

        # Heatmap Keyboard Grid
        layout_coords = load_layout_coords()
        if layout_coords:
            max_x = max(d["x"] + d["w"] for d in layout_coords.values()) + 16
            max_y = max(d["y"] + d["h"] for d in layout_coords.values()) + 16
            hm_frame = tk.Frame(parent, bg="#09090B", width=max_x, height=max_y, bd=1, relief="solid")
            hm_frame.pack(padx=10, pady=10, anchor="w")
            hm_frame.pack_propagate(False)

            for key_id, d in layout_coords.items():
                lbl = d.get("label", key_id)
                w_lbl = tk.Label(
                    hm_frame, text=f"{lbl}\n0",
                    fg="#E4E4E7", bg="#1E1E24", bd=1, relief="solid",
                    font=("Segoe UI", 8)
                )
                w_lbl.place(x=d["x"], y=d["y"], width=d["w"], height=d["h"])
                self.heatmap_buttons[key_id] = (w_lbl, lbl)
        else:
            hm_frame = tk.Frame(parent, bg="#09090B", padx=12, pady=12)
            hm_frame.pack(padx=10, pady=10, anchor="w")

            for row in KB_LAYOUT:
                r_frame = tk.Frame(hm_frame, bg="#09090B")
                r_frame.pack(anchor="w", pady=2)
                for key_id, label, width_mult in row:
                    if not key_id or key_id.startswith("spacer_"):
                        spacer_px = int(width_mult * 36)
                        spacer = tk.Frame(r_frame, bg="#09090B", width=spacer_px, height=32)
                        spacer.pack(side="left")
                        continue
                    w_lbl = tk.Label(
                        r_frame, text=f"{label}\n0", width=int(width_mult * 5), height=2,
                        fg="#E4E4E7", bg="#1E1E24", bd=1, relief="solid", font=("Segoe UI", 8)
                    )
                    w_lbl.pack(side="left", padx=2)
                    self.heatmap_buttons[key_id] = (w_lbl, label)

        self.mouse_stats_lbl = tk.Label(parent, text="Mouse Clicks — Left: 0 | Right: 0 | Middle: 0", fg="#A1A1AA", bg="#18181B", font=("Segoe UI", 10))
        self.mouse_stats_lbl.pack(anchor="w", padx=14, pady=6)

    def pick_color(self, group: str, kind: str):
        LiveColorPicker(self, group, kind)

    def apply_timing_changes(self):
        with self.engine.lock:
            for grp, var in self.fade_vars.items():
                try:
                    self.engine.config["groups"][grp]["fade_sec"] = float(var.get())
                except ValueError:
                    pass
            try:
                self.engine.config["idle_timeout_sec"] = int(self.idle_timeout_var.get())
                self.engine.config["idle_fade_sec"] = float(self.idle_fade_var.get())
            except ValueError:
                pass
        self.engine.save_config()

    def assign_key_to_brush(self, key_id: str):
        brush = self.selected_brush.get()
        with self.engine.lock:
            if brush == "kb" and not key_id.startswith("lightbar_"):
                self.engine.config["key_groups"].pop(key_id, None)
            else:
                self.engine.config["key_groups"][key_id] = brush
        self.engine.save_config()

    def update_heatmap_view(self):
        stats = self.engine.stats
        kb_counts = [stats.get(k, 0) for row in KB_LAYOUT for k, _, _ in row if k and not k.startswith("spacer_")]
        max_count = max(kb_counts) if kb_counts and max(kb_counts) > 0 else 1
        total = sum(stats.values())
        self.total_presses_lbl.configure(text=f"Total Recorded Presses: {total:,}")

        for key_id, (widget, label) in self.heatmap_buttons.items():
            cnt = stats.get(key_id, 0)
            ratio = cnt / max_count if cnt > 0 else 0.0
            if cnt == 0:
                bg_hex = "#1E1E24"
            else:
                rgb = lerp_rgb((30, 64, 175), (239, 68, 68), ratio)
                bg_hex = rgb_to_hex(rgb)
            widget.configure(text=f"{label}\n{cnt}", bg=bg_hex)

        ml = stats.get("mouse_left", 0)
        mr = stats.get("mouse_right", 0)
        mm = stats.get("mouse_middle", 0)
        self.mouse_stats_lbl.configure(text=f"Mouse Clicks — Left: {ml:,}  |  Right: {mr:,}  |  Middle: {mm:,}")

    def auto_assign_top_keys(self):
        valid_keys = {
            k for row in KB_LAYOUT for k, _, _ in row
            if k and not k.startswith("spacer_") and not k.startswith("lightbar_")
        }
        ranked = sorted(
            [(k, v) for k, v in self.engine.stats.items() if k in valid_keys and v > 0],
            key=lambda x: x[1], reverse=True
        )[:8]
        with self.engine.lock:
            for k, _ in ranked:
                self.engine.config["key_groups"][k] = "most_used_kb"
        self.engine.save_config()

    def reset_heatmap(self):
        with self.engine.lock:
            self.engine.stats.clear()
        self.engine.save_stats()
        self.update_heatmap_view()

    def _refresh_ui_loop(self):
        if self.live_preview.get():
            for key_id, btn in self.key_buttons.items():
                rgb = self.engine.get_current_key_rgb(key_id)
                grp = self.engine.get_key_group(key_id)
                border_color = {
                    "kb": "#27272A",
                    "special_kb": "#F59E0B",
                    "most_used_kb": "#10B981",
                    "lightbar": "#3B82F6",
                    "fn_key": "#8B5CF6"
                }.get(grp, "#27272A")
                btn.configure(bg=rgb_to_hex(rgb), highlightbackground=border_color)

            m_rgb = self.engine.get_current_mouse_rgb()
            self.mouse_preview_box.configure(bg=rgb_to_hex(m_rgb))

            pct = int(self.engine.global_brightness * 100)
            idle_s = int(get_os_idle_seconds())
            self.status_lbl.configure(text=f"Brightness: {pct}% (Idle: {idle_s}s)")

        self.root.after(50, self._refresh_ui_loop)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        self.engine.save_config()
        self.engine.save_stats()
        self.engine.running = False
        self.engine.wake_event.set()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description="OpenRGB Keyboard & Mouse LED Animation Service")
    parser.add_argument("--gui", action="store_true", help="Launch interactive Configurator UI")
    args = parser.parse_args()

    acquire_mutex()
    logging.info("kb-effect starting...")

    engine = LEDAnimationEngine()

    def win32_event_filter(msg, data):
        is_down = msg in (0x0100, 0x0104)
        engine.handle_raw_key_event(data.vkCode, data.scanCode, data.flags, is_down)
        return True

    kb_listener = keyboard.Listener(
        on_press=lambda k: None,
        win32_event_filter=win32_event_filter
    )
    ms_listener = mouse.Listener(on_click=engine.on_mouse_click)
    kb_listener.daemon = True
    ms_listener.daemon = True
    kb_listener.start()
    ms_listener.start()

    if args.gui:
        logging.info("Starting in GUI Configurator mode.")
        render_thread = threading.Thread(target=engine.render_loop, daemon=True)
        render_thread.start()
        ui = ConfiguratorUI(engine)
        ui.run()
    else:
        logging.info("Starting in headless background mode (main thread running render loop).")
        try:
            engine.render_loop()
        except (KeyboardInterrupt, SystemExit):
            logging.info("kb-effect interrupted. Exiting.")
        finally:
            engine.running = False
            engine.wake_event.set()
            kb_listener.stop()
            ms_listener.stop()
            engine.save_config()
            engine.save_stats()
            logging.info("kb-effect shutdown complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        logging.error(traceback.format_exc())
