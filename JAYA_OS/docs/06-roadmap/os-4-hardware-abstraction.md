# Phase OS-4: Hardware Abstraction Layer

## Objective
Cross-platform hardware abstraction: display, input, audio, storage, network, power management.

---

## Scope
- **In scope**: Display, Input, Audio, Storage, Network, Power abstractions with platform backends
- **Out of scope**: Sandbox Hardening (OS-5)

---

## Prerequisites
- ✅ OS-1 complete (standalone JAYA_OS package)
- ✅ OS-2 complete (WindowManager + Widget Runtime)
- ✅ OS-3 complete (IPC Bridge + Protocol)

---

## Deliverables

| # | Deliverable | File/Location | Status |
|---|---|---|---|
| 1 | Display Abstraction | `src/jaya_os/hardware/display.py` | 🔄 Planned |
| 2 | Input Abstraction | `src/jaya_os/hardware/input.py` | 🔄 Planned |
| 3 | Audio Abstraction | `src/jaya_os/hardware/audio.py` | 🔄 Planned |
| 4 | Storage Abstraction | `src/jaya_os/hardware/storage.py` | 🔄 Planned |
| 5 | Network Abstraction | `src/jaya_os/hardware/network.py` | 🔄 Planned |
| 6 | Power Management | `src/jaya_os/hardware/power.py` | 🔄 Planned |
| 7 | Platform Backends (Win32, X11/Wayland, Cocoa) | `src/jaya_os/hardware/backends/` | 🔄 Planned |
| 8 | Hardware Manager (unified API) | `src/jaya_os/hardware/manager.py` | 🔄 Planned |
| 9 | Unit tests | `tests/test_hardware_*.py` | 🔄 Planned |
| 10 | Integration tests | `tests/test_hardware_integration.py` | 🔄 Planned |

---

## Technical Implementation

### 4.1 Hardware Manager (Unified API)

```python
# src/jaya_os/hardware/manager.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
import sys

@dataclass
class HardwareManager:
    display: "DisplayManager"
    input: "InputManager"
    audio: "AudioManager"
    storage: "StorageManager"
    network: "NetworkManager"
    power: "PowerManager"
    
    @classmethod
    def create(cls) -> "HardwareManager":
        """Create hardware manager with platform-appropriate backends."""
        if sys.platform == "win32":
            from jaya_os.hardware.backends.win32 import (
                Win32DisplayManager, Win32InputManager, Win32AudioManager,
                Win32StorageManager, Win32NetworkManager, Win32PowerManager
            )
            return cls(
                display=Win32DisplayManager(),
                input=Win32InputManager(),
                audio=Win32AudioManager(),
                storage=Win32StorageManager(),
                network=Win32NetworkManager(),
                power=Win32PowerManager()
            )
        elif sys.platform.startswith("linux"):
            from jaya_os.hardware.backends.linux import (
                LinuxDisplayManager, LinuxInputManager, LinuxAudioManager,
                LinuxStorageManager, LinuxNetworkManager, LinuxPowerManager
            )
            return cls(
                display=LinuxDisplayManager(),
                input=LinuxInputManager(),
                audio=LinuxAudioManager(),
                storage=LinuxStorageManager(),
                network=LinuxNetworkManager(),
                power=LinuxPowerManager()
            )
        elif sys.platform == "darwin":
            from jaya_os.hardware.backends.macos import (
                MacOSDisplayManager, MacOSInputManager, MacOSAudioManager,
                MacOSStorageManager, MacOSNetworkManager, MacOSPowerManager
            )
            return cls(
                display=MacOSDisplayManager(),
                input=MacOSInputManager(),
                audio=MacOSAudioManager(),
                storage=MacOSStorageManager(),
                network=MacOSNetworkManager(),
                power=MacOSPowerManager()
            )
        else:
            raise NotImplementedError(f"Platform {sys.platform} not supported")
    
    def get_capabilities(self) -> Dict[str, Any]:
        """Get combined hardware capabilities."""
        return {
            "display": self.display.get_capabilities(),
            "input": self.input.get_capabilities(),
            "audio": self.audio.get_capabilities(),
            "storage": self.storage.get_capabilities(),
            "network": self.network.get_capabilities(),
            "power": self.power.get_capabilities(),
        }
```

