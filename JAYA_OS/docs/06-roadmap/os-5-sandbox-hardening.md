# Phase OS-5: Sandbox Hardening

## Objective
Progressively harden the sandbox: process isolation, WASM runtime, formal verification, capability-based filesystem.

---

## Scope
- **In scope**: Process isolation, user namespaces, container integration, WASM runtime, formal verification, capability-based FS, network namespaces, audit log integrity
- **Out of scope**: New hardware abstractions (OS-4 complete)

---

## Prerequisites
- ✅ OS-1 complete (standalone JAYA_OS package)
- ✅ OS-2 complete (WindowManager + Widget Runtime)
- ✅ OS-3 complete (IPC Bridge + Protocol)
- ✅ OS-4 complete (Hardware Abstraction Layer)

---

## Deliverables

| # | Deliverable | File/Location | Status |
|---|---|---|---|
| 1 | Process Isolation (multiprocessing) | `src/jaya_os/sandbox/process_isolation.py` | 🔄 Planned |
| 2 | User Namespace Isolation (Linux) | `src/jaya_os/sandbox/user_namespace.py` | 🔄 Planned |
| 3 | Container Integration (Docker/Podman) | `src/jaya_os/sandbox/container.py` | 🔄 Planned |
| 4 | WASM Runtime (wasmtime) | `src/jaya_os/sandbox/wasm_runtime.py` | 🔄 Planned |
| 5 | Formal Verification (TLA+/Coq) | `specs/sandbox.tla`, `specs/sandbox.v` | 🔄 Planned |
| 6 | Capability-based FS (FUSE) | `src/jaya_os/sandbox/capability_fs.py` | 🔄 Planned |
| 7 | Network Namespace Isolation | `src/jaya_os/sandbox/network_namespace.py` | 🔄 Planned |
| 8 | Audit Log Integrity (Merkle tree) | `src/jaya_os/sandbox/audit_log.py` | 🔄 Planned |
| 9 | Unit tests | `tests/test_sandbox_*.py` | 🔄 Planned |
| 10 | Penetration testing suite | `scripts/penetration_test.py` | 🔄 Planned |

---

## Technical Implementation

### 5.1 Process Isolation

```python
# src/jaya_os/sandbox/process_isolation.py
import multiprocessing
from multiprocessing import Process, Queue, Pipe
from dataclasses import dataclass
from typing import Any, Dict, Optional, Callable
import sys
import os
import signal

@dataclass
class IsolatedFeature:
    feature_id: str
    module_name: str
    process: multiprocessing.Process
    request_queue: Queue
    response_queue: Queue
    pid: int
    
    def dispatch(self, action: str, payload: Dict) -> Any:
        """Send action to isolated feature process."""
        request_id = str(uuid.uuid4())
        self.request_queue.put({
            "request_id": request_id,
            "action": action,
            "payload": payload
        })
        
        # Wait for response
        while True:
            response = self.response_queue.get()
            if response.get("request_id") == request_id:
                if response.get("error"):
                    raise Exception(response["error"])
                return response.get("result")
    
    def stop(self, timeout: float = 5.0):
        """Stop the isolated feature process."""
        self.request_queue.put(None)  # Shutdown signal
        self.process.join(timeout=timeout)
        if self.process.is_alive():
            self.process.terminate()
            self.process.join()

class ProcessIsolationManager:
    def __init__(self):
        self.features: Dict[str, IsolatedFeature] = {}
    
    def spawn_feature(self, feature_id: str, module_name: str, 
                      config: Dict = None) -> IsolatedFeature:
        """Spawn a feature in an isolated process."""
        request_queue = Queue()
        response_queue = Queue()
        
        process = multiprocessing.Process(
            target=self._run_feature,
            args=(feature_id, module_name, config, request_queue, response_queue),
            daemon=True
        )
        process.start()
        
        feature = IsolatedFeature(
            feature_id=feature_id,
            module_name=module_name,
            process=process,
            request_queue=request_queue,
            response_queue=response_queue,
            pid=process.pid
        )
        
        self.features[feature_id] = feature
        return feature
    
    def _run_feature(self, feature_id: str, module_name: str, 
                     config: Dict, request_queue: Queue, response_queue: Queue):
        """Entry point for isolated feature process."""
        # Set up sandbox in child process
        from jaya_os.sandbox import setup_sandbox
        setup_sandbox(feature_id)
        
        # Apply resource limits
        from jaya_os.sandbox.resource_limiter import apply_limits
        apply_limits()
        
        # Import and initialize feature
        try:
            module = __import__(module_name, fromlist=['Feature'])
            feature = module.Feature(config or {})
        except Exception as e:
            response_queue.put({"error": f"Feature init failed: {e}"})
            return
        
        # Main loop
        while True:
            request = request_queue.get()
            if request is None:  # Shutdown signal
                break
            
            request_id = request.get("request_id")
            action = request.get("action")
            payload = request.get("payload", {})
            
            try:
                # Dispatch to feature
                if hasattr(feature, action):
                    method = getattr(feature, action)
                    result = method(payload)
                else:
                    result = feature.handle_action(action, payload)
                
                response_queue.put({
                    "request_id": request_id,
                    "result": result
                })
            except Exception as e:
                response_queue.put({
                    "request_id": request_id,
                    "error": str(e),
                    "traceback": traceback.format_exc()
                })
    
    def stop_feature(self, feature_id: str, timeout: float = 5.0):
        """Stop an isolated feature."""
        feature = self.features.pop(feature_id, None)
        if feature:
            feature.stop(timeout)
    
    def stop_all(self):
        for feature in list(self.features.values()):
            feature.stop()
        self.features.clear()
```

