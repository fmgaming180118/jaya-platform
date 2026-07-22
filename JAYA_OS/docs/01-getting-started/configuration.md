# Configuration — JAYA_OS

## Environment Variables

| Variable | Default | Deskripsi |
|---|---|---|
| `JAYA_OS_FEATURES_DIR` | `./features` | Direktori feature packages |
| `JAYA_OS_MOUNT_TIMEOUT` | `10` | Detik timeout mount feature |
| `JAYA_OS_MAX_FEATURES` | `50` | Max concurrent mounted features |
| `JAYA_OS_SANDBOX_TIMEOUT` | `30` | Detik timeout sandbox execution |
| `JAYA_OS_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `JAYA_OS_ALLOWED_IMPORTS` | `json,math,datetime,typing,dataclasses,enum,collections` | Whitelist imports untuk sandbox |
| `JAYA_OS_BLOCKED_BUILTINS` | `__import__,eval,exec,open,compile,input` | Diblokir di sandbox |

---

## Config Files

### `config/os.yaml` (Optional)
```yaml
features_dir: "./features"
mount_timeout: 10
max_features: 50
sandbox:
  timeout: 30
  allowed_imports:
    - "json"
    - "math"
    - "datetime"
    - "typing"
    - "dataclasses"
    - "enum"
    - "collections"
  blocked_builtins:
    - "__import__"
    - "eval"
    - "exec"
    - "open"
    - "compile"
    - "input"

ipc:
  default_timeout: 5.0
  max_message_size: 1048576  # 1MB

window_manager:
  default_width: "800px"
  default_height: "600px"
  theme: "light"
```

### `config/sandbox.yaml` (Optional)
```yaml
# Sandbox policy per feature
default_policy:
  cpu_limit_percent: 50
  memory_limit_mb: 200
  network_allowed: false
  filesystem_read: ["./features", "./data"]
  filesystem_write: ["./features/tmp"]

feature_overrides:
  "network_feature":
    network_allowed: true
    allowed_domains: ["api.github.com", "api.nvidia.com"]
```

---

## Feature Compiler Config

Di `src/os_kernel/feature_compiler.py`:

```python
FeatureCompiler(
    sandbox_timeout=30,           # Detik timeout sandbox exec
    allowed_imports=[             # Whitelist imports
        "json", "math", "datetime", "typing",
        "dataclasses", "enum", "collections"
    ],
    blocked_builtins=[            # Diblokir di sandbox
        "__import__", "eval", "exec", "open", "compile"
    ]
)
```

---

## JayaBridge Config

Di `src/os_kernel/feature_bridge.py`:

```python
JayaBridge(
    features_dir="./features",    # Direktori feature packages
    mount_timeout=10,             # Detik timeout mount
    max_features=50               # Max concurrent features
)
```

---

## Intent → UI Pipeline Config

Di `src/os_kernel/intent_to_ui.py`:

```python
IntentToUIPipeline(
    bridge=JayaBridge(...),
    intent_engine=IntentEngine(...)
)
```

Built-in templates (10):
| Template | Patterns | Parameters |
|---|---|---|
| `login_dialog` | "show login", "sign in" | title, show_remember, fields[] |
| `dashboard` | "create dashboard", "show metrics" | metrics[], charts[], refresh_interval |
| `settings_dialog` | "open settings", "preferences" | categories[], show_reset |
| `file_explorer` | "show files", "browse files" | root_path, show_hidden, multi_select |
| `chat_interface` | "chat with", "open chat" | history[], placeholder, send_action |
| `confirm_dialog` | "confirm", "are you sure" | message, title, danger, actions[] |
| `progress_dialog` | "show progress", "loading" | title, max_value, cancellable, show_eta |
| `list_view` | "list", "show list" | items[], columns[], multi_select, actions[] |
| `form` | "create form", "input form" | fields[], submit_action, validation |
| `generic_dialog` | "dialog", "popup", "modal" | title, content_widgets[], actions[] |

---

## Window Manager Config

Di `src/os_kernel/window_manager.py`:

```python
WindowManager(
    default_width="800px",
    default_height="600px",
    theme="light",              # "light" | "dark" | "auto"
    animations_enabled=True,
    max_windows=20
)
```

---

## IPC Config

Di `src/os_kernel/ipc.py`:

```python
IPCChannel(
    channel_name="jaya_os",
    default_timeout=5.0,        # Detik
    max_message_size=1048576    # 1MB
)
```

---

## Resource Monitor Integration (from JAYA_CORE)

JAYA_OS menggunakan `ResourceMonitor` dari JAYA_CORE untuk adaptive behavior:

```python
from src.brain_v2.organism.resource_monitor import ResourceMonitor, get_readings

# Readings: {'cpu_pct': float, 'mem_pct': float, 'battery_pct': float}
readings = get_readings()

# Auto-adjust feature behavior based on resources
if readings['cpu_pct'] > 85:
    # Reduce feature complexity, disable animations
    pass
```

---

## Logging Config

Default: `logging.basicConfig(level=INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")`

Override via `JAYA_OS_LOG_LEVEL` atau di code:
```python
import logging
logging.getLogger("FeatureCompiler").setLevel(logging.DEBUG)
logging.getLogger("JayaBridge").setLevel(logging.DEBUG)
```

---

## Ringkasan File Config Penting

| File | Lokasi | Jenis |
|---|---|---|
| `config/os.yaml` | `JAYA_OS/` (optional) | Main config |
| `config/sandbox.yaml` | `JAYA_OS/` (optional) | Sandbox policy |
| `pyrightconfig.json` | `JAYA_OS/` | Type checking |
| `.env` | `JAYA_OS/` (optional) | Env overrides |