### 4.2 Display Abstraction

```python
# src/jaya_os/hardware/display.py
from dataclasses import dataclass
from typing import List, Optional, Tuple
from abc import ABC, abstractmethod
from enum import Enum

class Rotation(Enum):
    NORMAL = "normal"
    ROTATE_90 = "rotate_90"
    ROTATE_180 = "rotate_180"
    ROTATE_270 = "rotate_270"

@dataclass
class MonitorInfo:
    id: str
    name: str
    width: int
    height: int
    x: int
    y: int
    is_primary: bool
    dpi_scale: float
    refresh_rate: int
    rotation: Rotation
    physical_width_mm: int
    physical_height_mm: int

@dataclass
class Resolution:
    width: int
    height: int
    refresh_rate: int

@dataclass
class DisplayCapabilities:
    monitors: List[MonitorInfo]
    max_resolution: Resolution
    supports_hdr: bool
    supports_vrr: bool  # Variable Refresh Rate
    supports_multiple: bool

class DisplayManager(ABC):
    @abstractmethod
    def get_monitors(self) -> List[MonitorInfo]:
        """Get all connected monitors."""
        pass
    
    @abstractmethod
    def get_primary_monitor(self) -> MonitorInfo:
        """Get primary monitor."""
        pass
    
    @abstractmethod
    def get_monitor(self, monitor_id: str) -> Optional[MonitorInfo]:
        """Get specific monitor by ID."""
        pass
    
    @abstractmethod
    def set_resolution(self, monitor_id: str, resolution: Resolution) -> bool:
        """Set monitor resolution."""
        pass
    
    @abstractmethod
    def set_refresh_rate(self, monitor_id: str, refresh_rate: int) -> bool:
        """Set monitor refresh rate."""
        pass
    
    @abstractmethod
    def set_rotation(self, monitor_id: str, rotation: Rotation) -> bool:
        """Set monitor rotation."""
        pass
    
    @abstractmethod
    def set_position(self, monitor_id: str, x: int, y: int) -> bool:
        """Set monitor position (for multi-monitor)."""
        pass
    
    @abstractmethod
    def get_dpi_scale(self, monitor_id: str) -> float:
        """Get DPI scale factor for monitor."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> DisplayCapabilities:
        """Get display capabilities."""
        pass
    
    @abstractmethod
    def on_monitor_change(self, callback: callable) -> None:
        """Register callback for monitor connect/disconnect."""
        pass
```