### 5.2 User Namespace Isolation (Linux)

```python
# src/jaya_os/sandbox/user_namespace.py
import os
import subprocess
import ctypes
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class UserNamespaceConfig:
    uid_map: List[tuple] = None  # [(container_uid, host_uid, count)]
    gid_map: List[tuple] = None
    deny_setgroups: bool = True

class UserNamespaceManager:
    """Manage Linux user namespaces for feature isolation."""
    
    CLONE_NEWUSER = 0x10000000
    CLONE_NEWNS = 0x00020000
    CLONE_NEWPID = 0x20000000
    CLONE_NEWNET = 0x40000000
    CLONE_NEWUTS = 0x04000000
    CLONE_NEWIPC = 0x08000000
    CLONE_NEWCGROUP = 0x02000000
    
    def __init__(self):
        self.libc = ctypes.CDLL("libc.so.6", use_errno=True)
    
    def create_namespace(self, flags: int = None) -> int:
        """Create new user namespace and return child PID."""
        if flags is None:
            flags = (self.CLONE_NEWUSER | self.CLONE_NEWNS | 
                     self.CLONE_NEWPID | self.CLONE_NEWNET |
                     self.CLONE_NEWUTS | self.CLONE_NEWIPC |
                     self.CLONE_NEWCGROUP)
        
        # Use clone() syscall
        child_pid = self.libc.clone(
            ctypes.CFUNCTYPE(ctypes.c_int)(self._child_func),
            ctypes.c_void_p(),  # stack (NULL = allocate)
            flags,
            None  # arg
        )
        
        if child_pid == -1:
            errno = ctypes.get_errno()
            raise OSError(errno, os.strerror(errno))
        
        return child_pid
    
    def _child_func(self) -> int:
        """Child process entry point."""
        # Setup UID/GID maps
        self._setup_uid_gid_map()
        
        # Drop capabilities
        self._drop_capabilities()
        
        # Execute feature
        os.execvpe("/usr/bin/python3", ["python3", "-m", "feature_module"], os.environ)
        return 1
    
    def _setup_uid_gid_map(self):
        """Write UID/GID maps for the namespace."""
        pid = os.getpid()
        
        # Deny setgroups
        with open(f"/proc/{pid}/setgroups", "w") as f:
            f.write("deny")
        
        # Map root inside namespace to current user outside
        uid = os.getuid()
        gid = os.getgid()
        
        with open(f"/proc/{pid}/uid_map", "w") as f:
            f.write(f"0 {uid} 1\n")
        
        with open(f"/proc/{pid}/gid_map", "w") as f:
            f.write(f"0 {gid} 1\n")
    
    def _drop_capabilities(self):
        """Drop all capabilities except minimal set."""
        import subprocess
        # Keep only CAP_DAC_OVERRIDE, CAP_CHOWN, CAP_FOWNER
        subprocess.run(["capsh", "--drop=all", "--caps=cap_dac_override,cap_chown,cap_fowner+eip"], 
                       check=False)
    
    def run_in_namespace(self, command: List[str], 
                         uid_map: List[tuple] = None,
                         gid_map: List[tuple] = None) -> subprocess.CompletedProcess:
        """Run command in new user namespace."""
        # Use unshare command
        cmd = ["unshare", "--user", "--map-root-user", "--map-current-user"]
        
        if uid_map:
            for container_uid, host_uid, count in uid_map:
                cmd.extend(["--uid-map", f"{container_uid} {host_uid} {count}"])
        
        if gid_map:
            for container_gid, host_gid, count in gid_map:
                cmd.extend(["--gid-map", f"{container_gid} {host_gid} {count}"])
        
        cmd.extend(["--", *command])
        
        return subprocess.run(command, capture_output=True, text=True)
```