#### Win32 Display Backend
```python
# src/jaya_os/hardware/backends/win32/display.py
import ctypes
from ctypes import wintypes
from jaya_os.hardware.display import DisplayManager, MonitorInfo, Resolution, DisplayCapabilities, Rotation

user32 = ctypes.windll.user32
dxgi = ctypes.windll.dxgi
d3d11 = ctypes.windll.d3d11

class Win32DisplayManager(DisplayManager):
    def get_monitors(self) -> List[MonitorInfo]:
        monitors = []
        
        def monitor_enum_proc(hmonitor, hdc, lprect, lparam):
            info = ctypes.MONITORINFOEXW()
            info.cbSize = ctypes.sizeof(ctypes.MONITORINFOEXW)
            user32.GetMonitorInfoW(hmonitor, ctypes.byref(info))
            
            # Get DPI
            dpi_x = ctypes.c_uint()
            dpi_y = ctypes.c_uint()
            user32.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
            dpi_scale = dpi_x.value / 96.0
            
            rect = info.rcMonitor
            work_rect = info.rcWork
            
            monitor = MonitorInfo(
                id=str(hmonitor),
                name=info.szDevice.decode('utf-16le').rstrip('\x00'),
                width=rect.right - rect.left,
                height=rect.bottom - rect.top,
                x=rect.left,
                y=rect.top,
                is_primary=bool(info.dwFlags & 1),
                dpi_scale=dpi_scale,
                refresh_rate=self._get_refresh_rate(info.szDevice),
                rotation=Rotation.NORMAL,
                physical_width_mm=0,  # Would need EDID
                physical_height_mm=0
            )
            monitors.append(monitor)
            return True
        
        user32.EnumDisplayMonitors(None, None, ctypes.MONITORENUMPROC(monitor_enum_proc), 0)
        return monitors
    
    def _get_refresh_rate(self, device_name) -> int:
        # Use DEVMODE to get refresh rate
        devmode = ctypes.DEVMODEW()
        devmode.dmSize = ctypes.sizeof(ctypes.DEVMODEW)
        if user32.EnumDisplaySettingsW(device_name, -1, ctypes.byref(devmode)):
            return devmode.dmDisplayFrequency
        return 60
    
    def get_primary_monitor(self) -> MonitorInfo:
        monitors = self.get_monitors()
        for m in monitors:
            if m.is_primary:
                return m
        return monitors[0] if monitors else None
    
    def get_monitor(self, monitor_id: str) -> Optional[MonitorInfo]:
        for m in self.get_monitors():
            if m.id == monitor_id:
                return m
        return None
    
    def set_resolution(self, monitor_id: str, resolution: Resolution) -> bool:
        # Use ChangeDisplaySettingsEx
        devmode = ctypes.DEVMODEW()
        devmode.dmSize = ctypes.sizeof(ctypes.DEVMODEW)
        devmode.dmPelsWidth = resolution.width
        devmode.dmPelsHeight = resolution.height
        devmode.dmDisplayFrequency = resolution.refresh_rate
        devmode.dmFields = 0x00080000 | 0x00100000 | 0x00400000  # DM_PELSWIDTH | DM_PELSHEIGHT | DM_DISPLAYFREQUENCY
        
        result = user32.ChangeDisplaySettingsExW(
            monitor_id, ctypes.byref(devmode), None, 0, None
        )
        return result == 0  # DISP_CHANGE_SUCCESSFUL
    
    def set_refresh_rate(self, monitor_id: str, refresh_rate: int) -> bool:
        # Get current resolution, change only refresh rate
        monitor = self.get_monitor(monitor_id)
        if monitor:
            return self.set_resolution(monitor_id, Resolution(
                monitor.width, monitor.height, refresh_rate
            ))
        return False
    
    def set_rotation(self, monitor_id: str, rotation: Rotation) -> bool:
        # Would need to use DMDO_* constants
        return False  # Not implemented
    
    def set_position(self, monitor_id: str, x: int, y: int) -> bool:
        # Would need to use CDS_SETRECT
        return False  # Not implemented
    
    def get_dpi_scale(self, monitor_id: str) -> float:
        monitor = self.get_monitor(monitor_id)
        return monitor.dpi_scale if monitor else 1.0
    
    def get_capabilities(self) -> DisplayCapabilities:
        monitors = self.get_monitors()
        max_w = max(m.width for m in monitors) if monitors else 0
        max_h = max(m.height for m in monitors) if monitors else 0
        max_rr = max(m.refresh_rate for m in monitors) if monitors else 60
        
        return DisplayCapabilities(
            monitors=monitors,
            max_resolution=Resolution(max_w, max_h, max_rr),
            supports_hdr=False,  # Would need DXGI check
            supports_vrr=False,  # Would need DXGI check
            supports_multiple=len(monitors) > 1
        )
```