### 5.3 Container Integration

```python
# src/jaya_os/sandbox/container.py
import docker
import subprocess
import json
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum

class ContainerRuntime(Enum):
    DOCKER = "docker"
    PODMAN = "podman"

@dataclass
class ContainerConfig:
    image: str
    name: str
    cpu_limit: str = "0.5"  # CPUs
    memory_limit: str = "200m"  # Memory
    network_mode: str = "none"  # No network by default
    volumes: List[str] = None
    environment: Dict[str, str] = None
    capabilities: List[str] = None
    security_opt: List[str] = None
    read_only: bool = True
    user: str = "1000:1000"  # Non-root user

class ContainerManager:
    def __init__(self, runtime: ContainerRuntime = ContainerRuntime.DOCKER):
        self.runtime = runtime
        self.client = None
        if runtime == ContainerRuntime.DOCKER:
            self.client = docker.from_env()
    
    def create_container(self, config: ContainerConfig) -> str:
        """Create and start container."""
        if self.runtime == ContainerRuntime.DOCKER:
            return self._create_docker_container(config)
        else:
            return self._create_podman_container(config)
    
    def _create_docker_container(self, config: ContainerConfig) -> str:
        container = self.client.containers.run(
            config.image,
            name=config.name,
            cpu_quota=int(float(config.cpu_limit) * 100000),
            mem_limit=config.memory_limit,
            network_mode=config.network_mode,
            volumes=config.volumes or {},
            environment=config.environment or {},
            cap_add=config.capabilities or [],
            security_opt=config.security_opt or [],
            read_only=config.read_only,
            user=config.user,
            detach=True,
            remove=True  # Auto-remove on stop
        )
        return container.id
    
    def _create_podman_container(self, config: ContainerConfig) -> str:
        cmd = ["podman", "run", "-d", "--name", config.name]
        
        cmd.extend(["--cpus", config.cpu_limit])
        cmd.extend(["--memory", config.memory_limit])
        cmd.extend(["--network", config.network_mode])
        
        if config.volumes:
            for vol in config.volumes:
                cmd.extend(["-v", vol])
        
        if config.environment:
            for k, v in config.environment.items():
                cmd.extend(["-e", f"{k}={v}"])
        
        if config.capabilities:
            for cap in config.capabilities:
                cmd.extend(["--cap-add", cap])
        
        if config.security_opt:
            for opt in config.security_opt:
                cmd.extend(["--security-opt", opt])
        
        if config.read_only:
            cmd.append("--read-only")
        
        cmd.extend(["--user", config.user])
        cmd.append(config.image)
        
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    
    def stop_container(self, container_id: str, timeout: int = 10):
        if self.runtime == ContainerRuntime.DOCKER:
            container = self.client.containers.get(container_id)
            container.stop(timeout=timeout)
        else:
            subprocess.run(["podman", "stop", "-t", str(timeout), container_id], check=True)
    
    def get_logs(self, container_id: str) -> str:
        if self.runtime == ContainerRuntime.DOCKER:
            container = self.client.containers.get(container_id)
            return container.logs().decode('utf-8')
        else:
            result = subprocess.run(["podman", "logs", container_id], 
                                  capture_output=True, text=True)
            return result.stdout
    
    def exec_in_container(self, container_id: str, command: List[str]) -> str:
        if self.runtime == ContainerRuntime.DOCKER:
            container = self.client.containers.get(container_id)
            result = container.exec_run(command)
            return result.output.decode('utf-8')
        else:
            cmd = ["podman", "exec", container_id] + command
            result = subprocess.run(cmd, capture_output=True, text=True)
            return result.stdout

class FeatureContainer:
    """High-level feature container abstraction."""
    
    def __init__(self, manager: ContainerManager, feature_id: str):
        self.manager = manager
        self.feature_id = feature_id
        self.container_id: Optional[str] = None
    
    def start(self, image: str, config: ContainerConfig = None):
        if config is None:
            config = ContainerConfig(
                image=image,
                name=f"jaya_feature_{self.feature_id}",
                cpu_limit="0.5",
                memory_limit="200m",
                network_mode="none",
                read_only=True,
                user="1000:1000"
            )
        self.container_id = self.manager.create_container(config)
    
    def stop(self, timeout: int = 10):
        if self.container_id:
            self.manager.stop_container(self.container_id, timeout)
            self.container_id = None
    
    def exec(self, command: List[str]) -> str:
        if self.container_id:
            return self.manager.exec_in_container(self.container_id, command)
        raise RuntimeError("Container not started")
    
    def get_logs(self) -> str:
        if self.container_id:
            return self.manager.get_logs(self.container_id)
        return ""
```