#### Linux Display Backend
```python
# src/jaya_os/hardware/backends/linux/display.py
import subprocess
import json
from jaya_os.hardware.display import DisplayManager, MonitorInfo, Resolution, DisplayCapabilities, Rotation

class LinuxDisplayManager(DisplayManager):
    def get_monitors(self) -> List[MonitorInfo]:
        # Use xrandr or wlr-randr for Wayland
        try:
            # Try xrandr first
            result = subprocess.run(["xrandr", "--query"], capture_output=True, text=True)
            return self._parse_xrandr(result.stdout)
        except:
            # Fallback to wlr-randr for Wayland
            try:
                result = subprocess.run(["wlr-randr", "--json"], capture_output=True, text=True)
                return self._parse_wlr_randr(json.loads(result.stdout))
            except:
                return []
    
    def _parse_xrandr(self, output: str) -> List[MonitorInfo]:
        monitors = []
        current_monitor = None
        
        for line in output.split('\n'):
            if ' connected' in line:
                parts = line.split()
                name = parts[0]
                is_primary = 'primary' in line
                
                # Parse resolution
                for part in parts:
                    if 'x' in part and '+' in part:
                        # Format: 1920x1080+0+0
                        res_pos = part.split('+')
                        res = res_pos[0].split('x')
                        width = int(res[0])
                        height = int(res[1])
                        x = int(res_pos[1]) if len(res_pos) > 1 else 0
                        y = int(res_pos[2]) if len(res_pos) > 2 else 0
                        
                        monitor = MonitorInfo(
                            id=name,
                            name=name,
                            width=width,
                            height=height,
                            x=x,
                            y=y,
                            is_primary=is_primary,
                            dpi_scale=1.0,  # Would need xrdb or xft.dpi
                            refresh_rate=60,  # Would need parsing
                            rotation=Rotation.NORMAL,
                            physical_width_mm=0,
                            physical_height_mm=0
                        )
                        monitors.append(monitor)
                        break
        
        return monitors
    
    def _parse_wlr_randr(self, data: dict) -> List[MonitorInfo]:
        monitors = []
        for output in data.get("outputs", []):
            monitor = MonitorInfo(
                id=output["name"],
                name=output["name"],
                width=output["current_mode"]["width"],
                height=output["current_mode"]["height"],
                x=output["position"]["x"],
                y=output["position"]["y"],
                is_primary=False,  # Would need to check
                dpi_scale=output.get("scale", 1.0),
                refresh_rate=int(output["current_mode"]["refresh"]),
                rotation=Rotation.NORMAL,
                physical_width_mm=output.get("physical_width", 0),
                physical_height_mm=output.get("physical_height", 0)
            )
            monitors.append(monitor)
        return monitors
    
    def get_primary_monitor(self) -> MonitorInfo:
        monitors = self.get_monitors()
        for m in monitors:
            if m.is_primary:
                return m
        return monitors[0] if monitors else None
    
    def get_monitor(self, monitor_id: str) -> Optional[MonitorInfo]:
        for m in self.get_monitors():
            if m.id == monitor_id:
                return m
        return None
    
    def set_resolution(self, monitor_id: str, resolution: Resolution) -> bool:
        try:
            subprocess.run([
                "xrandr", "--output", monitor_id,
                "--mode", f"{resolution.width}x{resolution.height}",
                "--rate", str(resolution.refresh_rate)
            ], check=True)
            return True
        except:
            return False
    
    def set_refresh_rate(self, monitor_id: str, refresh_rate: int) -> bool:
        monitor = self.get_monitor(monitor_id)
        if monitor:
            return self.set_resolution(monitor_id, Resolution(
                monitor.width, monitor.height, refresh_rate
            ))
        return False
    
    def set_rotation(self, monitor_id: str, rotation: Rotation) -> bool:
        rotation_map = {
            Rotation.NORMAL: "normal",
            Rotation.ROTATE_90: "left",
            Rotation.ROTATE_180: "inverted",
            Rotation.ROTATE_270: "right"
        }
        try:
            subprocess.run([
                "xrandr", "--output", monitor_id,
                "--rotate", rotation_map[rotation]
            ], check=True)
            return True
        except:
            return False
    
    def set_position(self, monitor_id: str, x: int, y: int) -> bool:
        try:
            subprocess.run([
                "xrandr", "--output", monitor_id,
                "--pos", f"{x}x{y}"
            ], check=True)
            return True
        except:
            return False
    
    def get_dpi_scale(self, monitor_id: str) -> float:
        # Would need to parse xrdb or xft.dpi
        return 1.0
    
    def get_capabilities(self) -> DisplayCapabilities:
        monitors = self.get_monitors()
        max_w = max(m.width for m in monitors) if monitors else 0
        max_h = max(m.height for m in monitors) if monitors else 0
        max_rr = max(m.refresh_rate for m in monitors) if monitors else 60
        
        return DisplayCapabilities(
            monitors=monitors,
            max_resolution=Resolution(max_w, max_h, max_rr),
            supports_hdr=False,
            supports_vrr=False,
            supports_multiple=len(monitors) > 1
        )
```