### 5.4 WASM Runtime

```python
# src/jaya_os/sandbox/wasm_runtime.py
import wasmtime
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Callable
import json

@dataclass
class WASMFeatureConfig:
    module_path: str
    allowed_imports: List[str] = None
    allowed_exports: List[str] = None
    memory_limit: int = 10 * 1024 * 1024  # 10MB
    fuel_limit: int = 1000000  # Instruction limit

class WASMFeature:
    def __init__(self, config: WASMFeatureConfig):
        self.config = config
        self.engine = wasmtime.Engine()
        self.store = wasmtime.Store(self.engine)
        self.module = None
        self.instance = None
        self.memory = None
        self._setup_limits()
    
    def _setup_limits(self):
        # Set memory limit
        self.store.limiter = wasmtime.ResourceLimiter(
            memory_size=self.config.memory_limit
        )
        
        # Set fuel limit (instruction count)
        if self.config.fuel_limit:
            self.store.add_fuel(self.config.fuel_limit)
    
    def load(self, wasm_bytes: bytes = None):
        """Load WASM module from file or bytes."""
        if wasm_bytes:
            self.module = wasmtime.Module(self.engine, wasm_bytes)
        else:
            self.module = wasmtime.Module.from_file(self.engine, self.config.module_path)
        
        # Define imports
        imports = self._create_imports()
        
        # Instantiate
        self.instance = wasmtime.Instance(self.store, self.module, imports)
        self.memory = self.instance.exports(self.store)["memory"]
    
    def _create_imports(self) -> List[wasmtime.Extern]:
        """Create import functions for WASM module."""
        imports = []
        
        # Define host functions that WASM can call
        for import_name in self.config.allowed_imports or []:
            if import_name == "js_log":
                func = wasmtime.Func(self.store, 
                    wasmtime.FuncType([wasmtime.ValType.i32(), wasmtime.ValType.i32()], []),
                    self._host_log)
                imports.append(func)
            elif import_name == "js_fetch":
                func = wasmtime.Func(self.store,
                    wasmtime.FuncType([wasmtime.ValType.i32(), wasmtime.ValType.i32()], [wasmtime.ValType.i32()]),
                    self._host_fetch)
                imports.append(func)
            # ... more imports
        
        return imports
    
    def _host_log(self, caller, ptr: int, len: int):
        """Host function: log from WASM."""
        memory = self.memory
        data = memory.read(caller, ptr, len)
        print(f"[WASM] {data.decode('utf-8')}")
    
    def _host_fetch(self, caller, url_ptr: int, url_len: int) -> int:
        """Host function: HTTP fetch from WASM."""
        memory = self.memory
        url = memory.read(caller, url_ptr, url_len).decode('utf-8')
        
        # Validate URL against allowed domains
        # ... validation logic ...
        
        # Perform fetch (async would need async host functions)
        # For now, return error
        return -1
    
    def call(self, func_name: str, *args) -> Any:
        """Call exported WASM function."""
        func = self.instance.exports(self.store)[func_name]
        return func(self.store, *args)
    
    def get_memory(self) -> bytes:
        """Get WASM linear memory as bytes."""
        return self.memory.data(self.store)
    
    def write_memory(self, offset: int, data: bytes):
        """Write to WASM linear memory."""
        self.memory.write(self.store, offset, data)

class WASMRuntime:
    def __init__(self):
        self.features: Dict[str, WASMFeature] = {}
    
    def load_feature(self, feature_id: str, config: WASMFeatureConfig) -> WASMFeature:
        feature = WASMFeature(config)
        feature.load()
        self.features[feature_id] = feature
        return feature
    
    def call_feature(self, feature_id: str, func_name: str, *args) -> Any:
        feature = self.features.get(feature_id)
        if not feature:
            raise ValueError(f"Feature not loaded: {feature_id}")
        return feature.call(func_name, *args)
    
    def unload_feature(self, feature_id: str):
        self.features.pop(feature_id, None)
```

### 5.5 Formal Verification (TLA+)