### 4.3 Input Abstraction

```python
# src/jaya_os/hardware/input.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Callable
from abc import ABC, abstractmethod
from enum import Enum

class Key(Enum):
    # Letters
    A = "a"; B = "b"; C = "c"; D = "d"; E = "e"; F = "f"
    G = "g"; H = "h"; I = "i"; J = "j"; K = "k"; L = "l"
    M = "m"; N = "n"; O = "o"; P = "p"; Q = "q"; R = "r"
    S = "s"; T = "t"; U = "u"; V = "v"; W = "w"; X = "x"
    Y = "y"; Z = "z"
    # Numbers
    NUM_0 = "0"; NUM_1 = "1"; NUM_2 = "2"; NUM_3 = "3"; NUM_4 = "4"
    NUM_5 = "5"; NUM_6 = "6"; NUM_7 = "7"; NUM_8 = "8"; NUM_9 = "9"
    # Function keys
    F1 = "f1"; F2 = "f2"; F3 = "f3"; F4 = "f4"; F5 = "f5"
    F6 = "f6"; F7 = "f7"; F8 = "f8"; F9 = "f9"; F10 = "f10"
    F11 = "f11"; F12 = "f12"
    # Modifiers
    SHIFT = "shift"; CTRL = "ctrl"; ALT = "alt"; META = "meta"
    # Special
    SPACE = "space"; ENTER = "enter"; TAB = "tab"; ESC = "escape"
    BACKSPACE = "backspace"; DELETE = "delete"; INSERT = "insert"
    HOME = "home"; END = "end"; PAGE_UP = "page_up"; PAGE_DOWN = "page_down"
    UP = "up"; DOWN = "down"; LEFT = "left"; RIGHT = "right"
    # Numpad
    NUMPAD_0 = "numpad_0"; NUMPAD_1 = "numpad_1"; NUMPAD_2 = "numpad_2"
    NUMPAD_3 = "numpad_3"; NUMPAD_4 = "numpad_4"; NUMPAD_5 = "numpad_5"
    NUMPAD_6 = "numpad_6"; NUMPAD_7 = "numpad_7"; NUMPAD_8 = "numpad_8"
    NUMPAD_9 = "numpad_9"; NUMPAD_ENTER = "numpad_enter"
    NUMPAD_DOT = "numpad_dot"; NUMPAD_SLASH = "numpad_slash"
    NUMPAD_ASTERISK = "numpad_*"; NUMPAD_MINUS = "numpad_-"
    NUMPAD_PLUS = "numpad_+"

@dataclass
class KeyboardState:
    pressed_keys: set[Key]
    modifiers: set[Key]  # SHIFT, CTRL, ALT, META

@dataclass
class MouseState:
    x: int
    y: int
    buttons: set[int]  # 1=left, 2=right, 3=middle, 4=back, 5=forward
    wheel_delta: int

@dataclass
class TouchPoint:
    id: int
    x: float
    y: float
    pressure: float
    touch_type: str  # "touch", "pen", "mouse"

@dataclass
class InputCapabilities:
    has_keyboard: bool
    has_mouse: bool
    has_touch: bool
    has_pen: bool
    max_touch_points: int

class InputManager(ABC):
    @abstractmethod
    def get_keyboard_state(self) -> KeyboardState:
        pass
    
    @abstractmethod
    def get_mouse_state(self) -> MouseState:
        pass
    
    @abstractmethod
    def get_touch_state(self) -> List[TouchPoint]:
        pass
    
    @abstractmethod
    def is_key_pressed(self, key: Key) -> bool:
        pass
    
    @abstractmethod
    def is_mouse_button_pressed(self, button: int) -> bool:
        pass
    
    @abstractmethod
    def register_hotkey(self, key: Key, modifiers: List[Key], callback: Callable) -> bool:
        """Register global hotkey."""
        pass
    
    @abstractmethod
    def unregister_hotkey(self, key: Key, modifiers: List[Key]) -> bool:
        pass
    
    @abstractmethod
    def get_capabilities(self) -> InputCapabilities:
        pass
    
    @abstractmethod
    def on_key_event(self, callback: Callable[[Key, bool], None]) -> None:
        """Register callback for key press/release."""
        pass
    
    @abstractmethod
    def on_mouse_event(self, callback: Callable[[MouseState], None]) -> None:
        pass
    
    @abstractmethod
    def on_touch_event(self, callback: Callable[[List[TouchPoint]], None]) -> None:
        pass
```