```tla
---- MODULE Sandbox ----
EXTENDS Naturals, Sequences, TLC

CONSTANTS Features, Capabilities, Resources

VARIABLES 
    featureState,      \* [f \in Features |-> {"running", "stopped", "error"}]
    capabilities,      \* [f \in Features |-> SUBSET Capabilities]
    resourceUsage,     \* [f \in Features, r \in Resources |-> Nat]
    auditLog           \* Seq(Record)

TypeOK == 
    /\ featureState \in [Features -> {"running", "stopped", "error"}]
    /\ capabilities \in [Features -> SUBSET Capabilities]
    /\ resourceUsage \in [Features \X Resources -> Nat]
    /\ auditLog \in Seq(Record)

Record == [feature: Features, capability: Capabilities, resource: Resources, 
           action: {"request", "grant", "deny", "release"}, 
           timestamp: Nat]

Init == 
    /\ featureState = [f \in Features |-> "stopped"]
    /\ capabilities = [f \in Features |-> {}]
    /\ resourceUsage = [f \in Features, r \in Resources |-> 0]
    /\ auditLog = <<>>

RequestCapability(f, cap, resource) ==
    /\ featureState[f] = "running"
    /\ cap \in Capabilities
    /\ resource \in Resources
    /\ cap \notin capabilities[f]
    /\ capabilities' = [capabilities EXCEPT ![f] = @ \cup {cap}]
    /\ auditLog' = Append(auditLog, 
        [feature |-> f, capability |-> cap, resource |-> resource, 
         action |-> "request", timestamp |-> Len(auditLog)])

GrantCapability(f, cap, resource) ==
    /\ featureState[f] = "running"
    /\ cap \in Capabilities
    /\ resource \in Resources
    /\ cap \in capabilities[f]
    /\ resourceUsage[f, resource] < MaxResource[resource]
    /\ resourceUsage' = [resourceUsage EXCEPT ![f, resource] = @ + 1]
    /\ auditLog' = Append(auditLog,
        [feature |-> f, capability |-> cap, resource |-> resource,
         action |-> "grant", timestamp |-> Len(auditLog)])

DenyCapability(f, cap, resource) ==
    /\ featureState[f] = "running"
    /\ cap \in Capabilities
    /\ resource \in Resources
    /\ cap \notin capabilities[f] \/ resourceUsage[f, resource] >= MaxResource[resource]
    /\ auditLog' = Append(auditLog,
        [feature |-> f, capability |-> cap, resource |-> resource,
         action |-> "deny", timestamp |-> Len(auditLog)])

ReleaseCapability(f, cap, resource) ==
    /\ featureState[f] = "running"
    /\ cap \in capabilities[f]
    /\ resourceUsage[f, resource] > 0
    /\ capabilities' = [capabilities EXCEPT ![f] = @ \ {cap}]
    /\ resourceUsage' = [resourceUsage EXCEPT ![f, resource] = @ - 1]
    /\ auditLog' = Append(auditLog,
        [feature |-> f, capability |-> cap, resource |-> resource,
         action |-> "release", timestamp |-> Len(auditLog)])

StartFeature(f) ==
    /\ featureState[f] = "stopped"
    /\ featureState' = [featureState EXCEPT ![f] = "running"]

StopFeature(f) ==
    /\ featureState[f] = "running"
    /\ featureState' = [featureState EXCEPT ![f] = "stopped"]
    /\ capabilities' = [capabilities EXCEPT ![f] = {}]
    /\ resourceUsage' = [r \in Resources |-> [f \in Features |-> 0]]

Next ==
    \E f \in Features, cap \in Capabilities, resource \in Resources:
        \/ RequestCapability(f, cap, resource)
        \/ GrantCapability(f, cap, resource)
        \/ DenyCapability(f, cap, resource)
        \/ ReleaseCapability(f, cap, resource)
        \/ StartFeature(f)
        \/ StopFeature(f)

Safety == 
    /\ \A f \in Features, r \in Resources: resourceUsage[f, r] <= MaxResource[r]
    /\ \A f \in Features: capabilities[f] \subseteq AllowedCapabilities[f]
    /\ \A f \in Features: featureState[f] = "running" => capabilities[f] # {} => 
        \E cap \in capabilities[f]: TRUE

Liveness == 
    \A f \in Features: <> (featureState[f] = "stopped")

Spec == Init /\ [][Next]_vars /\ Safety /\ Liveness

====
```

### 5.6 Capability-based Filesystem (FUSE)

```python
# src/jaya_os/sandbox/capability_fs.py
import os
import errno
from fuse import FUSE, FuseOSError, Operations
from dataclasses import dataclass
from typing import Dict, List, Optional, Set
from pathlib import Path

@dataclass
class CapabilityFSConfig:
    allowed_read: List[str]
    allowed_write: List[str]
    mount_point: str

class CapabilityFS(Operations):
    def __init__(self, config: CapabilityFSConfig):
        self.config = config
        self.allowed_read = [Path(p).resolve() for p in config.allowed_read]
        self.allowed_write = [Path(p).resolve() for p in config.allowed_write]
        self.fd_counter = 0
        self.open_files: Dict[int, Dict] = {}
    
    def _check_read(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(resolved.is_relative_to(p) for p in self.allowed_read)
    
    def _check_write(self, path: Path) -> bool:
        resolved = path.resolve()
        return any(resolved.is_relative_to(p) for p in self.allowed_write)
    
    def _full_path(self, path: str) -> Path:
        return Path(self.config.mount_point) / path.lstrip('/')
    
    # Filesystem operations
    def getattr(self, path: str, fh: int = None):
        full = self._full_path(path)
        if not full.exists():
            raise FuseOSError(errno.ENOENT)
        st = full.stat()
        return dict((key, getattr(st, key)) for key in (
            'st_atime', 'st_ctime', 'st_gid', 'st_mode', 'st_mtime',
            'st_nlink', 'st_size', 'st_uid'))
    
    def readdir(self, path: str, fh: int):
        full = self._full_path(path)
        if not self._check_read(full):
            raise FuseOSError(errno.EACCES)
        return ['.', '..'] + [p.name for p in full.iterdir()]
    
    def open(self, path: str, flags: int):
        full = self._full_path(path)
        if flags & os.O_WRONLY or flags & os.O_RDWR:
            if not self._check_write(full):
                raise FuseOSError(errno.EACCES)
        else:
            if not self._check_read(full):
                raise FuseOSError(errno.EACCES)
        
        self.fd_counter += 1
        self.open_files[self.fd_counter] = {"path": full, "flags": flags}
        return self.fd_counter
    
    def read(self, path: str, size: int, offset: int, fh: int):
        file_info = self.open_files.get(fh)
        if not file_info:
            raise FuseOSError(errno.EBADF)
        
        with open(file_info["path"], 'rb') as f:
            f.seek(offset)
            return f.read(size)
    
    def write(self, path: str, data: bytes, offset: int, fh: int):
        file_info = self.open_files.get(fh)
        if not file_info:
            raise FuseOSError(errno.EBADF)
        
        if not self._check_write(file_info["path"]):
            raise FuseOSError(errno.EACCES)
        
        with open(file_info["path"], 'r+b') as f:
            f.seek(offset)
            f.write(data)
        return len(data)
    
    def release(self, path: str, fh: int):
        self.open_files.pop(fh, None)
        return 0
    
    def create(self, path: str, mode: int, fi: int = None):
        full = self._full_path(path)
        if not self._check_write(full.parent):
            raise FuseOSError(errno.EACCES)
        full.touch(mode=mode)
        return 0
    
    def unlink(self, path: str):
        full = self._full_path(path)
        if not self._check_write(full):
            raise FuseOSError(errno.EACCES)
        full.unlink()
        return 0
    
    def mkdir(self, path: str, mode: int):
        full = self._full_path(path)
        if not self._check_write(full.parent):
            raise FuseOSError(errno.EACCES)
        full.mkdir(mode=mode, parents=True)
        return 0
    
    def rmdir(self, path: str):
        full = self._full_path(path)
        if not self._check_write(full):
            raise FuseOSError(errno.EACCES)
        full.rmdir()
        return 0
    
    def rename(self, old: str, new: str):
        old_full = self._full_path(old)
        new_full = self._full_path(new)
        if not self._check_write(old_full) or not self._check_write(new_full.parent):
            raise FuseOSError(errno.EACCES)
        old_full.rename(new_full)
        return 0

def mount_capability_fs(config: CapabilityFSConfig):
    """Mount capability-based filesystem."""
    fs = CapabilityFS(config)
    FUSE(fs, config.mount_point, foreground=True, allow_other=True)
```

### 5.7 Network Namespace Isolation