### 4.4 Audio Abstraction

```python
# src/jaya_os/hardware/audio.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
from enum import Enum

class AudioDeviceType(Enum):
    OUTPUT = "output"
    INPUT = "input"

@dataclass
class AudioDevice:
    id: str
    name: str
    type: AudioDeviceType
    is_default: bool
    sample_rates: List[int]
    channels: int
    latency_ms: float

@dataclass
class AudioFormat:
    sample_rate: int = 44100
    channels: int = 2
    bit_depth: int = 16  # 16, 24, 32
    format: str = "pcm"  # pcm, float

@dataclass
class PlaybackHandle:
    id: str
    device_id: str
    is_playing: bool
    volume: float
    position_ms: int
    duration_ms: int

@dataclass
class AudioCapabilities:
    devices: List[AudioDevice]
    supports_surround: bool
    supports_spatial: bool
    max_channels: int

class AudioManager(ABC):
    @abstractmethod
    def get_devices(self, device_type: Optional[AudioDeviceType] = None) -> List[AudioDevice]:
        pass
    
    @abstractmethod
    def get_default_device(self, device_type: AudioDeviceType) -> Optional[AudioDevice]:
        pass
    
    @abstractmethod
    def play(self, device_id: str, audio_data: bytes, format: AudioFormat) -> PlaybackHandle:
        """Play audio data on device."""
        pass
    
    @abstractmethod
    def stop(self, handle: PlaybackHandle) -> bool:
        pass
    
    @abstractmethod
    def pause(self, handle: PlaybackHandle) -> bool:
        pass
    
    @abstractmethod
    def resume(self, handle: PlaybackHandle) -> bool:
        pass
    
    @abstractmethod
    def set_volume(self, handle: PlaybackHandle, volume: float) -> bool:
        """0.0 to 1.0"""
        pass
    
    @abstractmethod
    def get_position(self, handle: PlaybackHandle) -> int:
        """Get playback position in ms."""
        pass
    
    @abstractmethod
    def seek(self, handle: PlaybackHandle, position_ms: int) -> bool:
        pass
    
    @abstractmethod
    def capture(self, device_id: str, duration_ms: int, format: AudioFormat) -> bytes:
        """Capture audio from input device."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> AudioCapabilities:
        pass
```

### 4.5 Storage Abstraction