```python
# src/jaya_os/sandbox/network_namespace.py
import subprocess
import os
from dataclasses import dataclass
from typing: List, Optional

@dataclass
class NetworkNamespaceConfig:
    name: str
    enable_loopback: bool = True
    allowed_ports: List[int] = None
    allowed_domains: List[str] = None
    bandwidth_limit: str = None  # e.g., "10mbit"

class NetworkNamespaceManager:
    def __init__(self):
        self.namespaces: Dict[str, str] = {}  # name -> netns id
    
    def create_namespace(self, config: NetworkNamespaceConfig) -> str:
        """Create new network namespace."""
        ns_id = f"jaya_{config.name}"
        
        # Create namespace
        subprocess.run(["ip", "netns", "add", ns_id], check=True)
        
        # Enable loopback
        if config.enable_loopback:
            subprocess.run(["ip", "netns", "exec", ns_id, "ip", "link", "set", "lo", "up"], check=True)
        
        # Apply bandwidth limit
        if config.bandwidth_limit:
            subprocess.run([
                "tc", "qdisc", "add", "dev", "lo", "root", "tbf",
                "rate", config.bandwidth_limit, "burst", "1600", "latency", "50ms"
            ], check=True)
        
        self.namespaces[config.name] = ns_id
        return ns_id
    
    def delete_namespace(self, name: str):
        ns_id = self.namespaces.pop(name, None)
        if ns_id:
            subprocess.run(["ip", "netns", "delete", ns_id], check=False)
    
    def exec_in_namespace(self, name: str, command: List[str]) -> subprocess.CompletedProcess:
        ns_id = self.namespaces.get(name)
        if not ns_id:
            raise ValueError(f"Namespace not found: {name}")
        
        cmd = ["ip", "netns", "exec", ns_id] + command
        return subprocess.run(cmd, capture_output=True, text=True)
    
    def add_veth_pair(self, name: str, peer_name: str, ns_name: str):
        """Add veth pair, one end in namespace."""
        ns_id = self.namespaces.get(ns_name)
        if not ns_id:
            raise ValueError(f"Namespace not found: {ns_name}")
        
        # Create veth pair
        subprocess.run(["ip", "link", "add", name, "type", "veth", "peer", "name", peer_name], check=True)
        
        # Move peer to namespace
        subprocess.run(["ip", "link", "set", peer_name, "netns", ns_id], check=True)
        
        # Bring up both ends
        subprocess.run(["ip", "link", "set", name, "up"], check=True)
        self.exec_in_namespace(ns_name, ["ip", "link", "set", peer_name, "up"])
    
    def apply_bandwidth_limit(self, name: str, interface: str, limit: str):
        """Apply TBF qdisc for bandwidth limiting."""
        ns_id = self.namespaces.get(name)
        if not ns_id:
            raise ValueError(f"Namespace not found: {name}")
        
        subprocess.run([
            "ip", "netns", "exec", ns_id,
            "tc", "qdisc", "add", "dev", interface, "root", "tbf",
            "rate", limit, "burst", "1600", "latency", "50ms"
        ], check=True)
    
    def apply_firewall_rules(self, name: str, allowed_ports: List[int], 
                             allowed_domains: List[str]):
        """Apply nftables rules in namespace."""
        ns_id = self.namespaces.get(name)
        if not ns_id:
            raise ValueError(f"Namespace not found: {name}")
        
        # Flush existing rules
        self.exec_in_namespace(name, ["nft", "flush", "ruleset"])
        
        # Default deny
        self.exec_in_namespace(name, ["nft", "add", "table", "inet", "filter"])
        self.exec_in_namespace(name, ["nft", "add", "chain", "inet", "filter", "input", "{", "type", "filter", "hook", "input", "priority", "0", ";", "policy", "drop", ";", "}"])
        self.exec_in_namespace(name, ["nft", "add", "chain", "inet", "filter", "output", "{", "type", "filter", "hook", "output", "priority", "0", ";", "policy", "drop", ";", "}"])
        
        # Allow loopback
        self.exec_in_namespace(name, ["nft", "add", "rule", "inet", "filter", "input", "iif", "lo", "accept"])
        self.exec_in_namespace(name, ["nft", "add", "rule", "inet", "filter", "output", "oif", "lo", "accept"])
        
        # Allow established/related
        self.exec_in_namespace(name, ["nft", "add", "rule", "inet", "filter", "input", "ct", "state", "established,related", "accept"])
        self.exec_in_namespace(name, ["nft", "add", "rule", "inet", "filter", "output", "ct", "state", "established,related", "accept"])
        
        # Allow specific ports
        for port in allowed_ports:
            self.exec_in_namespace(name, ["nft", "add", "rule", "inet", "filter", "output", "tcp", "dport", str(port), "accept"])
        
        # DNS
        self.exec_in_namespace(name, ["nft", "add", "rule", "inet", "filter", "output", "udp", "dport", "53", "accept"])
```

### 5.8 Audit Log Integrity (Merkle Tree)