```python
# src/jaya_os/hardware/storage.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any, BinaryIO
from abc import ABC, abstractmethod
from enum import Enum

class StorageType(Enum):
    HDD = "hdd"
    SSD = "ssd"
    NVME = "nvme"
    USB = "usb"
    SD = "sd"
    VIRTUAL = "virtual"

@dataclass
class StorageDevice:
    id: str
    name: str
    type: StorageType
    total_bytes: int
    free_bytes: int
    is_removable: bool
    is_system: bool
    filesystem: str
    mount_points: List[str]

@dataclass
class StorageCapabilities:
    devices: List[StorageDevice]
    supports_trim: bool
    supports_encryption: bool
    supports_compression: bool
    max_file_size: int

class StorageManager(ABC):
    @abstractmethod
    def get_devices(self) -> List[StorageDevice]:
        pass
    
    @abstractmethod
    def get_device(self, device_id: str) -> Optional[StorageDevice]:
        pass
    
    @abstractmethod
    def get_free_space(self, path: str) -> int:
        pass
    
    @abstractmethod
    def get_total_space(self, path: str) -> int:
        pass
    
    @abstractmethod
    def read_file(self, path: str) -> bytes:
        pass
    
    @abstractmethod
    def write_file(self, path: str, data: bytes) -> bool:
        pass
    
    @abstractmethod
    def delete_file(self, path: str) -> bool:
        pass
    
    @abstractmethod
    def list_directory(self, path: str) -> List[str]:
        pass
    
    @abstractmethod
    def create_directory(self, path: str) -> bool:
        pass
    
    @abstractmethod
    def get_capabilities(self) -> StorageCapabilities:
        pass
```

### 4.6 Network Abstraction

```python
# src/jaya_os/hardware/network.py
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
from abc import ABC, abstractmethod
from enum import Enum

class NetworkInterfaceType(Enum):
    ETHERNET = "ethernet"
    WIFI = "wifi"
    CELLULAR = "cellular"
    LOOPBACK = "loopback"
    VPN = "vpn"
    VIRTUAL = "virtual"

@dataclass
class NetworkInterface:
    id: str
    name: str
    type: NetworkInterfaceType
    ipv4_addresses: List[str]
    ipv6_addresses: List[str]
    mac_address: str
    is_up: bool
    speed_mbps: int
    mtu: int

@dataclass
class NetworkCapabilities:
    interfaces: List[NetworkInterface]
    supports_ipv6: bool
    supports_dns_over_https: bool
    supports_vpn: bool

class NetworkManager(ABC):
    @abstractmethod
    def get_interfaces(self) -> List[NetworkInterface]:
        pass
    
    @abstractmethod
    def get_interface(self, interface_id: str) -> Optional[NetworkInterface]:
        pass
    
    @abstractmethod
    def get_default_interface(self) -> Optional[NetworkInterface]:
        pass
    
    @abstractmethod
    def http_request(self, method: str, url: str, headers: Dict = None, 
                     body: bytes = None, timeout: float = 30.0) -> Dict:
        """Make HTTP request."""
        pass
    
    @abstractmethod
    def tcp_connect(self, host: str, port: int, timeout: float = 10.0) -> Any:
        """Create TCP connection."""
        pass
    
    @abstractmethod
    def udp_send(self, host: str, port: int, data: bytes) -> bool:
        pass
    
    @abstractmethod
    def dns_resolve(self, hostname: str, record_type: str = "A") -> List[str]:
        pass
    
    @abstractmethod
    def get_capabilities(self) -> NetworkCapabilities:
        pass
```

### 4.7 Power Management