```python
# src/jaya_os/sandbox/audit_log.py
import hashlib
import json
import time
from dataclasses import dataclass, field
from typing: List, Optional, Dict, Any
from pathlib import Path

@dataclass
class AuditEntry:
    index: int
    timestamp: float
    feature_id: str
    capability: str
    resource: str
    action: str  # "request", "grant", "deny", "release"
    result: str  # "allowed", "denied"
    duration_ms: float
    prev_hash: str
    hash: str = field(init=False)
    
    def __post_init__(self):
        self.hash = self._compute_hash()
    
    def _compute_hash(self) -> str:
        data = f"{self.index}{self.timestamp}{self.feature_id}{self.capability}{self.resource}{self.action}{self.result}{self.duration_ms}{self.prev_hash}"
        return hashlib.sha256(data.encode()).hexdigest()

class MerkleAuditLog:
    def __init__(self, log_path: str):
        self.log_path = Path(log_path)
        self.entries: List[AuditEntry] = []
        self._load()
    
    def _load(self):
        if self.log_path.exists():
            with open(self.log_path, 'r') as f:
                for line in f:
                    entry_data = json.loads(line)
                    entry = AuditEntry(**entry_data)
                    self.entries.append(entry)
    
    def append(self, feature_id: str, capability: str, resource: str,
               action: str, result: str, duration_ms: float) -> AuditEntry:
        prev_hash = self.entries[-1].hash if self.entries else "0" * 64
        entry = AuditEntry(
            index=len(self.entries),
            timestamp=time.time(),
            feature_id=feature_id,
            capability=capability,
            resource=resource,
            action=action,
            result=result,
            duration_ms=duration_ms,
            prev_hash=prev_hash
        )
        self.entries.append(entry)
        self._persist(entry)
        return entry
    
    def _persist(self, entry: AuditEntry):
        with open(self.log_path, 'a') as f:
            f.write(json.dumps({
                "index": entry.index,
                "timestamp": entry.timestamp,
                "feature_id": entry.feature_id,
                "capability": entry.capability,
                "resource": entry.resource,
                "action": entry.action,
                "result": entry.result,
                "duration_ms": entry.duration_ms,
                "prev_hash": entry.prev_hash,
                "hash": entry.hash
            }) + '\n')
    
    def verify_integrity(self) -> bool:
        """Verify the entire log chain."""
        prev_hash = "0" * 64
        for entry in self.entries:
            if entry.prev_hash != prev_hash:
                return False
            if entry.hash != entry._compute_hash():
                return False
            prev_hash = entry.hash
        return True
    
    def get_merkle_root(self) -> str:
        """Get Merkle root of all entries."""
        if not self.entries:
            return "0" * 64
        
        # Build Merkle tree
        hashes = [entry.hash for entry in self.entries]
        while len(hashes) > 1:
            if len(hashes) % 2 == 1:
                hashes.append(hashes[-1])  # Duplicate last if odd
            new_hashes = []
            for i in range(0, len(hashes), 2):
                combined = hashes[i] + hashes[i+1]
                new_hashes.append(hashlib.sha256(combined.encode()).hexdigest())
            hashes = new_hashes
        return hashes[0]
    
    def get_proof(self, index: int) -> List[str]:
        """Get Merkle proof for entry at index."""
        if index >= len(self.entries):
            return []
        
        # Build tree and return sibling hashes along path
        # Simplified implementation
        return []
    
    def query(self, feature_id: str = None, capability: str = None,
              action: str = None, since: float = None) -> List[AuditEntry]:
        results = []
        for entry in self.entries:
            if feature_id and entry.feature_id != feature_id:
                continue
            if capability and entry.capability != capability:
                continue
            if action and entry.action != action:
                continue
            if since and entry.timestamp < since:
                continue
            results.append(entry)
        return results
```

---

## Verification Checklist

### Functional
- [ ] Process isolation: features run in separate processes
- [ ] User namespaces: Linux UID/GID mapping works
- [ ] Container integration: Docker/Podman feature containers
- [ ] WASM runtime: features compile to WASM, execute safely
- [ ] Formal verification: TLA+ model checks safety/liveness
- [ ] Capability FS: FUSE filesystem enforces path restrictions
- [ ] Network namespaces: isolated network stacks with firewall
- [ ] Audit log: Merkle tree integrity verification

### Security
- [ ] No capability leakage between features
- [ ] Resource limits enforced (CPU, memory, network)
- [ ] Filesystem access restricted to declared paths
- [ ] Network access restricted to declared domains/ports
- [ ] Audit log tamper-evident (Merkle tree)

### Quality
- [ ] Unit tests for each sandbox component
- [ ] Integration tests: feature lifecycle in sandbox
- [ ] Penetration testing suite
- [ ] Formal model checking (TLC for TLA+)

### Performance
- [ ] Process spawn < 100ms
- [ ] WASM execution near-native speed
- [ ] FUSE overhead < 10%
- [ ] Network namespace creation < 50ms

---

## Success Criteria
- [ ] Features run in fully isolated processes
- [ ] Linux user namespaces provide UID isolation
- [ ] Containerized features work with Docker/Podman
- [ ] WASM features execute with same API
- [ ] TLA+ model verified (safety + liveness)
- [ ] Capability FS enforces path restrictions
- [ ] Network namespaces isolate traffic
- [ ] Audit log cryptographically verifiable

---

## 🔗 Related

- [Sandbox Isolation](../05-research-notes/sandbox-isolation.md)
- [Capability System](../05-research-notes/capability-system.md)
- [Runtime Features](../03-features/runtime-features.md)
- [Roadmap Overview](../06-roadmap/README.md)