```python
# src/jaya_os/hardware/power.py
from dataclasses import dataclass
from typing import List, Optional, Callable
from abc import ABC, abstractmethod
from enum import Enum

class PowerSource(Enum):
    AC = "ac"
    BATTERY = "battery"
    UPS = "ups"
    UNKNOWN = "unknown"

class PowerState(Enum):
    ACTIVE = "active"
    IDLE = "idle"
    SLEEP = "sleep"
    HIBERNATE = "hibernate"
    SHUTDOWN = "shutdown"

@dataclass
class BatteryInfo:
    present: bool
    percentage: float  # 0.0 to 1.0
    charging: bool
    time_remaining_minutes: Optional[int]
    capacity_mwh: int
    voltage_mv: int
    health: str  # "good", "fair", "poor"

@dataclass
class PowerCapabilities:
    has_battery: bool
    supports_sleep: bool
    supports_hibernate: bool
    supports_wake_on_lan: bool
    can_control_brightness: bool

class PowerManager(ABC):
    @abstractmethod
    def get_power_source(self) -> PowerSource:
        pass
    
    @abstractmethod
    def get_battery_info(self) -> Optional[BatteryInfo]:
        pass
    
    @abstractmethod
    def get_power_state(self) -> PowerState:
        pass
    
    @abstractmethod
    def set_power_state(self, state: PowerState) -> bool:
        pass
    
    @abstractmethod
    def set_brightness(self, level: float) -> bool:
        """0.0 to 1.0"""
        pass
    
    @abstractmethod
    def get_brightness(self) -> float:
        pass
    
    @abstractmethod
    def on_power_change(self, callback: Callable[[PowerSource], None]) -> None:
        """Register callback for power source change."""
        pass
    
    @abstractmethod
    def on_battery_low(self, callback: Callable[[float], None]) -> None:
        """Register callback for low battery."""
        pass
    
    @abstractmethod
    def get_capabilities(self) -> PowerCapabilities:
        pass
```

---

## Platform Backends Structure

```
src/jaya_os/hardware/backends/
├── win32/
│   ├── __init__.py
│   ├── display.py
│   ├── input.py
│   ├── audio.py
│   ├── storage.py
│   ├── network.py
│   └── power.py
├── linux/
│   ├── __init__.py
│   ├── display.py
│   ├── input.py
│   ├── audio.py
│   ├── storage.py
│   ├── network.py
│   └── power.py
└── macos/
    ├── __init__.py
    ├── display.py
    ├── input.py
    ├── audio.py
    ├── storage.py
    ├── network.py
    └── power.py
```

---

## Verification Checklist

### Functional
- [ ] DisplayManager: get_monitors, set_resolution, set_rotation, multi-monitor
- [ ] InputManager: keyboard, mouse, touch, hotkeys
- [ ] AudioManager: play, capture, volume, devices
- [ ] StorageManager: read, write, list, free space
- [ ] NetworkManager: HTTP, TCP, UDP, DNS
- [ ] PowerManager: battery, brightness, sleep, state changes
- [ ] All backends work on respective platforms

### Quality
- [ ] Unit tests for each abstraction
- [ ] Integration tests with real hardware
- [ ] Cross-platform CI (Windows, Linux, macOS)
- [ ] Mock backends for testing

### Performance
- [ ] Display queries < 10ms
- [ ] Input latency < 5ms
- [ ] Audio latency < 20ms
- [ ] Storage I/O near native speed

---

## Success Criteria
- [ ] All 6 hardware abstractions implemented
- [ ] Win32, Linux (X11/Wayland), macOS backends working
- [ ] Unified HardwareManager API
- [ ] Integration with WindowManager, WidgetRuntime
- [ ] ResourceMonitor integration for adaptive behavior

---

## Handoff to OS-5

**Contract**: OS-4 provides:
- HardwareManager with 6 subsystems
- Platform backends for Win32, Linux, macOS
- Capability-based access through proxies
- Resource monitoring integration

**Files for OS-5**:
- `src/jaya_os/sandbox/` (process isolation, WASM, formal verification)

---

## 🔗 Related

- [Architecture Overview](../02-architecture/overview.md)
- [UI Runtime](../03-features/ui-runtime.md)
- [IPC Bridge](../03-features/ipc-bridge.md)
- [Sandbox Security](../03-features/sandbox-security.md)
- [Roadmap Overview](../06-roadmap/README.md)